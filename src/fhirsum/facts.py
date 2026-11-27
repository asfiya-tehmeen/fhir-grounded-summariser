"""Key-facts extractor (pure code). Produces the 'expected facts' list used for omission (recall)
scoring, plus deterministic safety checks that are shown to clinicians alongside — never instead of —
the summary. No LLM is involved here."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta

from . import clinical
from .record import PatientRecord, concept_text, parse_date, ref_of, resource_date

LAB_WINDOW_DAYS = 365
TREND_REL_CHANGE = 0.05   # >5% change first->last = increasing/decreasing


@dataclass
class Fact:
    fact_id: str
    kind: str                 # allergy | no_allergy_record | medication | problem | abnormal_lab | lab_trend
    label: str
    refs: list[str]           # FHIR refs ("Type/id") that support it
    weight: float
    detail: dict = field(default_factory=dict)


@dataclass
class SafetyCheck:
    kind: str     # duplicate_medication | allergy_conflict | no_allergy_record | quarantined_text | critical_lab
                  # | note_conflicts_record
    message: str
    refs: list[str]
    severity: float = 0.0     # critical_lab: how many times past the limit (ranks the alert banner)


# A note sentence that says an ACTIVE drug was stopped, or an ACTIVE allergy was ruled out, contradicts the
# structured record. It may be a real update the medication list has not caught up with, or poisoning; either way
# the clinician must see the discrepancy. The sentence is NOT hidden from the model (it can be real clinical news).
CONFLICT_WORDS = re.compile(r"\b(discontinu\w*|stopped|no longer|ruled out|not allergic|tolerat\w*|removed|"
                            r"outdated|out of date|left out|omit\w*|no known allerg\w*|resolved)\b", re.I)
CLASS_WORDS = {"warfarin": ["anticoagulant", "blood thinner"], "apixaban": ["anticoagulant", "blood thinner"],
               "rivaroxaban": ["anticoagulant", "blood thinner"], "dabigatran": ["anticoagulant", "blood thinner"],
               "heparin": ["anticoagulant", "blood thinner"], "enoxaparin": ["anticoagulant", "blood thinner"],
               "insulin": ["insulin"], "metformin": ["diabetes medicine"]}
SALT_WORDS = {"sodium", "potassium", "hydrochloride", "calcium", "magnesium", "sulfate", "acetate", "citrate",
              "maleate", "succinate", "tartrate", "besylate", "mesylate", "bromide", "chloride", "hour", "extended",
              "release", "actuat", "metered", "dose", "inhaler"}
_SENTENCE = re.compile(r"(?<=[.!?\n])\s+")


def note_conflicts(rec: PatientRecord, note_texts: dict[str, str]) -> list[SafetyCheck]:
    out: list[SafetyCheck] = []
    targets: list[tuple[str, list[str]]] = []          # (record ref, words that name it)
    for m in rec.of_type("MedicationRequest", "MedicationStatement"):
        if rec.is_active(m):
            # "warfarin sodium 5 MG" -> ["warfarin"]: salts and forms are not how notes name a drug
            words = [w for w in re.findall(r"[a-z]{4,}", clinical.ingredient_key(rec.med_name(m)))
                     if w not in SALT_WORDS]
            for w in list(words):
                words += CLASS_WORDS.get(w, [])
            if words:
                targets.append((ref_of(m), sorted(set(words))))
    for a in rec.of_type("AllergyIntolerance"):
        if rec.is_active(a):
            sub = concept_text(a.get("code")).lower()
            words = [w for w in re.findall(r"[a-z]{5,}", sub) if w not in ("allergy", "substance", "dietary")]
            words += [k for k in clinical.ALLERGY_CLASS if k in sub]
            targets.append((ref_of(a), sorted(set(words)) + ["allerg"]))
    for doc_ref, txt in note_texts.items():
        for sent in _SENTENCE.split(txt):
            if not CONFLICT_WORDS.search(sent):
                continue
            low = sent.lower()
            for ref, words in targets:
                named = [w for w in words if w != "allerg" and w in low]
                if named or ("allerg" in words and "no known allerg" in low):
                    out.append(SafetyCheck("note_conflicts_record",
                                           f"Note says '{sent.strip()[:140]}' but {ref.split('/')[0]} is active in the "
                                           "record. Check which is current.", [doc_ref, ref]))
    seen, uniq = set(), []
    for c in out:                                   # one alert per (note, resource)
        k = tuple(c.refs)
        if k not in seen:
            seen.add(k); uniq.append(c)
    return uniq


def fitted_rel_change(values: list[float]) -> float:
    """Relative change over the series from a least-squares line through ALL points (not first vs last), as a
    fraction of the series mean. Robust to single-point noise and rounding steps (creatinine 0.9 <-> 1.0)."""
    n = len(values)
    if n < 2:
        return 0.0
    if n == 2:
        a, b = values
        return (b - a) / abs(a) if a else 0.0
    xs = range(n)
    mx, my = (n - 1) / 2, sum(values) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, values)) / sxx
    return slope * (n - 1) / abs(my) if my else 0.0


def reporting_step(values: list[float]) -> float:
    """Finest reporting resolution in the series (1.0 / 0.9 -> 0.1; 52 / 49.5 -> 0.1; 120 / 118 -> 1)."""
    decimals = 0
    for v in values:
        s = f"{round(v, 6):.6f}".rstrip("0").rstrip(".")
        decimals = max(decimals, len(s.split(".")[1]) if "." in s else 0)
    return 10.0 ** -decimals


def trend_direction(values: list[float]) -> str:
    rel = fitted_rel_change(values)
    if values and abs(rel * (sum(values) / len(values))) < reporting_step(values):
        return "stable"            # the whole fitted change is smaller than one reporting step: not a trend
    if rel > TREND_REL_CHANGE:
        return "increasing"
    if rel < -TREND_REL_CHANGE:
        return "decreasing"
    return "stable"


def recent_series(rec: PatientRecord, days: int = LAB_WINDOW_DAYS):
    cutoff = rec.latest_date() - timedelta(days=days)
    out = {}
    for code, pts in rec.lab_series().items():
        recent = [p for p in pts if (d := parse_date(p.when)) and d >= cutoff]
        if recent:
            out[code] = recent
    return out


def key_facts(rec: PatientRecord) -> list[Fact]:
    facts: list[Fact] = []

    allergies = [a for a in rec.of_type("AllergyIntolerance") if rec.is_active(a)]
    for a in allergies:
        facts.append(Fact(f"allergy:{a['id']}", "allergy", concept_text(a.get("code")), [ref_of(a)], 3.0))
    if not allergies:
        facts.append(Fact("no_allergy_record", "no_allergy_record", "No allergy record found", [], 3.0))

    if (rec.meta.get("scope") or {}).get("kind") == "admission":
        # One fact per distinct drug ordered during the stay (any status); any of its orders covers it.
        # High-risk drugs carry the weight: an admission has a median of 38 distinct drugs and a summary must select.
        by_name: dict[str, list[dict]] = {}
        for m in rec.of_type("MedicationRequest", "MedicationStatement"):
            by_name.setdefault(rec.med_name(m), []).append(m)
        for name, ms in sorted(by_name.items()):
            facts.append(Fact(f"med:{ms[0]['id']}", "medication", name, [ref_of(m) for m in ms],
                              3.0 if clinical.is_high_risk_med(name) else 1.0))
    else:
        for m in rec.of_type("MedicationRequest", "MedicationStatement"):
            if not rec.is_active(m):
                continue
            name = rec.med_name(m)
            facts.append(Fact(f"med:{m['id']}", "medication", name, [ref_of(m)],
                              3.0 if clinical.is_high_risk_med(name) else 2.0))

    for c in rec.of_type("Condition"):
        disp = concept_text(c.get("code"))
        if rec.is_active(c) and not clinical.is_social_condition(disp):
            facts.append(Fact(f"problem:{c['id']}", "problem", disp, [ref_of(c)], 2.0))

    for code, pts in recent_series(rec).items():
        latest = pts[-1]
        flag = clinical.lab_flag(latest)
        name = clinical.short_lab_name(latest)
        if flag:
            facts.append(Fact(f"lab:{code}", "abnormal_lab", f"{name} {latest.value:g} {latest.unit} ({flag})",
                              [latest.ref], 2.0, {"code": code, "value": latest.value, "flag": flag}))
        if len(pts) >= 2:
            direction = trend_direction([p.value for p in pts])
            if direction != "stable" and (flag or any(clinical.lab_flag(p) for p in pts)):
                facts.append(Fact(f"trend:{code}", "lab_trend", f"{name} {direction}",
                                  [p.ref for p in pts], 1.0, {"code": code, "direction": direction}))
    return facts


def safety_checks(rec: PatientRecord, quarantined: dict[str, list[str]] | None = None,
                  note_texts: dict[str, str] | None = None) -> list[SafetyCheck]:
    checks: list[SafetyCheck] = []
    active_meds = [m for m in rec.of_type("MedicationRequest", "MedicationStatement") if rec.is_active(m)]
    by_ing: dict[str, list[dict]] = {}
    for m in active_meds:
        by_ing.setdefault(clinical.ingredient_key(rec.med_name(m)), []).append(m)
    for ing, ms in by_ing.items():
        if ing and len(ms) > 1:
            names = sorted({rec.med_name(m) for m in ms})
            checks.append(SafetyCheck("duplicate_medication",
                                      f"{len(ms)} active orders for '{ing}': " + "; ".join(names),
                                      [ref_of(m) for m in ms]))
    allergies = [a for a in rec.of_type("AllergyIntolerance") if rec.is_active(a)]
    for a in allergies:
        sub = concept_text(a.get("code"))
        for m in active_meds:
            if clinical.allergy_conflicts(sub, rec.med_name(m)):
                checks.append(SafetyCheck("allergy_conflict",
                                          f"Active order '{rec.med_name(m)}' may conflict with recorded allergy '{concept_text(a.get('code'))}'",
                                          [ref_of(a), ref_of(m)]))
    if not allergies:
        checks.append(SafetyCheck("no_allergy_record",
                                  "No AllergyIntolerance resources in the record. Absence of a record is not absence of allergy.", []))
    for code, pts in recent_series(rec, 30).items():
        p = pts[-1]
        lo, hi, _, _ = clinical.REF_RANGES.get(p.code, (p.low, p.high, "", ""))
        if (hi is not None and p.value > hi * 1.5) or (lo is not None and p.value < lo * 0.67):
            sev = max(p.value / hi if hi else 0.0, (lo / p.value) if (lo and p.value > 0) else (9.9 if lo else 0.0))
            checks.append(SafetyCheck("critical_lab", f"{clinical.short_lab_name(p)} {p.value:g} {p.unit} on "
                                      f"{(p.when or '')[:10]} is far outside range", [p.ref], round(sev, 2)))
    for ref, spans in (quarantined or {}).items():
        checks.append(SafetyCheck("quarantined_text",
                                  f"{len(spans)} instruction-like span(s) in {ref} were withheld from the model", [ref]))
    if note_texts:
        checks += note_conflicts(rec, note_texts)
    return checks


def latest_encounters(rec: PatientRecord, n: int = 3) -> list[dict]:
    encs = rec.of_type("Encounter")
    encs.sort(key=lambda e: resource_date(e) or "", reverse=True)
    return encs[:n]


KIND_FOR_FACT = {"allergy": {"allergy"}, "medication": {"medication", "medication_issue"}, "problem": {"condition"},
                 "abnormal_lab": {"lab_value", "lab_trend"}, "lab_trend": {"lab_trend"}}


def covered(f: Fact, kept) -> bool:
    """Is fact f expressed by any kept claim (Verdict list)? Trend facts need the latest value cited."""
    if f.kind == "no_allergy_record":
        return any(v.claim.kind == "absence" and v.claim.absent_type == "AllergyIntolerance" for v in kept)
    for v in kept:
        if v.claim.kind not in KIND_FOR_FACT[f.kind]:
            continue
        refs = set(v.resolved_refs)
        if (f.kind == "lab_trend" and f.refs[-1] in refs) or (f.kind != "lab_trend" and refs & set(f.refs)):
            return True
    return False
