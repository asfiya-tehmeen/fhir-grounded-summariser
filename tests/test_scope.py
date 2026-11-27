"""Admission scoping on a small MIMIC-shaped record (no real MIMIC data needed)."""
from fhirsum.claims import Claim
from fhirsum.facts import key_facts
from fhirsum.mock_mimic import mimic_like_record
from fhirsum.prompts import build_user_prompt
from fhirsum.scope import scope_admission
from fhirsum.summarise import prepare_notes, template_summary
from fhirsum.verifier import Verifier


def test_scope_keeps_only_latest_admission():
    rec = mimic_like_record()
    s = scope_admission(rec)
    assert s.meta["scope"]["encounter"] == "Encounter/adm2"
    assert {c["id"] for c in s.of_type("Condition")} == {"c2a", "c2b"}          # adm1 diagnosis excluded
    assert {m["id"] for m in s.of_type("MedicationRequest")} == {"mr2a", "mr2b", "mr2c", "mr2d"}
    assert all(o["id"].startswith("o2") for o in s.of_type("Observation"))      # linked or inside the period


def test_mimic_medication_names_from_identifier_and_mix():
    s = scope_admission(mimic_like_record())
    names = {m["id"]: s.med_name(m) for m in s.of_type("MedicationRequest")}
    assert names["mr2a"] == "Heparin"                                           # identifier, not the NDC code
    assert names["mr2c"] == "Calcium Gluconate + 0.9% Sodium Chloride"          # mix -> ingredients


def test_admission_facts_group_orders_and_weight_high_risk():
    s = scope_admission(mimic_like_record())
    meds = {f.label: f for f in key_facts(s) if f.kind == "medication"}
    assert len(meds["Heparin"].refs) == 2 and meds["Heparin"].weight == 3.0    # two orders, one fact
    assert meds["Calcium Gluconate + 0.9% Sodium Chloride"].weight == 1.0


def test_admission_prompt_is_grouped_and_never_says_active():
    s = scope_admission(mimic_like_record())
    u = build_user_prompt(s, prepare_notes(s)[0], "handoff")
    assert "ORDERED DURING THIS STAY" in u and "| Heparin | x2 |" in u
    assert "never as current or active" in u
    assert "clinicalStatus=active" not in u


def test_template_on_admission_passes_verifier_and_completed_order_is_not_active():
    s = scope_admission(mimic_like_record())
    t = template_summary(s)
    assert not t.dropped, [(v.claim.text, v.reasons) for v in t.dropped]
    h = next(h for h, r in s.handles.items() if r == "MedicationRequest/mr2b")
    v = Verifier(s).verify(Claim(kind="medication", text="Heparin infusion.", refs=[h], status="active"))
    assert any(r.startswith("status_mismatch") for r in v.reasons)


def test_number_in_mimic_drug_name_is_supported():
    s = scope_admission(mimic_like_record())
    h = next(h for h, r in s.handles.items() if r == "MedicationRequest/mr2d")
    v = Verifier(s).verify(Claim(kind="medication", text="Albumin 25% (12.5g / 50mL) given.", refs=[h]))
    assert v.ok, v.reasons
