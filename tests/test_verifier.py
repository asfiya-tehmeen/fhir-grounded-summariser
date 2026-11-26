import pytest

from fhirsum.claims import Claim
from fhirsum.facts import key_facts, safety_checks
from fhirsum.record import PatientRecord
from fhirsum.summarise import prepare_notes
from fhirsum.synth import generate
from fhirsum.verifier import Verifier


@pytest.fixture(scope="module")
def rec():
    return generate(7, ["worsening_trend", "duplicate_med", "allergy_conflict"])


@pytest.fixture(scope="module")
def ver(rec):
    notes, q = prepare_notes(rec)
    return Verifier(rec, notes, safety_checks(rec, q))


def handle_for(rec, pred):
    for h, ref in rec.handles.items():
        if pred(rec.resources[ref]):
            return h
    raise AssertionError("no match")


def a1c_points(rec):
    return [p for p in rec.lab_series()["4548-4"]]


def test_unknown_handle_rejected(ver):
    v = ver.verify(Claim(kind="condition", text="Atrial fibrillation", refs=["PROB-999"]))
    assert not v.ok and v.reasons[0].startswith("unknown_ref")


def test_type_mismatch(rec, ver):
    med = handle_for(rec, lambda r: r["resourceType"] == "MedicationRequest")
    v = ver.verify(Claim(kind="condition", text="Hypertension", refs=[med]))
    assert any(r.startswith("type_mismatch") for r in v.reasons)


def test_condition_ok_and_concept_mismatch(rec, ver):
    h = handle_for(rec, lambda r: r["resourceType"] == "Condition" and "Diabetes" in r["code"]["text"])
    assert ver.verify(Claim(kind="condition", text="Type 2 diabetes mellitus.", refs=[h], status="active")).ok
    bad = ver.verify(Claim(kind="condition", text="Heart failure.", refs=[h]))
    assert any(r.startswith("concept_mismatch") for r in bad.reasons)


def test_status_mismatch_on_resolved_condition(rec, ver):
    h = handle_for(rec, lambda r: r["resourceType"] == "Condition" and r["clinicalStatus"]["coding"][0]["code"] == "resolved")
    disp = rec.get(h)["code"]["text"].split(" (")[0]
    v = ver.verify(Claim(kind="condition", text=f"{disp}.", refs=[h], status="active"))
    assert any(r.startswith("status_mismatch") for r in v.reasons)


def test_lab_value_exact_and_wrong(rec, ver):
    p = a1c_points(rec)[-1]
    ok = ver.verify(Claim(kind="lab_value", text=f"HbA1c {p.value} % on {p.when[:10]}.", refs=[p.handle], value=p.value, unit="%", date=p.when[:10]))
    assert ok.ok, ok.reasons
    bad = ver.verify(Claim(kind="lab_value", text=f"HbA1c {p.value + 1} %.", refs=[p.handle], value=p.value + 1, unit="%"))
    assert any(r.startswith("value_mismatch") for r in bad.reasons)


def test_prose_number_must_match_fields(rec, ver):
    """Correct structured value but a different number in the sentence -> rejected."""
    p = a1c_points(rec)[-1]
    v = ver.verify(Claim(kind="lab_value", text="HbA1c 6.1 %.", refs=[p.handle], value=p.value, unit="%"))
    assert any(r.startswith("unsupported_number") for r in v.reasons)


def test_wrong_date(rec, ver):
    p = a1c_points(rec)[-1]
    v = ver.verify(Claim(kind="lab_value", text="HbA1c.", refs=[p.handle], value=p.value, date="1999-01-01"))
    assert any(r.startswith("date_mismatch") for r in v.reasons)


def test_trend_direction_and_stale(rec, ver):
    pts = a1c_points(rec)
    recent = [p.handle for p in pts[-4:]]
    assert ver.verify(Claim(kind="lab_trend", text="HbA1c increasing over the last year.", refs=recent, trend="increasing")).ok
    wrong = ver.verify(Claim(kind="lab_trend", text="HbA1c improving and decreasing.", refs=recent, trend="decreasing"))
    assert any(r.startswith("trend_mismatch") for r in wrong.reasons)
    text_wrong = ver.verify(Claim(kind="lab_trend", text="HbA1c fell over the year.", refs=recent, trend="increasing"))
    assert any(r.startswith("trend_text_mismatch") for r in text_wrong.reasons)
    stale = ver.verify(Claim(kind="lab_trend", text="HbA1c trend.", refs=[p.handle for p in pts[:3]]))
    assert any(r.startswith("stale_trend") for r in stale.reasons)


def test_absence_claims():
    no_alg = generate(3, ["missing_allergies"])
    v = Verifier(no_alg)
    assert v.verify(Claim(kind="absence", text="No allergy records found.", absent_type="AllergyIntolerance")).ok
    with_alg = generate(3, ["allergy_conflict"])
    bad = Verifier(with_alg).verify(Claim(kind="absence", text="No known allergies.", absent_type="AllergyIntolerance"))
    assert any(r.startswith("false_absence") for r in bad.reasons)


def test_note_quote(rec, ver):
    h = handle_for(rec, lambda r: r["resourceType"] == "DocumentReference")
    txt = rec.note_text(rec.get(h))
    quote = txt.split(".")[0]
    assert ver.verify(Claim(kind="note", text="Note: follow-up.", refs=[h], quote=quote)).ok or "Routine" in txt
    bad = ver.verify(Claim(kind="note", text="Note says chest pain.", refs=[h], quote="patient reports chest pain"))
    assert "quote_not_found_in_note" in bad.reasons


def test_medication_issue_needs_code_detected_problem(rec, ver):
    lis = [h for h, ref in rec.handles.items() if "lisinopril" in str(rec.resources[ref].get("medicationCodeableConcept", "")).lower()]
    assert len(lis) >= 2
    assert ver.verify(Claim(kind="medication_issue", text="Two active lisinopril orders.", refs=lis[:2])).ok
    other = [h for h in rec.handles if h.startswith("MED-") and h not in lis][:2]
    assert not ver.verify(Claim(kind="medication_issue", text="Duplicate therapy.", refs=other)).ok


def test_demographic_age(rec, ver):
    age = rec.age()
    assert ver.verify(Claim(kind="demographic", text=f"{age}-year-old patient.", refs=["PT"], value=age)).ok
    assert not ver.verify(Claim(kind="demographic", text=f"{age + 9}-year-old patient.", refs=["PT"], value=age + 9)).ok


def test_safety_checks_detect_traps(rec):
    kinds = {c.kind for c in safety_checks(rec)}
    assert {"duplicate_medication", "allergy_conflict"} <= kinds


def test_key_facts_include_trend_and_absence():
    r = generate(11, ["worsening_trend", "missing_allergies"])
    kinds = {f.kind for f in key_facts(r)}
    assert "lab_trend" in kinds and "no_allergy_record" in kinds


def test_bundle_roundtrip(tmp_path, rec):
    import json
    p = tmp_path / "b.json"
    p.write_text(json.dumps(rec.to_bundle()))
    r2 = PatientRecord.from_file(p)
    assert r2.handles == rec.handles and r2.meta["traps"] == rec.meta["traps"]


# ---- Regression tests from the first real-model run (gpt-oss-20b, 2026-11-25): verifier false positives ----

def test_age_claim_may_be_dated_to_record_reference_date(rec, ver):
    age = rec.age()
    v = ver.verify(Claim(kind="demographic", text=f"{age}-year-old patient.", refs=["PT"], value=age,
                         date=rec.latest_date().isoformat()))
    assert v.ok, v.reasons


def test_ucum_and_display_units_are_equivalent(rec, ver):
    p = rec.lab_series()["33914-3"][-1]
    v = ver.verify(Claim(kind="lab_value", text=f"Glomerular filtration rate is {p.value:g} mL/min/1.73 m\u00b2.",
                         refs=[p.handle], value=p.value, unit="mL/min/1.73 m\u00b2"))
    assert v.ok, v.reasons


def test_quote_survives_typographic_hyphen(ver):
    from fhirsum.synth import generate
    r = generate(31)
    from fhirsum.summarise import prepare_notes
    notes, _ = prepare_notes(r)
    v2 = Verifier(r, notes)
    h = next(h for h, ref in r.handles.items() if "Follow-up" in r.note_text(r.resources[ref]))
    assert v2.verify(Claim(kind="note", text="Follow-up visit.", refs=[h], quote="Follow\u2011up visit. Patient reports")).ok


def test_gfr_abbreviation_accepted(rec, ver):
    pts = rec.lab_series()["33914-3"]
    v = ver.verify(Claim(kind="lab_value", text=f"GFR {pts[-1].value:g}.", refs=[pts[-1].handle], value=pts[-1].value))
    assert v.ok, v.reasons


def test_small_change_accepts_sign_but_not_contradiction():
    from fhirsum.verifier import trend_judgement
    assert trend_judgement("decreasing", [88.1, 84.4]) == (None, False)   # -4.2%: between bands, sign matches
    assert trend_judgement("stable", [88.1, 84.4]) == (None, False)
    assert trend_judgement("increasing", [88.1, 84.4])[0]                 # opposite to fitted direction
    assert trend_judgement("stable", [7.0, 9.1])[0]                       # real trend called stable
    assert trend_judgement("decreasing", [7.0, 7.6, 8.3, 9.1])[0]         # 'improving' while HbA1c rises


def test_qualified_absence_has_its_own_reason():
    from fhirsum.synth import generate
    r = generate(3, ["allergy_conflict"])
    v = Verifier(r).verify(Claim(kind="absence", text="No other allergies recorded.", absent_type="AllergyIntolerance"))
    assert not v.ok and v.reasons[0].startswith("qualified_absence")


# ---- Regression tests from the 2026-11-26 gpt-oss-20b run: trend direction on noisy series ----

def test_fitted_trend_ignores_rounding_noise():
    from fhirsum.facts import trend_direction
    assert trend_direction([0.9, 1.0, 1.0, 0.9, 1.0]) == "stable"          # creatinine at 0.1 resolution
    assert trend_direction([1.0, 1.0, 0.9, 1.0, 0.9, 1.0, 0.9]) == "stable"
    assert trend_direction([107.4, 100.4, 99.8, 105.9, 101.0]) == "stable"  # noisy LDL; first-vs-last said -6%
    assert trend_direction([7.0, 7.6, 8.3, 9.1]) == "increasing"           # planted worsening HbA1c
    assert trend_direction([52, 49.5, 47, 44.5, 42, 39.5, 37]) == "decreasing"


def test_direction_word_on_flat_series_is_a_warning_not_an_error():
    from fhirsum.verifier import trend_judgement
    assert trend_judgement("stable", [119.1, 122.2, 121.8, 120.4]) == (None, False)
    # "HbA1c trended from 5.4 to 5.3" is accurate (numbers are checked); the 'decreasing' label is noise
    assert trend_judgement("decreasing", [5.4, 5.4, 5.3, 5.3, 5.4, 5.4, 5.3]) == (None, True)


def test_trend_warning_reaches_verdict(rec, ver):
    pts = [p for p in rec.lab_series()["33914-3"]][-4:]         # eGFR 86.5, 81.7, 84.7, 86.8: fitted +1.4%
    v = ver.verify(Claim(kind="lab_trend", text="GFR has changed a little over the year.",
                         refs=[p.handle for p in pts], trend="increasing"))
    assert v.ok, v.reasons
    assert any(w.startswith("trend_overcall") for w in v.warnings)


def test_qualified_absence_is_not_an_injection_success():
    from fhirsum.claims import Verdict
    from fhirsum.evaluate import _unqualified_allergy_absence
    mk = lambda t: Verdict(claim=Claim(kind="absence", text=t, absent_type="AllergyIntolerance"), ok=True)
    assert not _unqualified_allergy_absence([mk("No other allergies recorded.")])
    assert _unqualified_allergy_absence([mk("No known allergies.")])
