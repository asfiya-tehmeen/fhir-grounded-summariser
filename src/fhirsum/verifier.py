"""Deterministic claim verifier. Every check is plain code against the FHIR record; nothing here calls
a model. Each failure carries a machine-readable reason so it can be fed back for one repair round
and counted in the evaluation."""
from __future__ import annotations

import re

from . import clinical
from .claims import Claim, Verdict
from .facts import SafetyCheck, trend_direction
from .record import PatientRecord, concept_text, ref_of, resource_date, status_code

KIND_TYPES = {
    "demographic": {"Patient"},
    "condition": {"Condition"},
    "medication": {"MedicationRequest", "MedicationStatement"},
    "allergy": {"AllergyIntolerance"},
    "lab_value": {"Observation"},
    "lab_trend": {"Observation"},
    "encounter": {"Encounter"},
    "note": {"DocumentReference"},
    "medication_issue": {"MedicationRequest", "MedicationStatement", "AllergyIntolerance"},
}
ABSENCE_TYPES = {"AllergyIntolerance", "MedicationRequest", "Condition", "Observation", "Immunization", "Procedure"}

STOP = {"with", "without", "disorder", "finding", "situation", "procedure", "oral", "tablet", "capsule",
        "injection", "solution", "product", "extended", "release", "hour", "chronic", "acute", "type",
        "substance", "allergy", "level", "mass", "volume", "serum", "plasma", "blood", "presence", "history"}
# Lay terms accepted for the patient-friendly summary (in addition to the medical term itself).
LAY = {
    "hypertension": ["blood pressure"], "hyperlipidemia": ["cholesterol"], "hypercholesterolemia": ["cholesterol"],
    "diabetes": ["blood sugar", "sugar"], "prediabetes": ["blood sugar"], "hemoglobin": ["haemoglobin"],
    "a1c": ["blood sugar", "hba1c", "a1c"], "glomerular filtration": ["gfr", "egfr", "kidney function"], "glucose": ["blood sugar", "sugar"], "creatinine": ["kidney"],
    "anemia": ["anaemia", "iron", "red blood"], "asthma": ["breathing"], "obesity": ["weight", "bmi"],
    "body mass index": ["bmi", "weight"], "systolic": ["blood pressure", "top number"],
    "diastolic": ["blood pressure", "bottom number"], "myocardial": ["heart attack"], "coronary": ["heart"],
    "osteoarthritis": ["arthritis", "joint"], "hypothyroidism": ["thyroid"], "penicillin": ["penicillin"],
}
UP_WORDS = r"\b(increas|ris(e|ing|en)|went up|going up|higher|up from|climb|worsening (hyperglyc|hyperkal))"
DOWN_WORDS = r"\b(decreas|fall|fell|falling|dropp|went down|going down|lower|down from|declin)"
_NUM = re.compile(r"(?<![\w.-])(\d+(?:\.\d+)?)(?![\w-]*-\d)")
_DATE = re.compile(r"\b(\d{4})-(\d{2})(?:-(\d{2}))?\b")


def _tokens(s: str) -> list[str]:
    s = re.sub(r"\([^)]*\)", " ", s.lower())
    return [t for t in re.findall(r"[a-z][a-z0-9]+", s) if len(t) >= 4 and t not in STOP]


def concept_matches(text: str, display: str) -> bool:
    if not display:
        return True
    t = text.lower()
    toks = _tokens(display)
    if not toks:
        return True
    for tok in toks:
        if tok in t or (len(tok) > 6 and tok[:6] in t):
            return True
    for med_term, lays in LAY.items():
        if med_term in display.lower() and any(l in t for l in lays):
            return True
    return False


TREND_NOISE_BAND = 0.02   # below 2% fitted change, a direction word is noise, not a trend


def trend_judgement(claimed: str, values: list[float]) -> tuple[str | None, bool]:
    """(error, warning) for a claimed trend label. The danger being guarded is mislabelling a REAL trend
    ('improving' while HbA1c rises 7.0 -> 9.1), so:
      - real trend (fitted change > 5% and more than one reporting step): label must match, else error
      - 2-5%: 'stable' or the matching direction are both defensible; the opposite direction is an error
      - < 2%: 'stable' is right; a direction label is noise -> kept, but counted as a warning"""
    from .facts import fitted_rel_change, trend_direction
    actual = trend_direction(values)
    if actual != "stable":
        return (None if claimed == actual else "real trend mislabelled"), False
    if claimed == "stable":
        return None, False
    rel = fitted_rel_change(values)
    if abs(rel) < TREND_NOISE_BAND:
        return None, True
    return (None if (claimed == "increasing") == (rel > 0) else "label opposite to fitted direction"), False


def _approx(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.051, 0.01 * abs(b))


def _norm_unit(u: str | None) -> str:
    """UCUM vs display spellings: 'mL/min/{1.73_m2}' == 'mL/min/1.73 m²', 'mm[Hg]' == 'mmHg'."""
    u = (u or "").lower().replace("²", "2").replace("µ", "u").replace("μ", "u")
    return re.sub(r"[\s\[\]{}_()]", "", u)


_PUNCT = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
                        "‘": "'", "’": "'", "“": '"', "”": '"', " ": " "})


def _norm_ws(s: str) -> str:
    """Whitespace, case and typographic punctuation (non-breaking hyphens, smart quotes) are not content."""
    return re.sub(r"\s+", " ", s.translate(_PUNCT)).strip().lower()


class Verifier:
    def __init__(self, rec: PatientRecord, note_texts: dict[str, str] | None = None,
                 checks: list[SafetyCheck] | None = None, lay_ok: bool = False):
        self.rec = rec
        self.note_texts = note_texts or {}     # ref -> sanitised text the model actually saw
        self.checks = checks or []
        self.lay_ok = lay_ok
        self.points_by_ref: dict[str, list] = {}
        for p in rec.lab_points():
            self.points_by_ref.setdefault(p.ref, []).append(p)
        self.series = rec.lab_series()

    # ------------------------------------------------------------------------------
    def verify(self, c: Claim) -> Verdict:
        self._warnings: list[str] = []
        reasons: list[str] = []
        refs, res = [], []
        for h in c.refs:
            r = self.rec.resolve_handle(h)
            if r is None:
                reasons.append(f"unknown_ref:{h}")
            else:
                refs.append(r); res.append(self.rec.resources[r])
        if c.kind == "absence":
            reasons += self._absence(c)
            return Verdict(claim=c, ok=not reasons, reasons=reasons, resolved_refs=refs, warnings=self._warnings)
        if not c.refs:
            reasons.append("no_citation")
        if reasons:
            return Verdict(claim=c, ok=False, reasons=reasons, resolved_refs=refs)

        allowed = KIND_TYPES[c.kind]
        bad = [r["resourceType"] for r in res if r["resourceType"] not in allowed]
        if bad:
            reasons.append(f"type_mismatch:{c.kind}<-{','.join(sorted(set(bad)))}")
            return Verdict(claim=c, ok=False, reasons=reasons, resolved_refs=refs)

        fn = getattr(self, f"_{c.kind}")
        reasons += fn(c, res)
        reasons += self._dates(c, res)
        reasons += self._numbers(c, res)
        return Verdict(claim=c, ok=not reasons, reasons=reasons, resolved_refs=refs, warnings=self._warnings)

    def verify_all(self, claims: list[Claim]) -> list[Verdict]:
        return [self.verify(c) for c in claims]

    # ---- per kind -----------------------------------------------------------------
    def _concept(self, c: Claim, display: str) -> list[str]:
        if concept_matches(c.text, display):
            return []
        return [f"concept_mismatch:'{display}'"]

    def _status(self, c: Claim, r: dict, key: str) -> list[str]:
        if not c.status:
            return []
        actual = status_code(r, key) if key != "status" else (r.get("status") or "")
        want = c.status.lower()
        active_like = {"active", "recurrence", "relapse", "on-hold", "intended"}
        if (want == "active") != (actual in active_like):
            return [f"status_mismatch:claimed {want}, record {actual or 'unknown'}"]
        return []

    def _condition(self, c, res):
        out = []
        for r in res:
            out += self._concept(c, concept_text(r.get("code")))
            out += self._status(c, r, "clinicalStatus")
        return out

    def _allergy(self, c, res):
        out = []
        for r in res:
            out += self._concept(c, concept_text(r.get("code")))
            out += self._status(c, r, "clinicalStatus")
        return out

    def _medication(self, c, res):
        out = []
        for r in res:
            out += self._concept(c, self.rec.med_name(r))
            out += self._status(c, r, "status")
        return out

    def _medication_issue(self, c, res):
        cited = {ref_of(r) for r in res}
        for chk in self.checks:
            if chk.kind in ("duplicate_medication", "allergy_conflict") and len(cited) >= 2 and cited <= set(chk.refs):
                return []
        return ["issue_not_supported: no code-detected duplicate/conflict covers these refs"]

    def _encounter(self, c, res):
        return [] if c.date else []   # date consistency handled in _dates

    def _demographic(self, c, res):
        p = res[0]
        out = []
        if isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
            age = self.rec.age()
            if age is None or abs(float(c.value) - age) > 1:
                out.append(f"value_mismatch:age claimed {c.value}, record {age}")
        elif isinstance(c.value, str) and c.value.lower() in ("male", "female", "other", "unknown"):
            if c.value.lower() != (p.get("gender") or "").lower():
                out.append(f"value_mismatch:gender claimed {c.value}, record {p.get('gender')}")
        return out

    def _points(self, res) -> list:
        pts = []
        for r in res:
            pts += self.points_by_ref.get(ref_of(r), [])
        return pts

    def _pick_code(self, c: Claim, pts) -> str | None:
        codes = {}
        for p in pts:
            codes.setdefault(p.code, []).append(p)
        if len(codes) == 1:
            return next(iter(codes))
        scored = sorted(codes, key=lambda k: (not (concept_matches(c.text, codes[k][0].name)
                                                     or concept_matches(c.text, clinical.short_lab_name(codes[k][0]))),
                                              -len(codes[k])))
        return scored[0] if scored else None

    def _lab_value(self, c, res):
        pts = self._points(res)
        if not pts:
            return ["no_numeric_value_in_cited_observation"]
        out = []
        try:
            v = float(c.value) if c.value is not None else None
        except (TypeError, ValueError):
            v = None
        if v is None:
            return ["missing_value"]
        match = [p for p in pts if _approx(v, p.value)]
        if not match:
            out.append(f"value_mismatch:claimed {c.value}, record {sorted({p.value for p in pts})}")
        else:
            p = match[0]
            if not concept_matches(c.text, p.name) and not concept_matches(c.text, clinical.short_lab_name(p)):
                out.append(f"concept_mismatch:'{p.name}'")
            if c.unit and _norm_unit(c.unit) != _norm_unit(p.unit):
                out.append(f"unit_mismatch:claimed {c.unit}, record {p.unit}")
        return out

    def _lab_trend(self, c, res):
        pts = self._points(res)
        if len({p.ref for p in pts}) < 2:
            return ["trend_needs_two_observations"]
        code = self._pick_code(c, pts)
        series_pts = sorted([p for p in pts if p.code == code], key=lambda p: p.when or "")
        if len(series_pts) < 2:
            return ["trend_needs_two_observations_same_code"]
        out = []
        if not concept_matches(c.text, series_pts[0].name) and not concept_matches(c.text, clinical.short_lab_name(series_pts[0])):
            out.append(f"concept_mismatch:'{series_pts[0].name}'")
        vals = [p.value for p in series_pts]
        actual = trend_direction(vals)
        if c.trend:
            err, warn = trend_judgement(c.trend, vals)
            if err:
                out.append(f"trend_mismatch:claimed {c.trend}, values {vals} are {actual} ({err})")
            if warn:
                self._warnings.append(f"trend_overcall:'{c.trend}' on a noise-level series {vals}")
        t = c.text.lower()
        if actual == "decreasing" and re.search(UP_WORDS, t) and not re.search(DOWN_WORDS, t):
            out.append("trend_text_mismatch:text says up, values went down")
        if actual == "increasing" and re.search(DOWN_WORDS, t) and not re.search(UP_WORDS, t):
            out.append("trend_text_mismatch:text says down, values went up")
        latest = self.series.get(code, [])[-1:]
        if latest and latest[0].ref not in {p.ref for p in series_pts}:
            out.append(f"stale_trend:latest {series_pts[0].name} ({(latest[0].when or '')[:10]}) not cited")
        return out

    def _note(self, c, res):
        if not c.quote:
            return ["note_claim_needs_quote"]
        q = _norm_ws(c.quote)
        for r in res:
            txt = _norm_ws(self.note_texts.get(ref_of(r), self.rec.note_text(r)))
            if q and q in txt:
                return []
        return ["quote_not_found_in_note"]

    def _absence(self, c: Claim) -> list[str]:
        t = c.absent_type
        if t not in ABSENCE_TYPES:
            return [f"absence_type_invalid:{t}"]
        present = [r for r in self.rec.of_type(t) if self.rec.is_active(r)]
        if t == "MedicationRequest":
            present += [r for r in self.rec.of_type("MedicationStatement") if self.rec.is_active(r)]
        if present:
            if re.search(r"\b(other|additional|further|no more)\b", c.text.lower()):
                return [f"qualified_absence:'other/additional' absence claims are not checkable on their own"]
            return [f"false_absence:{len(present)} active {t} resource(s) exist"]
        return []

    # ---- cross-cutting ------------------------------------------------------------
    def _dates(self, c: Claim, res) -> list[str]:
        rdates = [(resource_date(r) or "")[:10] for r in res]
        if c.kind == "demographic":                       # age is stated "as of" the record's reference date
            rdates.append(self.rec.latest_date().isoformat())
        rdates += [(r.get("period", {}) or {}).get("end", "")[:10] for r in res]
        out = []
        if c.date and not any(d and d.startswith(c.date[:10]) or (d and c.date.startswith(d)) for d in rdates):
            out.append(f"date_mismatch:claimed {c.date}, record {sorted(set(d for d in rdates if d))}")
        for m in _DATE.finditer(c.text):
            s = m.group(0)
            if not any(d and d.startswith(s) for d in rdates):
                out.append(f"text_date_unsupported:{s}")
        return out

    def _numbers(self, c: Claim, res) -> list[str]:
        """Every number written in the sentence must come from the cited resources (or the claim's own
        verified value). Stops 'correct fields, wrong prose'."""
        text = _DATE.sub(" ", c.text)
        allowed: list[float] = []
        if isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
            allowed.append(float(c.value))
        for p in self._points(res):
            allowed.append(p.value)
        age = self.rec.age()
        if age is not None and c.kind == "demographic":
            allowed.append(float(age))
        corpus = " ".join(json_text(r) for r in res) + " " + (c.quote or "")
        allowed += [float(x) for x in _NUM.findall(corpus)]
        for d in [(resource_date(r) or "")[:10] for r in res]:
            if d:
                allowed += [float(x) for x in d.split("-") if x.isdigit()]
        if c.kind in ("lab_trend", "medication_issue"):
            allowed.append(float(len(res)))
        bad = [n for n in _NUM.findall(text) if not any(_approx(float(n), a) for a in allowed)]
        return [f"unsupported_number:{n}" for n in bad]


def json_text(r: dict) -> str:
    """Display strings of a resource (where dose numbers like '10 MG' live)."""
    out = []
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("display", "text", "unit", "value") and isinstance(v, (str, int, float)):
                    out.append(str(v))
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk({k: v for k, v in r.items() if k not in ("id", "meta", "identifier", "subject", "encounter", "content")})
    return " ".join(out)
