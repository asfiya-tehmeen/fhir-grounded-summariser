"""Small, explicit clinical reference tables. Used only when a record does not carry its own
referenceRange / interpretation (Synthea omits them). Adult ranges; illustrative, not for care."""
from __future__ import annotations

import re

from .record import LabPoint

# LOINC -> (low, high, unit, short name). Vital signs are included because Synthea stores them as Observations.
REF_RANGES: dict[str, tuple[float | None, float | None, str, str]] = {
    "4548-4": (None, 5.7, "%", "HbA1c"),
    "2339-0": (70, 99, "mg/dL", "Glucose"),
    "2345-7": (70, 99, "mg/dL", "Glucose"),
    "2160-0": (0.6, 1.3, "mg/dL", "Creatinine"),
    "38483-4": (0.6, 1.3, "mg/dL", "Creatinine"),
    "6299-2": (7, 20, "mg/dL", "BUN"),
    "3094-0": (7, 20, "mg/dL", "BUN"),
    "33914-3": (60, None, "mL/min/1.73m2", "eGFR"),
    "2951-2": (135, 145, "mmol/L", "Sodium"),
    "2947-0": (135, 145, "mmol/L", "Sodium"),
    "2823-3": (3.5, 5.1, "mmol/L", "Potassium"),
    "6298-4": (3.5, 5.1, "mmol/L", "Potassium"),
    "2075-0": (98, 107, "mmol/L", "Chloride"),
    "2028-9": (22, 29, "mmol/L", "CO2"),
    "17861-6": (8.6, 10.3, "mg/dL", "Calcium"),
    "2093-3": (None, 200, "mg/dL", "Total cholesterol"),
    "18262-6": (None, 130, "mg/dL", "LDL"),
    "2089-1": (None, 130, "mg/dL", "LDL"),
    "2085-9": (40, None, "mg/dL", "HDL"),
    "2571-8": (None, 150, "mg/dL", "Triglycerides"),
    "718-7": (12.0, 17.5, "g/dL", "Hemoglobin"),
    "6690-2": (4.0, 11.0, "10*3/uL", "WBC"),
    "777-3": (150, 450, "10*3/uL", "Platelets"),
    "6301-6": (None, 1.1, "{INR}", "INR"),
    "34714-6": (None, 1.1, "{INR}", "INR"),
    "8480-6": (None, 139, "mm[Hg]", "Systolic BP"),
    "8462-4": (None, 89, "mm[Hg]", "Diastolic BP"),
    "8867-4": (50, 110, "/min", "Heart rate"),
    "39156-5": (18.5, 30, "kg/m2", "BMI"),
    "59408-5": (92, None, "%", "SpO2"),
    "2708-6": (92, None, "%", "SpO2"),
}

# Higher weight in key-fact recall: missing these in a handoff is more dangerous.
HIGH_RISK_MED_PATTERNS = [
    r"warfarin", r"heparin", r"enoxaparin", r"apixaban", r"rivaroxaban", r"dabigatran", r"clopidogrel",
    r"insulin", r"glipizide", r"glyburide", r"metformin",
    r"oxycodone", r"hydrocodone", r"morphine", r"fentanyl", r"tramadol", r"methadone", r"buprenorphine",
    r"digoxin", r"amiodarone", r"lithium", r"methotrexate", r"tacrolimus", r"prednisone",
]

SOCIAL_TAGS = ("(finding)", "(situation)", "(person)", "(social concept)", "(observable entity)")


def is_high_risk_med(name: str) -> bool:
    n = name.lower()
    return any(re.search(p, n) for p in HIGH_RISK_MED_PATTERNS)


def is_social_condition(display: str) -> bool:
    d = display.lower()
    return d.endswith(SOCIAL_TAGS) and not any(k in d for k in ("disorder", "disease", "pain", "injury"))


def lab_flag(p: LabPoint) -> str:
    """'H', 'L' or '' using the record's own interpretation/range first, then the built-in table."""
    if p.interp in ("H", "HH", "HU", "A", "AA", ">"):
        return "H" if p.interp != "A" else "A"
    if p.interp in ("L", "LL", "LU", "<"):
        return "L"
    low, high = p.low, p.high
    if low is None and high is None and p.code in REF_RANGES:
        low, high, _, _ = REF_RANGES[p.code]
    if high is not None and p.value > high:
        return "H"
    if low is not None and p.value < low:
        return "L"
    return ""


def short_lab_name(p: LabPoint) -> str:
    return REF_RANGES.get(p.code, (None, None, "", p.name))[3] or p.name


def ingredient_key(med_name: str) -> str:
    """Offline ingredient guess: text before the first number ('lisinopril 10 MG Oral Tablet' -> 'lisinopril').
    An RxNorm ingredient lookup (RxNav) is the planned refinement."""
    n = med_name.lower()
    n = re.sub(r"^\d+\s*(hr|ml)?\s*", "", n)
    n = re.split(r"\s\d|\[|/|,", n)[0]
    return re.sub(r"\s+(oral|injectable|topical|tablet|capsule|solution).*$", "", n).strip()


# Allergen -> drug-name patterns in the same class. Small and explicit on purpose; the RxClass API
# (rxnav.nlm.nih.gov/REST/rxclass) is the scalable replacement (see README "Next").
ALLERGY_CLASS = {
    "penicillin": [r"penicillin", r"amoxicillin", r"ampicillin", r"piperacillin", r"nafcillin", r"dicloxacillin", r"oxacillin"],
    "sulfa": [r"sulfamethoxazole", r"sulfasalazine", r"sulfadiazine"],
    "sulfamethoxazole": [r"sulfamethoxazole", r"sulfasalazine", r"sulfadiazine"],
    "cephalosporin": [r"cef", r"ceph"],
    "aspirin": [r"aspirin", r"acetylsalicylic"],
    "nsaid": [r"ibuprofen", r"naproxen", r"diclofenac", r"ketorolac", r"celecoxib"],
}


def allergy_conflicts(allergen: str, med_name: str) -> bool:
    a, m = allergen.lower(), med_name.lower()
    for key, pats in ALLERGY_CLASS.items():
        if key in a and any(re.search(p, m) for p in pats):
            return True
    toks = [t for t in re.findall(r"[a-z]{5,}", a) if t not in ("allergy", "substance", "dietary")]
    return any(t in m for t in toks)
