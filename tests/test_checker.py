"""Tests for the safety verdict composer (P2-05).

Written TDD-style against `nutriguard.safety.checker.check_safety`. These
tests exercise the precedence rules in `SAFETY_VERDICT_PRECEDENCE`
(ALLERGEN_CONFLICT > CANNOT_VERIFY > MACRO_CAUTION > NO_CONFLICT_DETECTED),
the non-diagnostic explanation language requirement, and the
retrieval-failure (`kb_evidence=None`) behavior.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from nutriguard.domain.models import (
    AllergenTag,
    AllergyEntry,
    AllergySeverity,
    FoodItem,
    MacroBreakdown,
    SafetyVerdict,
    UserProfile,
)
from nutriguard.safety.checker import check_safety

CHECKER_PATH = Path(__file__).parent.parent / "src" / "nutriguard" / "safety" / "checker.py"


def _profile(*entries: AllergyEntry, daily_sugar_limit_g: float | None = None) -> UserProfile:
    return UserProfile(
        user_id="test-user",
        display_name="Test User",
        allergies=tuple(entries),
        daily_sugar_limit_g=daily_sugar_limit_g,
    )


def _macros(sugar_g: float | None = 0.0, **overrides: float | None) -> MacroBreakdown:
    fields: dict[str, float | None] = {
        "calories_kcal": 0.0,
        "protein_g": 0.0,
        "carbs_g": 0.0,
        "fat_g": 0.0,
        "sugar_g": sugar_g,
    }
    fields.update(overrides)
    return MacroBreakdown(
        calories_kcal=fields["calories_kcal"],
        protein_g=fields["protein_g"],
        carbs_g=fields["carbs_g"],
        fat_g=fields["fat_g"],
        sugar_g=fields["sugar_g"],
        source="aggregated",
    )


# --------------------------------------------------------------------------
# Precedence: ALLERGEN_CONFLICT beats everything, including sugar over limit
# --------------------------------------------------------------------------


def test_allergen_conflict_wins_even_when_sugar_also_over_limit() -> None:
    foods = [FoodItem(label="peanut sauce", identification_confidence=0.95)]
    profile = _profile(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS),
        daily_sugar_limit_g=10.0,
    )
    meal_macros = _macros(sugar_g=50.0)  # way over the 10g limit
    result = check_safety(foods, profile, meal_macros)
    assert result.verdict == SafetyVerdict.ALLERGEN_CONFLICT
    assert len(result.allergen_findings) == 1
    assert result.allergen_findings[0].allergen == AllergenTag.PEANUT
    # Macro caution must not leak through when allergen conflict wins.
    assert result.macro_notes == ()


# --------------------------------------------------------------------------
# CANNOT_VERIFY: low-confidence plausible-allergen food, no confirmed match
# --------------------------------------------------------------------------


def test_cannot_verify_on_low_confidence_plausible_allergen_food() -> None:
    # "almond milk" resembles a tree_nut term but the profile only lists
    # peanut, so check_allergens finds nothing - the CANNOT_VERIFY
    # heuristic is what should catch this.
    foods = [FoodItem(label="almond milk", identification_confidence=0.3)]
    profile = _profile(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ALLERGY)
    )
    meal_macros = _macros(sugar_g=0.0)
    result = check_safety(foods, profile, meal_macros)
    assert result.verdict == SafetyVerdict.CANNOT_VERIFY
    assert result.allergen_findings == ()
    assert "could not confirm" in result.explanation.lower()
    assert "photo alone" in result.explanation.lower()


def test_low_confidence_but_not_allergen_shaped_food_does_not_trigger_cannot_verify() -> None:
    # "white rice" is low confidence but doesn't resemble any allergen term.
    foods = [FoodItem(label="white rice", identification_confidence=0.2)]
    profile = _profile(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ALLERGY)
    )
    meal_macros = _macros(sugar_g=0.0)
    result = check_safety(foods, profile, meal_macros)
    assert result.verdict == SafetyVerdict.NO_CONFLICT_DETECTED


# --------------------------------------------------------------------------
# MACRO_CAUTION: sugar over limit, no allergen/verify issue
# --------------------------------------------------------------------------


def test_macro_caution_when_sugar_exceeds_limit() -> None:
    foods = [FoodItem(label="grilled chicken", identification_confidence=0.9)]
    profile = _profile(daily_sugar_limit_g=20.0)
    meal_macros = _macros(sugar_g=35.0)
    result = check_safety(foods, profile, meal_macros)
    assert result.verdict == SafetyVerdict.MACRO_CAUTION
    assert result.allergen_findings == ()
    assert result.macro_notes != ()
    assert "sugar" in result.explanation.lower()
    assert "no conflict was detected" in result.explanation.lower()


def test_macro_caution_not_triggered_when_no_limit_set() -> None:
    foods = [FoodItem(label="grilled chicken", identification_confidence=0.9)]
    profile = _profile(daily_sugar_limit_g=None)
    meal_macros = _macros(sugar_g=999.0)
    result = check_safety(foods, profile, meal_macros)
    assert result.verdict == SafetyVerdict.NO_CONFLICT_DETECTED


def test_macro_caution_not_triggered_when_sugar_is_none() -> None:
    foods = [FoodItem(label="grilled chicken", identification_confidence=0.9)]
    profile = _profile(daily_sugar_limit_g=5.0)
    meal_macros = _macros(sugar_g=None)
    result = check_safety(foods, profile, meal_macros)
    assert result.verdict == SafetyVerdict.NO_CONFLICT_DETECTED


# --------------------------------------------------------------------------
# NO_CONFLICT_DETECTED: default clean case
# --------------------------------------------------------------------------


def test_no_conflict_detected_is_default_clean_case() -> None:
    foods = [FoodItem(label="grilled chicken", identification_confidence=0.95)]
    profile = _profile(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ALLERGY),
        daily_sugar_limit_g=50.0,
    )
    meal_macros = _macros(sugar_g=5.0)
    result = check_safety(foods, profile, meal_macros)
    assert result.verdict == SafetyVerdict.NO_CONFLICT_DETECTED
    assert result.allergen_findings == ()
    assert result.macro_notes == ()
    assert "no conflict was detected" in result.explanation.lower()
    assert "hidden ingredients" in result.explanation.lower()


# --------------------------------------------------------------------------
# kb_evidence retrieval-failure path
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kb_evidence", [None, []])
def test_kb_evidence_missing_does_not_change_verdict_or_weaken_claim(
    kb_evidence: list[str] | None,
) -> None:
    foods = [FoodItem(label="peanut sauce", identification_confidence=0.95)]
    profile = _profile(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS)
    )
    meal_macros = _macros(sugar_g=0.0)

    with_evidence = check_safety(
        foods, profile, meal_macros, kb_evidence=["some retrieved snippet"]
    )
    without_evidence = check_safety(foods, profile, meal_macros, kb_evidence=kb_evidence)

    # Verdict and explanation must be identical regardless of retrieval outcome.
    assert without_evidence.verdict == with_evidence.verdict == SafetyVerdict.ALLERGEN_CONFLICT
    assert without_evidence.explanation == with_evidence.explanation
    assert without_evidence.allergen_findings == with_evidence.allergen_findings
    assert without_evidence.evidence_refs == ()
    assert with_evidence.evidence_refs == ("some retrieved snippet",)


def test_kb_evidence_failure_on_clean_meal_does_not_produce_false_safety_claim() -> None:
    """Retrieval failing on an otherwise-clean meal must not upgrade the
    explanation into an unqualified safety claim - it should read exactly
    the same as the clean case with no evidence at all."""
    foods = [FoodItem(label="grilled chicken", identification_confidence=0.95)]
    profile = _profile()
    meal_macros = _macros(sugar_g=0.0)
    result = check_safety(foods, profile, meal_macros, kb_evidence=None)
    assert result.verdict == SafetyVerdict.NO_CONFLICT_DETECTED
    assert result.evidence_refs == ()
    assert "safe" not in result.explanation.lower()
    assert "allergen-free" not in result.explanation.lower()


# --------------------------------------------------------------------------
# No diagnosis/treatment language, anywhere an explanation can be produced
# --------------------------------------------------------------------------

# Forbidden terms used as a medical-directive heuristic. Checked as whole
# words/phrases (not substrings of unrelated words) against every
# explanation string this module can produce, across all four verdicts.
_FORBIDDEN_MEDICAL_TERMS = (
    "take an",
    "take a",
    "dose",
    "dosage",
    "medication",
    "diagnose",
    "diagnosis",
    "treat ",
    "treatment",
    "antihistamine",
    "epipen",
    "prescri",
)


def _all_sample_explanations() -> list[str]:
    """Produce one explanation per verdict branch for the forbidden-term scan."""
    peanut_profile = _profile(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS)
    )
    allergen_conflict = check_safety(
        [FoodItem(label="peanut sauce", identification_confidence=0.95)],
        peanut_profile,
        _macros(sugar_g=0.0),
    )
    cannot_verify = check_safety(
        [FoodItem(label="almond milk", identification_confidence=0.3)],
        peanut_profile,
        _macros(sugar_g=0.0),
    )
    macro_caution = check_safety(
        [FoodItem(label="grilled chicken", identification_confidence=0.9)],
        _profile(daily_sugar_limit_g=10.0),
        _macros(sugar_g=50.0),
    )
    no_conflict = check_safety(
        [FoodItem(label="grilled chicken", identification_confidence=0.95)],
        _profile(),
        _macros(sugar_g=0.0),
    )
    return [
        allergen_conflict.explanation,
        cannot_verify.explanation,
        macro_caution.explanation,
        no_conflict.explanation,
    ]


def test_no_explanation_contains_diagnosis_or_treatment_language() -> None:
    """Scans every explanation this module can produce for forbidden medical terms.

    This is a heuristic word/phrase scan, not a full NLP classifier - it
    checks each of `_FORBIDDEN_MEDICAL_TERMS` (dosing, medication names,
    "diagnose", "treat", etc.) against the lowercased explanation text
    from all four verdict branches. It intentionally does not flag
    "confirm with your doctor" style deferrals, since directing the user
    to a professional is the safe, non-diagnostic pattern this module is
    supposed to use.
    """
    explanations = _all_sample_explanations()
    for explanation in explanations:
        lowered = explanation.lower()
        for term in _FORBIDDEN_MEDICAL_TERMS:
            assert term not in lowered, f"forbidden medical term {term!r} found in: {explanation!r}"


def test_no_explanation_contains_standalone_safe_or_allergen_free_claim() -> None:
    """No explanation may claim "safe" or "allergen-free" - only "no conflict detected" framing.

    Checked with a word-boundary regex so this doesn't false-positive on
    substrings (there are none expected here, but this keeps the check
    honest rather than a raw `in` substring test).
    """
    explanations = _all_sample_explanations()
    for explanation in explanations:
        lowered = explanation.lower()
        assert re.search(r"\bsafe\b", lowered) is None, explanation
        assert "allergen-free" not in lowered, explanation


def _non_docstring_string_literals(tree: ast.Module) -> list[str]:
    """Collect string constants from `tree`, excluding module/class/function docstrings.

    Docstrings legitimately *discuss* forbidden terms (e.g. explaining that
    this module must never emit dosing instructions necessarily mentions
    the word "dose" itself). Actual user-facing explanation text lives in
    plain string literals (e.g. f-string parts, return values), not in
    docstrings, so excluding the first-statement docstring of every
    module/class/function scope keeps this a check on *emitted* text
    rather than on prose *about* the forbidden terms.
    """
    docstring_nodes: set[int] = set()
    scopes = [tree] + [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    for scope in scopes:
        body = getattr(scope, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstring_nodes.add(id(body[0].value))

    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_nodes
    ]


def test_checker_source_itself_has_no_forbidden_medical_terms_in_string_literals() -> None:
    """Static scan of checker.py's non-docstring string literals for forbidden terms.

    Uses `ast` to pull out only string constants that aren't module,
    class, or function docstrings (those are documentation *about* the
    no-diagnosis-language rule and may legitimately name the forbidden
    terms while explaining the rule) so a future edit that introduces a
    new user-facing explanation string is still caught even if this test
    file's own sample-based check doesn't happen to exercise that new
    code path.
    """
    tree = ast.parse(CHECKER_PATH.read_text(encoding="utf-8"))
    combined = " ".join(_non_docstring_string_literals(tree)).lower()
    for term in _FORBIDDEN_MEDICAL_TERMS:
        assert term not in combined, f"forbidden medical term {term!r} found in checker.py source"


# --------------------------------------------------------------------------
# Allergen findings always populated regardless of which verdict wins
# --------------------------------------------------------------------------


def test_allergen_findings_always_reflect_check_allergens_output() -> None:
    foods = [
        FoodItem(label="peanut sauce", identification_confidence=0.95),
        FoodItem(label="grilled salmon", identification_confidence=0.9),
    ]
    profile = _profile(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS),
        AllergyEntry(allergen=AllergenTag.FISH, severity=AllergySeverity.ALLERGY),
    )
    result = check_safety(foods, profile, _macros(sugar_g=0.0))
    assert len(result.allergen_findings) == 2
    assert {f.allergen for f in result.allergen_findings} == {AllergenTag.PEANUT, AllergenTag.FISH}
