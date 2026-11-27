"""Admission scoping for long real records (MIMIC-IV demo on FHIR).

A whole MIMIC patient is years of admissions (median prompt 33K chars, max 291K). A summary is written for one
hospital stay, so we cut the record to the latest admission: the Encounter that has a `hospitalization` block, the
diagnoses and medication orders that reference it, observations linked to it or timed inside its period, and
patient-level resources (Patient, allergies). The scope is stored in `rec.meta["scope"]`, which facts.py and
prompts.py read: medications become "ordered during this admission" (never "active"), and the prompt groups
orders by drug and lab values by series to fit a free-tier token budget."""
from __future__ import annotations

from .record import PatientRecord, ref_of, resource_date


def admissions(rec: PatientRecord) -> list[dict]:
    adm = [e for e in rec.of_type("Encounter") if e.get("hospitalization")]
    return sorted(adm, key=lambda e: resource_date(e) or "")


def scope_admission(rec: PatientRecord, encounter_ref: str | None = None) -> PatientRecord | None:
    adm = admissions(rec)
    if not adm:
        return None
    enc = rec.resources.get(encounter_ref) if encounter_ref else adm[-1]
    if enc is None:
        return None
    eref = ref_of(enc)
    period = enc.get("period") or {}
    start, end = (period.get("start") or "")[:19], (period.get("end") or "9999")[:19]

    def linked(r: dict) -> bool:
        return (r.get("encounter") or {}).get("reference") == eref

    def in_period(r: dict) -> bool:
        d = (resource_date(r) or "")[:19]
        return bool(d) and start <= d <= end

    keep: list[dict] = [rec.patient, enc] if rec.patient else [enc]
    keep += rec.of_type("AllergyIntolerance")
    keep += [c for c in rec.of_type("Condition") if linked(c)]
    meds = [m for m in rec.of_type("MedicationRequest", "MedicationStatement") if linked(m)]
    keep += meds
    keep += [o for o in rec.of_type("Observation") if linked(o) or in_period(o)]
    keep += [d for d in rec.of_type("DocumentReference") if linked(d) or in_period(d)]
    med_refs = {(m.get("medicationReference") or {}).get("reference") for m in meds}
    for x in list(med_refs):                                  # medication mixes reference their ingredients
        for ing in (rec.resources.get(x) or {}).get("ingredient", []) or []:
            med_refs.add((ing.get("itemReference") or {}).get("reference"))
    keep += [rec.resources[x] for x in med_refs if x in rec.resources]
    meta = dict(rec.meta, scope={"kind": "admission", "encounter": eref, "start": start, "end": end,
                                 "admission_index": adm.index(enc) + 1, "n_admissions": len(adm)})
    return PatientRecord.from_resources(keep, source=rec.source, meta=meta)


def is_admission_scope(rec: PatientRecord) -> bool:
    return (rec.meta.get("scope") or {}).get("kind") == "admission"
