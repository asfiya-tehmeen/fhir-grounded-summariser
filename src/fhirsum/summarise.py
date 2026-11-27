"""Pipeline: record -> sanitise notes -> prompt -> claims -> verify -> one repair round -> keep/drop
-> completeness backfill (code adds any missed safety-critical fact, labelled as code-generated)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from . import prompts
from .claims import Claim, Verdict
from .facts import Fact, SafetyCheck, covered, key_facts, safety_checks
from .llm import LLM, CacheMiss, parse_json
from .record import PatientRecord, ref_of
from .sanitize import quarantine
from .verifier import Verifier

BACKFILL_MIN_WEIGHT = 3.0   # allergies, absence of allergy record, high-risk medications


@dataclass
class Summary:
    summary_type: str
    kept: list[Verdict]                     # everything shown (model claims + backfilled)
    dropped: list[Verdict]
    checks: list[SafetyCheck]
    raw_claims: list[Claim]                 # first-pass claims, before verification
    first_pass: list[Verdict] = field(default_factory=list)
    quarantined: dict[str, list[str]] = field(default_factory=dict)
    malformed: int = 0
    latency_s: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    mode: str = "verify"
    backfilled_ids: set[str] = field(default_factory=set)
    repair_skipped: bool = False            # offline re-score: repair answer not cached, repair round not run

    @property
    def model_kept(self) -> list[Verdict]:
        return [v for v in self.kept if v.claim.id not in self.backfilled_ids]


def prepare_notes(rec: PatientRecord, sanitise: bool = True):
    notes, quarantined = {}, {}
    for d in rec.of_type("DocumentReference"):
        ref = ref_of(d)
        txt = rec.note_text(d)
        if sanitise:
            txt, spans = quarantine(txt)
            if spans:
                quarantined[ref] = spans
        notes[ref] = txt
    return notes, quarantined


def _parse_claims(text: str) -> tuple[list[Claim], int]:
    try:
        data = parse_json(text)
    except Exception:
        return [], 1
    out, bad = [], 0
    for c in data.get("claims", []) if isinstance(data, dict) else []:
        try:
            extra = {k: c.pop(k) for k in list(c) if k.startswith("_")}
            cl = Claim(**c)
            cl._extra = extra
            out.append(cl)
        except (ValidationError, TypeError, AttributeError):
            bad += 1
    return out, bad


def _dump(c: Claim) -> dict:
    d = c.model_dump(exclude_none=True)
    d.update(c._extra)
    return d


def _dedupe(vs: list[Verdict]) -> list[Verdict]:
    seen, out = set(), []
    for v in vs:
        # one trend claim per series (keyed by the latest value it cites); exact-ref key for everything else
        if v.claim.kind == "lab_trend" and v.resolved_refs:
            k = ("lab_trend", v.resolved_refs[-1])
        else:
            k = (v.claim.kind, tuple(sorted(v.resolved_refs)), v.claim.absent_type, v.claim.trend)
        if k not in seen:
            seen.add(k); out.append(v)
    return out


def fact_claim(rec: PatientRecord, f: Fact, summary_type: str = "handoff") -> Claim | None:
    """Deterministic claim for one key fact (used by the template baseline and the backfill)."""
    h = rec.ref_to_handle
    hs = [h[r] for r in f.refs if r in h]
    sec = prompts.SECTIONS.get(summary_type, prompts.SECTIONS["handoff"])
    pick = lambda *names: next((s for s in sec if s in names), names[0])
    if f.kind == "allergy":
        return Claim(section=pick("Allergies"), kind="allergy", text=f"Allergy: {f.label}.", refs=hs)
    if f.kind == "no_allergy_record":
        return Claim(section=pick("Allergies"), kind="absence", text="No allergy records found.", absent_type="AllergyIntolerance")
    if f.kind == "medication":
        active = all(rec.is_active(rec.resources[r]) for r in f.refs)   # admission orders are completed/stopped
        return Claim(section=pick("Medications", "Active medications", "Your medicines"), kind="medication",
                     text=f"{f.label}.", refs=hs[-1:] if not active else hs, status="active" if active else None)
    if f.kind == "problem":
        explicit = bool(rec.resources[f.refs[0]].get("clinicalStatus"))   # MIMIC diagnoses carry no status
        return Claim(section=pick("Active problems", "Your health conditions"), kind="condition", text=f"{f.label}.",
                     refs=hs, status="active" if explicit else None)
    if f.kind == "abnormal_lab":
        p = next(p for p in rec.lab_points() if p.ref == f.refs[0] and p.code == f.detail["code"])
        return Claim(section=pick("Recent labs and trends", "Your recent test results"), kind="lab_value",
                     text=f"{p.name}: {p.value:g} {p.unit} ({f.detail['flag']}).", refs=hs[:1],
                     value=p.value, unit=p.unit, date=(p.when or "")[:10])
    if f.kind == "lab_trend":
        return Claim(section=pick("Recent labs and trends", "Your recent test results"), kind="lab_trend",
                     text=f"{f.label} over the last year.", refs=hs, trend=f.detail["direction"])
    return None


def summarise(rec: PatientRecord, llm: LLM, summary_type: str = "handoff", sanitise: bool = True,
              verify: bool = True, repair: bool = True, backfill: bool = True, prompt: str = "v1") -> Summary:
    system = prompts.SYSTEMS[prompt]
    ti, to, l0 = llm.tokens_in, llm.tokens_out, llm.latency
    notes, quarantined = prepare_notes(rec, sanitise)
    checks = safety_checks(rec, quarantined, notes)
    ver = Verifier(rec, notes, checks, lay_ok=summary_type == "patient")
    user = prompts.build_user_prompt(rec, notes, summary_type)

    claims, malformed = _parse_claims(llm.complete(system, user))
    for i, c in enumerate(claims):
        c.id = f"c{i + 1}"
    first = ver.verify_all(claims)
    s = Summary(summary_type, first, [], checks, claims, first, quarantined, malformed, mode="no_verify")

    if verify:
        s.mode = "verify"
        kept = _dedupe([v for v in first if v.ok])
        rejected = [v for v in first if not v.ok]
        repaired_bad: list[Verdict] = []
        if repair and rejected:
            try:
                fix_text = llm.complete(system, prompts.repair_prompt(
                    [(_dump(v.claim), v.reasons) for v in rejected]) + "\n\n" + user)
            except CacheMiss:
                fix_text, s.repair_skipped = '{"claims": []}', True
            fixed, bad2 = _parse_claims(fix_text)
            s.malformed += bad2
            for j, c in enumerate(fixed):
                c.id = f"r{j + 1}"
            fixed_v = ver.verify_all(fixed)
            kept = _dedupe(kept + [v for v in fixed_v if v.ok])
            repaired_bad = [v for v in fixed_v if not v.ok]
        s.kept, s.dropped = kept, rejected + repaired_bad
        if backfill:
            n = 0
            for f in key_facts(rec):
                if f.weight >= BACKFILL_MIN_WEIGHT and not covered(f, s.kept):
                    c = fact_claim(rec, f, summary_type)
                    if c is None:
                        continue
                    n += 1
                    c.id = f"b{n}"
                    v = ver.verify(c)
                    if v.ok:
                        s.kept.append(v); s.backfilled_ids.add(c.id)
    s.latency_s = round(llm.latency - l0, 2)          # model time, including when replayed from cache
    s.tokens_in, s.tokens_out = llm.tokens_in - ti, llm.tokens_out - to
    return s


def template_summary(rec: PatientRecord, summary_type: str = "handoff") -> Summary:
    """Baseline: code-only summary straight from the key facts (no LLM). The recall ceiling and the
    'is an LLM even needed?' comparison."""
    t0 = time.time()
    notes, quarantined = prepare_notes(rec)
    checks = safety_checks(rec, quarantined)
    ver = Verifier(rec, notes, checks)
    claims: list[Claim] = []
    if rec.age() is not None:
        claims.append(Claim(section="Patient", kind="demographic",
                            text=f"{rec.age()}-year-old {rec.patient.get('gender', '')} patient.", refs=["PT"], value=rec.age()))
    claims += [c for f in key_facts(rec) if (c := fact_claim(rec, f, summary_type))]
    for i, c in enumerate(claims):
        c.id = f"t{i + 1}"
    vs = ver.verify_all(claims)
    return Summary(summary_type, [v for v in vs if v.ok], [v for v in vs if not v.ok], checks, claims, vs,
                   quarantined, 0, round(time.time() - t0, 3), 0, 0, "template")
