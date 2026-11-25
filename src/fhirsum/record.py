"""PatientRecord: an indexed view over a patient's FHIR R4 resources.

Works with Synthea transaction bundles, MIMIC-IV-on-FHIR resources, SMART sandbox searches and
HAPI `$everything` output. Every resource gets a short, typed *handle* (MED-3, LAB-12, ...) that the
LLM cites; handles map back to the real `Type/id` reference so citations stay exact.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

HANDLE_PREFIX = {
    "Patient": "PT", "Condition": "PROB", "MedicationRequest": "MED", "MedicationStatement": "MED",
    "AllergyIntolerance": "ALG", "Observation": "LAB", "Encounter": "ENC", "DocumentReference": "NOTE",
    "DiagnosticReport": "RPT", "Immunization": "IMM", "Procedure": "PROC",
}
# Resource types the summariser shows to the model; everything else is kept for lookups only.
SUMMARY_TYPES = set(HANDLE_PREFIX)


def ref_of(res: dict) -> str:
    return f"{res['resourceType']}/{res.get('id', '?')}"


def first_coding(cc: dict | None) -> dict:
    if not cc:
        return {}
    for c in cc.get("coding", []) or []:
        return c
    return {}


def concept_text(cc: dict | None) -> str:
    if not cc:
        return ""
    if cc.get("text"):
        return cc["text"]
    c = first_coding(cc)
    return c.get("display") or c.get("code") or ""


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None


def resource_date(res: dict) -> str | None:
    """Best clinical date for a resource, ISO string (day precision kept as given)."""
    rt = res.get("resourceType")
    keys = {
        "Observation": ["effectiveDateTime", "issued"],
        "Condition": ["onsetDateTime", "recordedDate"],
        "MedicationRequest": ["authoredOn"],
        "MedicationStatement": ["effectiveDateTime", "dateAsserted"],
        "AllergyIntolerance": ["recordedDate", "onsetDateTime"],
        "Encounter": [],
        "DocumentReference": ["date"],
        "DiagnosticReport": ["effectiveDateTime", "issued"],
        "Immunization": ["occurrenceDateTime"],
        "Procedure": ["performedDateTime"],
        "Patient": ["birthDate"],
    }.get(rt, [])
    for k in keys:
        if res.get(k):
            return res[k]
    for k in ("period", "effectivePeriod", "performedPeriod"):
        if isinstance(res.get(k), dict) and res[k].get("start"):
            return res[k]["start"]
    return None


def status_code(res: dict, key: str) -> str:
    v = res.get(key)
    if isinstance(v, dict):
        return first_coding(v).get("code", "")
    return v or ""


@dataclass
class LabPoint:
    handle: str
    ref: str
    code: str          # LOINC (or local) code; component code for BP etc.
    name: str
    value: float
    unit: str
    when: str | None
    low: float | None = None
    high: float | None = None
    interp: str = ""   # H / L / N / HH / LL / A from Observation.interpretation


@dataclass
class PatientRecord:
    resources: dict[str, dict]                      # ref -> resource
    handles: dict[str, str] = field(default_factory=dict)   # handle -> ref
    ref_to_handle: dict[str, str] = field(default_factory=dict)
    source: str = "unknown"                         # synthea | mimic | sandbox | generated
    meta: dict = field(default_factory=dict)        # planted traps, ground truth, etc.

    # ---- construction -------------------------------------------------------------
    @classmethod
    def from_resources(cls, resources: list[dict], source="unknown", meta=None) -> "PatientRecord":
        idx: dict[str, dict] = {}
        for r in resources:
            if not isinstance(r, dict) or "resourceType" not in r:
                continue
            idx[ref_of(r)] = r
        rec = cls(resources=idx, source=source, meta=meta or {})
        rec._assign_handles()
        return rec

    @classmethod
    def from_bundle(cls, bundle: dict, source="unknown") -> "PatientRecord":
        res = [e["resource"] for e in bundle.get("entry", []) if "resource" in e]
        meta = {}
        for ext in bundle.get("meta", {}).get("extension", []) or []:
            if ext.get("url") == "urn:fhirsum:meta":
                meta = json.loads(ext.get("valueString", "{}"))
        return cls.from_resources(res, source=bundle.get("_source", source), meta=meta)

    @classmethod
    def from_file(cls, path: str | Path) -> "PatientRecord":
        p = Path(path)
        b = json.loads(p.read_text(encoding="utf-8"))
        src = "synthea" if "synthea" in str(p).lower() else ("mimic" if "mimic" in str(p).lower() else "generated")
        rec = cls.from_bundle(b, source=src)
        rec.meta.setdefault("file", str(p))
        return rec

    def to_bundle(self) -> dict:
        b = {"resourceType": "Bundle", "type": "collection",
             "entry": [{"fullUrl": ref, "resource": r} for ref, r in self.resources.items()]}
        if self.meta:
            b["meta"] = {"extension": [{"url": "urn:fhirsum:meta", "valueString": json.dumps(self.meta)}]}
        b["_source"] = self.source
        return b

    def _assign_handles(self):
        counters: dict[str, int] = {}
        self.handles.clear(); self.ref_to_handle.clear()
        # stable order: by type, then date, then id -> handles are reproducible across runs
        items = sorted(self.resources.items(),
                       key=lambda kv: (kv[1]["resourceType"], resource_date(kv[1]) or "", kv[0]))
        for ref, r in items:
            pre = HANDLE_PREFIX.get(r["resourceType"])
            if not pre:
                continue
            if pre == "PT":
                h = "PT"
            else:
                counters[pre] = counters.get(pre, 0) + 1
                h = f"{pre}-{counters[pre]}"
            self.handles[h] = ref
            self.ref_to_handle[ref] = h

    # ---- accessors ----------------------------------------------------------------
    def of_type(self, *types: str) -> list[dict]:
        return [r for r in self.resources.values() if r["resourceType"] in types]

    def get(self, ref_or_handle: str) -> dict | None:
        ref = self.handles.get(ref_or_handle, ref_or_handle)
        return self.resources.get(ref)

    def resolve_handle(self, h: str) -> str | None:
        if h in self.handles:
            return self.handles[h]
        return h if h in self.resources else None

    @property
    def patient(self) -> dict:
        pts = self.of_type("Patient")
        return pts[0] if pts else {}

    def latest_date(self) -> date:
        """Reference 'today' for the record = latest clinical date in it (records are historical)."""
        ds = [parse_date(resource_date(r)) for r in self.resources.values()]
        ds = [d for d in ds if d]
        return max(ds) if ds else date.today()

    def age(self) -> int | None:
        bd = parse_date(self.patient.get("birthDate"))
        if not bd:
            return None
        ref = parse_date(self.patient.get("deceasedDateTime")) or self.latest_date()
        return ref.year - bd.year - ((ref.month, ref.day) < (bd.month, bd.day))

    def med_name(self, mr: dict) -> str:
        if mr.get("medicationCodeableConcept"):
            return concept_text(mr["medicationCodeableConcept"])
        ref = (mr.get("medicationReference") or {}).get("reference", "")
        med = self.resources.get(ref) or self.resources.get(ref.replace("urn:uuid:", "Medication/"))
        return concept_text((med or {}).get("code")) or ref

    def med_rxcui(self, mr: dict) -> str | None:
        cc = mr.get("medicationCodeableConcept")
        if not cc:
            ref = (mr.get("medicationReference") or {}).get("reference", "")
            cc = (self.resources.get(ref) or {}).get("code")
        for c in (cc or {}).get("coding", []) or []:
            if "rxnorm" in (c.get("system") or "").lower():
                return c.get("code")
        return None

    def is_active(self, r: dict) -> bool:
        rt = r["resourceType"]
        if rt == "Condition":
            return status_code(r, "clinicalStatus") in ("active", "recurrence", "relapse", "")
        if rt in ("MedicationRequest", "MedicationStatement"):
            return (r.get("status") or "") in ("active", "on-hold", "intended")
        if rt == "AllergyIntolerance":
            return status_code(r, "clinicalStatus") in ("active", "") and \
                status_code(r, "verificationStatus") != "entered-in-error"
        return True

    def note_text(self, doc: dict) -> str:
        out = []
        for c in doc.get("content", []) or []:
            att = c.get("attachment", {})
            if att.get("data"):
                try:
                    out.append(base64.b64decode(att["data"]).decode("utf-8", "replace"))
                except Exception:
                    pass
            elif att.get("_text"):
                out.append(att["_text"])
        if not out and doc.get("description"):
            out.append(doc["description"])
        return "\n".join(out)

    def lab_points(self) -> list[LabPoint]:
        pts: list[LabPoint] = []
        for r in self.of_type("Observation"):
            if status_code(r, "status") in ("entered-in-error", "cancelled"):
                continue
            h = self.ref_to_handle.get(ref_of(r), "")
            when = resource_date(r)
            base_name = concept_text(r.get("code"))
            base_code = first_coding(r.get("code")).get("code", base_name)
            entries = []
            if "valueQuantity" in r:
                entries.append((base_code, base_name, r["valueQuantity"], r.get("referenceRange"), r.get("interpretation")))
            for comp in r.get("component", []) or []:
                if "valueQuantity" in comp:
                    entries.append((first_coding(comp.get("code")).get("code", ""), concept_text(comp.get("code")),
                                    comp["valueQuantity"], comp.get("referenceRange"), comp.get("interpretation")))
            for code, name, vq, rr, interp in entries:
                if vq.get("value") is None:
                    continue
                low = high = None
                if rr:
                    low = (rr[0].get("low") or {}).get("value")
                    high = (rr[0].get("high") or {}).get("value")
                ic = first_coding(interp[0]).get("code", "") if interp else ""
                pts.append(LabPoint(h, ref_of(r), code, name, float(vq["value"]),
                                    vq.get("unit") or vq.get("code") or "", when, low, high, ic))
        return pts

    def lab_series(self) -> dict[str, list[LabPoint]]:
        series: dict[str, list[LabPoint]] = {}
        for p in self.lab_points():
            series.setdefault(p.code, []).append(p)
        for v in series.values():
            v.sort(key=lambda p: p.when or "")
        return series
