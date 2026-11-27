"""A tiny record shaped like MIMIC-IV-on-FHIR (two admissions, NDC-coded Medication resources with the drug name in
an identifier, a medication mix, encounter-linked diagnoses and orders). For tests and demos without the real data."""
from __future__ import annotations

from .record import PatientRecord

NAME_SYS = "http://mimic.mit.edu/fhir/mimic/CodeSystem/mimic-medication-name"
NDC_SYS = "http://mimic.mit.edu/fhir/mimic/CodeSystem/mimic-medication-ndc"


def _med(mid, ndc, name=None, ingredients=None):
    m = {"resourceType": "Medication", "id": mid, "code": {"coding": [{"system": NDC_SYS, "code": ndc}]},
         "identifier": [{"system": NDC_SYS, "value": ndc}]}
    if name:
        m["identifier"].append({"system": NAME_SYS, "value": name})
    if ingredients:
        m["ingredient"] = [{"itemReference": {"reference": f"Medication/{i}"}} for i in ingredients]
    return m


def _enc(eid, start, end):
    return {"resourceType": "Encounter", "id": eid, "status": "finished", "class": {"code": "EMER"},
            "period": {"start": start, "end": end}, "subject": {"reference": "Patient/p1"},
            "hospitalization": {"admitSource": {"coding": [{"code": "EMERGENCY ROOM"}]},
                                "dischargeDisposition": {"coding": [{"code": "HOME"}]}}}


def _cond(cid, enc, display):
    return {"resourceType": "Condition", "id": cid, "subject": {"reference": "Patient/p1"},
            "encounter": {"reference": f"Encounter/{enc}"},
            "code": {"coding": [{"system": "icd9", "code": cid, "display": display}]},
            "category": [{"coding": [{"code": "encounter-diagnosis"}]}]}


def _mr(mid, enc, med, when, status="completed"):
    return {"resourceType": "MedicationRequest", "id": mid, "status": status, "intent": "order",
            "subject": {"reference": "Patient/p1"}, "encounter": {"reference": f"Encounter/{enc}"},
            "medicationReference": {"reference": f"Medication/{med}"}, "authoredOn": when}


def _obs(oid, enc, value, when, low=3.5, high=5.1):
    o = {"resourceType": "Observation", "id": oid, "status": "final", "subject": {"reference": "Patient/p1"},
         "code": {"coding": [{"system": "mimic-labitem", "code": "50971", "display": "Potassium"}]},
         "effectiveDateTime": when, "valueQuantity": {"value": value, "unit": "mEq/L"},
         "referenceRange": [{"low": {"value": low}, "high": {"value": high}}]}
    if enc:
        o["encounter"] = {"reference": f"Encounter/{enc}"}
    return o


def mimic_like_record() -> PatientRecord:
    res = [
        {"resourceType": "Patient", "id": "p1", "gender": "female", "birthDate": "2128-05-06"},
        _enc("adm1", "2179-01-01T10:00:00", "2179-01-04T10:00:00"),
        _enc("adm2", "2180-08-05T23:44:00", "2180-08-07T17:50:00"),
        _cond("c1a", "adm1", "Pneumonia, organism unspecified"),
        _cond("c2a", "adm2", "Hyperpotassemia"), _cond("c2b", "adm2", "Cirrhosis of liver without mention of alcohol"),
        _med("hep", "63323026201", "Heparin"), _med("cag", "61553008348", "Calcium Gluconate"),
        _med("ns", "00338004904", "0.9% Sodium Chloride"), _med("mix", "", ingredients=["cag", "ns"]),
        _med("alb", "00944049105", "Albumin 25% (12.5g / 50mL)"),
        _mr("mr1a", "adm1", "hep", "2179-01-02T08:00:00"),
        _mr("mr2a", "adm2", "hep", "2180-08-06T08:00:00"), _mr("mr2b", "adm2", "hep", "2180-08-06T20:00:00", "stopped"),
        _mr("mr2c", "adm2", "mix", "2180-08-06T09:00:00"), _mr("mr2d", "adm2", "alb", "2180-08-06T10:00:00"),
        _obs("o1a", "adm1", 4.0, "2179-01-02T06:00:00"),
        _obs("o2a", "adm2", 6.4, "2180-08-06T00:30:00"), _obs("o2b", None, 5.6, "2180-08-06T12:00:00"),
        _obs("o2c", "adm2", 4.6, "2180-08-07T06:00:00"),
    ]
    return PatientRecord.from_resources(res, source="mimic")
