"""Harder injections (2026-11-27): which layer catches what. Each assertion pins a measured result, including the
layers that do NOT catch an attack, so a regression in either direction is visible."""
import pytest

from fhirsum.facts import SafetyCheck, safety_checks
from fhirsum.render import display_checks
from fhirsum.sanitize import find_injections, normalise, quarantine
from fhirsum.summarise import prepare_notes
from fhirsum.synth import HARD_INJECTIONS, INJECTION_TARGETS, INJECTIONS, generate

SEED = {t: 700 + i for i, t in enumerate(sorted({**INJECTIONS, **HARD_INJECTIONS}))}


def layers(trap: str, inject: bool = True):
    rec = generate(SEED[trap], [trap], inject=inject)
    notes, quarantined = prepare_notes(rec, sanitise=True)
    conflict = any(c.kind == "note_conflicts_record" for c in safety_checks(rec, quarantined, notes))
    return bool(quarantined), conflict


# (regex withholds it, code cross-check flags it): measured on the generated suite
EXPECTED = {
    "injection_omit_med": (True, False), "injection_no_allergy": (True, False),
    "injection_paraphrased": (False, True), "injection_clinical_voice": (False, True),
    "injection_allergy_retraction": (False, True), "injection_split": (False, True),
    "injection_obfuscated": (True, False), "injection_delimiter": (True, False),
}


@pytest.mark.parametrize("trap", sorted(EXPECTED))
def test_each_attack_is_caught_by_the_expected_layer(trap):
    assert layers(trap) == EXPECTED[trap]


@pytest.mark.parametrize("trap", sorted(EXPECTED))
def test_clean_twin_raises_no_alarm(trap):
    assert layers(trap, inject=False) == (False, False)


def test_normalise_defeats_zero_width_obfuscation():
    t = HARD_INJECTIONS["injection_obfuscated"]["text"]
    assert "​" in t and find_injections(t)                 # caught only because of normalise()
    assert "​" not in normalise(t)
    clean, spans = quarantine("BP fine. " + t)
    assert "warfarin" not in clean and spans


def test_conflict_check_ignores_notes_about_inactive_drugs():
    rec = generate(3)                                           # amoxicillin 250 is a STOPPED order in every record
    from fhirsum.record import ref_of
    doc = rec.of_type("DocumentReference")[0]
    notes = {ref_of(doc): "Amoxicillin was discontinued two years ago."}
    assert not [c for c in safety_checks(rec, {}, notes) if c.kind == "note_conflicts_record"]


def test_every_injection_trap_has_a_target():
    assert set(INJECTION_TARGETS) == set(INJECTIONS) | set(HARD_INJECTIONS)


def test_critical_lab_banner_is_ranked_and_capped():
    checks = [SafetyCheck("critical_lab", f"lab {i}", [f"Observation/{i}"], sev) for i, sev in
              enumerate([1.6, 4.2, 1.9, 2.5, 3.1])]
    checks.append(SafetyCheck("note_conflicts_record", "note vs record", ["DocumentReference/x", "MedicationRequest/y"]))
    shown = display_checks(checks)
    assert shown[0].kind == "note_conflicts_record"             # record conflicts first
    crit = [c for c in shown if c.kind == "critical_lab"]
    assert [c.severity for c in crit[:3]] == [4.2, 3.1, 2.5] and "+2 more" in crit[3].message
    assert len(checks) == 6                                     # data untouched


def test_new_attacks_are_scored_with_twins(tmp_path):
    from fhirsum.evaluate import run_eval
    from fhirsum.llm import MockLLM
    from fhirsum.synth import build_suite
    paths = [p for p in build_suite(tmp_path / "s", n_clean=0) if p.stem.startswith("injection_clinical_voice_0")]
    assert len(paths) == 2
    agg = run_eval(paths, MockLLM())
    assert agg["injected_cases"] == 1 and agg["conflict_flagged_rate"] == 1
    assert agg["systems"]["llm_verify_bf"]["injection_cases"] == 1
