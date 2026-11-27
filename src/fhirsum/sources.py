"""Data sources: FHIR servers (HAPI / SMART sandbox), Synthea output, MIMIC-IV demo on FHIR (ndjson)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import httpx

from .record import PatientRecord

# High-volume ICU streams and non-clinical resources: skipped so a bundle stays summarisable.
MIMIC_SKIP = ("Chartevents", "Outputevents", "Datetimeevents", "Micro", "Specimen", "Location", "Organization",
              "MedicationAdministration", "MedicationDispense", "EncounterICU", "ProcedureICU")
FETCH_TYPES = ["Condition", "MedicationRequest", "AllergyIntolerance", "Observation", "Encounter", "DocumentReference"]


def fetch_patient(base: str, patient_id: str, token: str | None = None, max_pages: int = 20) -> PatientRecord:
    """Fetch one patient from a FHIR R4 server. Tries $everything, falls back to per-type searches."""
    h = {"Accept": "application/fhir+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    base = base.rstrip("/")
    with httpx.Client(timeout=60, headers=h) as c:
        res: list[dict] = []

        def page_through(url, params=None):
            n = 0
            while url and n < max_pages:
                r = c.get(url, params=params); r.raise_for_status(); b = r.json()
                res.extend(e["resource"] for e in b.get("entry", []) if "resource" in e)
                url = next((l["url"] for l in b.get("link", []) if l.get("relation") == "next"), None)
                params = None; n += 1

        try:
            page_through(f"{base}/Patient/{patient_id}/$everything", {"_count": 500})
        except httpx.HTTPError:
            res.clear()
            res.append(c.get(f"{base}/Patient/{patient_id}").raise_for_status().json())
            for t in FETCH_TYPES:
                key = "patient"
                page_through(f"{base}/{t}", {key: patient_id, "_count": 200})
    return PatientRecord.from_resources(res, source="server")


def load_synthea_dir(d: str | Path) -> list[Path]:
    """Synthea writes one transaction bundle per patient; skip hospital/practitioner bundles."""
    return sorted(p for p in Path(d).glob("*.json") if not p.name.startswith(("hospitalInformation", "practitionerInformation")))


def split_mimic(ndjson_dir: str | Path, out_dir: str | Path, max_patients: int | None = None) -> list[Path]:
    """MIMIC-IV demo on FHIR ships one ndjson.gz per resource profile. Group resources per patient into
    collection bundles. Medication resources (no subject) are attached to the bundles that reference them."""
    ndjson_dir, out_dir = Path(ndjson_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    per_patient: dict[str, list[dict]] = {}
    shared: dict[str, dict] = {}
    for f in sorted(ndjson_dir.glob("*.ndjson*")):
        if any(x in f.name for x in MIMIC_SKIP):
            continue
        opener = gzip.open if f.suffix == ".gz" else open
        with opener(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                rt = r["resourceType"]
                if rt == "Patient":
                    per_patient.setdefault(r["id"], []).append(r); continue
                subj = (r.get("subject") or r.get("patient") or {}).get("reference", "")
                if subj.startswith("Patient/"):
                    per_patient.setdefault(subj.split("/", 1)[1], []).append(r)
                elif rt in ("Medication",):
                    shared[f"Medication/{r['id']}"] = r
    paths = []
    for i, (pid, rs) in enumerate(sorted(per_patient.items())):
        if max_patients and i >= max_patients:
            break
        refs = {(r.get("medicationReference") or {}).get("reference") for r in rs}
        rs = rs + [shared[x] for x in refs if x in shared]
        rec = PatientRecord.from_resources(rs, source="mimic")
        p = out_dir / f"mimic_{pid}.json"
        p.write_text(json.dumps(rec.to_bundle()), encoding="utf-8")
        paths.append(p)
    return paths


def upload_to_hapi(base: str, bundle_path: Path):
    """POST a Synthea transaction bundle to a local HAPI server."""
    b = json.loads(bundle_path.read_text(encoding="utf-8"))
    if b.get("type") != "transaction":
        b = {"resourceType": "Bundle", "type": "transaction",
             "entry": [{"resource": e["resource"], "request": {"method": "PUT",
                        "url": f"{e['resource']['resourceType']}/{e['resource']['id']}"}} for e in b.get("entry", [])]}
    r = httpx.post(base.rstrip("/"), json=b, timeout=300, headers={"Content-Type": "application/fhir+json"})
    r.raise_for_status()
    return r.status_code
