"""Task 1 gate: prove the frozen domain contract is sound before fan-out.

Covers construction, validation rejection, and JSON round-trip for every
model in nutriguard.domain.models. This suite must be green before any
Wave 1/2 sub-agent is dispatched.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from nutriguard.domain.models import (
    SAFETY_VERDICT_PRECEDENCE,
    AllergenFinding,
    AllergenTag,
    AllergyEntry,
    AllergySeverity,
    FoodItem,
    MacroBreakdown,
    MealRecord,
    SafetyResult,
    SafetyVerdict,
    UserProfile,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# --------------------------------------------------------------------------
# FoodItem
# --------------------------------------------------------------------------


def test_food_item_valid_construction() -> None:
    item = FoodItem(label="grilled chicken", identification_confidence=0.92)
    assert item.label == "grilled chicken"
    assert item.grams is None
    assert item.portion_is_approximate is True


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0, -5.0])
def test_food_item_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValueError, match="identification_confidence"):
        FoodItem(label="rice", identification_confidence=confidence)


def test_food_item_rejects_negative_grams() -> None:
    with pytest.raises(ValueError, match="grams"):
        FoodItem(label="rice", identification_confidence=0.8, grams=-10.0)


def test_food_item_json_roundtrip() -> None:
    item = FoodItem(
        label="peanut sauce",
        identification_confidence=0.4,
        bbox=(0.1, 0.2, 0.3, 0.4),
        grams=85.0,
        portion_is_approximate=True,
        source="bedrock_vision",
    )
    payload = json.dumps(asdict(item))
    loaded = json.loads(payload)
    loaded["bbox"] = tuple(loaded["bbox"]) if loaded["bbox"] is not None else None
    restored = FoodItem(**loaded)
    assert restored == item


# --------------------------------------------------------------------------
# MacroBreakdown
# --------------------------------------------------------------------------


def test_macro_breakdown_allows_unknown_fields() -> None:
    macro = MacroBreakdown(
        calories_kcal=120.0,
        protein_g=None,
        carbs_g=None,
        fat_g=None,
        sugar_g=None,
        source="unknown",
    )
    assert macro.protein_g is None


@pytest.mark.parametrize(
    "field_name",
    ["calories_kcal", "protein_g", "carbs_g", "fat_g", "sugar_g"],
)
def test_macro_breakdown_rejects_negative_values(field_name: str) -> None:
    values: dict[str, float | None] = {
        "calories_kcal": 100.0,
        "protein_g": 5.0,
        "carbs_g": 10.0,
        "fat_g": 3.0,
        "sugar_g": 2.0,
        "source": "usda_fdc:12345",
    }
    values[field_name] = -1.0
    with pytest.raises(ValueError, match=field_name):
        MacroBreakdown(**values)  # type: ignore[arg-type]


def test_macro_breakdown_json_roundtrip() -> None:
    macro = MacroBreakdown(
        calories_kcal=250.5,
        protein_g=20.0,
        carbs_g=30.0,
        fat_g=8.0,
        sugar_g=12.0,
        source="usda_fdc:167512",
    )
    payload = json.dumps(asdict(macro))
    restored = MacroBreakdown(**json.loads(payload))
    assert restored == macro


# --------------------------------------------------------------------------
# UserProfile / AllergyEntry
# --------------------------------------------------------------------------


def test_user_profile_valid_construction() -> None:
    profile = UserProfile(
        user_id="demo-user-1",
        display_name="Sam",
        allergies=(
            AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS),
        ),
        daily_sugar_limit_g=30.0,
    )
    assert profile.allergies[0].allergen == AllergenTag.PEANUT


def test_user_profile_rejects_empty_user_id() -> None:
    with pytest.raises(ValueError, match="user_id must not be empty"):
        UserProfile(user_id="", display_name="Nobody")


def test_user_profile_rejects_duplicate_allergen() -> None:
    with pytest.raises(ValueError, match="duplicate allergen"):
        UserProfile(
            user_id="demo-user-x",
            display_name="Dup",
            allergies=(
                AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ALLERGY),
                AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS),
            ),
        )


def test_user_profile_json_roundtrip() -> None:
    profile = UserProfile(
        user_id="demo-user-2",
        display_name="Riley",
        allergies=(
            AllergyEntry(
                allergen=AllergenTag.MILK,
                severity=AllergySeverity.INTOLERANCE,
                notes="Mild GI discomfort",
            ),
        ),
        daily_sugar_limit_g=None,
    )
    payload = {
        "user_id": profile.user_id,
        "display_name": profile.display_name,
        "allergies": [
            {
                "allergen": entry.allergen.value,
                "severity": entry.severity.value,
                "notes": entry.notes,
            }
            for entry in profile.allergies
        ],
        "daily_sugar_limit_g": profile.daily_sugar_limit_g,
        "notes": profile.notes,
    }
    dumped = json.loads(json.dumps(payload))
    restored = UserProfile(
        user_id=dumped["user_id"],
        display_name=dumped["display_name"],
        allergies=tuple(
            AllergyEntry(
                allergen=AllergenTag(entry["allergen"]),
                severity=AllergySeverity(entry["severity"]),
                notes=entry["notes"],
            )
            for entry in dumped["allergies"]
        ),
        daily_sugar_limit_g=dumped["daily_sugar_limit_g"],
        notes=dumped["notes"],
    )
    assert restored == profile


@pytest.mark.parametrize("case", ["valid"])
def test_profiles_fixture_file_loads(case: str) -> None:
    data = json.loads((FIXTURES_DIR / "profiles.json").read_text())
    for payload in data[case]:
        profile = UserProfile(
            user_id=payload["user_id"],
            display_name=payload["display_name"],
            allergies=tuple(
                AllergyEntry(
                    allergen=AllergenTag(entry["allergen"]),
                    severity=AllergySeverity(entry["severity"]),
                    notes=entry["notes"],
                )
                for entry in payload["allergies"]
            ),
            daily_sugar_limit_g=payload["daily_sugar_limit_g"],
            notes=payload["notes"],
        )
        assert profile.user_id == payload["user_id"]


def test_profiles_fixture_invalid_cases_reject() -> None:
    data = json.loads((FIXTURES_DIR / "profiles.json").read_text())
    for case in data["invalid"]:
        payload = case["payload"]
        with pytest.raises(ValueError, match=case["expected_error"]):
            UserProfile(
                user_id=payload["user_id"],
                display_name=payload["display_name"],
                allergies=tuple(
                    AllergyEntry(
                        allergen=AllergenTag(entry["allergen"]),
                        severity=AllergySeverity(entry["severity"]),
                        notes=entry["notes"],
                    )
                    for entry in payload["allergies"]
                ),
                daily_sugar_limit_g=payload["daily_sugar_limit_g"],
                notes=payload["notes"],
            )


# --------------------------------------------------------------------------
# AllergenFinding
# --------------------------------------------------------------------------


def test_allergen_finding_valid_construction() -> None:
    finding = AllergenFinding(
        allergen=AllergenTag.PEANUT,
        severity=AllergySeverity.ANAPHYLAXIS,
        matched_food="peanut sauce",
        match_basis="direct",
        identification_confidence=0.9,
    )
    assert finding.match_basis == "direct"


@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_allergen_finding_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValueError, match="identification_confidence"):
        AllergenFinding(
            allergen=AllergenTag.MILK,
            severity=AllergySeverity.INTOLERANCE,
            matched_food="cheese",
            match_basis="alias",
            identification_confidence=confidence,
        )


# --------------------------------------------------------------------------
# SafetyResult / verdict precedence
# --------------------------------------------------------------------------


def test_safety_verdict_has_no_variant_meaning_safe() -> None:
    # Deliberate contract assertion: no member of SafetyVerdict may claim
    # the meal is safe or allergen-free. A photo cannot rule out hidden
    # ingredients, so the strongest positive claim is "no conflict detected".
    forbidden_substrings = ("safe", "allergen_free", "clear")
    for member in SafetyVerdict:
        lowered = member.value.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, (
                f"{member!r} must not imply a safety guarantee"
            )


def test_safety_verdict_precedence_is_total_ordering_of_all_members() -> None:
    assert set(SAFETY_VERDICT_PRECEDENCE) == set(SafetyVerdict)
    assert len(SAFETY_VERDICT_PRECEDENCE) == len(set(SAFETY_VERDICT_PRECEDENCE))


def test_allergen_conflict_outranks_everything() -> None:
    assert SAFETY_VERDICT_PRECEDENCE[0] == SafetyVerdict.ALLERGEN_CONFLICT


def test_safety_result_construction_with_findings() -> None:
    result = SafetyResult(
        verdict=SafetyVerdict.ALLERGEN_CONFLICT,
        allergen_findings=(
            AllergenFinding(
                allergen=AllergenTag.PEANUT,
                severity=AllergySeverity.ANAPHYLAXIS,
                matched_food="peanut sauce",
                match_basis="direct",
                identification_confidence=0.9,
            ),
        ),
        explanation="Peanut detected; profile lists a peanut anaphylaxis allergy.",
    )
    assert result.verdict == SafetyVerdict.ALLERGEN_CONFLICT
    assert len(result.allergen_findings) == 1


def test_safety_result_json_roundtrip() -> None:
    result = SafetyResult(
        verdict=SafetyVerdict.NO_CONFLICT_DETECTED,
        allergen_findings=(),
        explanation="No allergen conflict detected against the profile.",
        macro_notes=("Sugar within daily limit",),
        evidence_refs=("kb://doc-1",),
    )
    payload = {
        "verdict": result.verdict.value,
        "allergen_findings": [],
        "explanation": result.explanation,
        "macro_notes": list(result.macro_notes),
        "evidence_refs": list(result.evidence_refs),
    }
    dumped = json.loads(json.dumps(payload))
    restored = SafetyResult(
        verdict=SafetyVerdict(dumped["verdict"]),
        allergen_findings=(),
        explanation=dumped["explanation"],
        macro_notes=tuple(dumped["macro_notes"]),
        evidence_refs=tuple(dumped["evidence_refs"]),
    )
    assert restored == result


# --------------------------------------------------------------------------
# MealRecord
# --------------------------------------------------------------------------


def test_meal_record_valid_construction() -> None:
    record = MealRecord(
        meal_id="meal-1",
        user_id="demo-user-1",
        logged_at_iso="2026-09-01T12:00:00Z",
        foods=(FoodItem(label="rice", identification_confidence=0.95, grams=150.0),),
        macros=MacroBreakdown(
            calories_kcal=200.0,
            protein_g=4.0,
            carbs_g=45.0,
            fat_g=0.5,
            sugar_g=0.1,
            source="usda_fdc:20444",
        ),
        safety_result=SafetyResult(
            verdict=SafetyVerdict.NO_CONFLICT_DETECTED,
            allergen_findings=(),
            explanation="No allergen conflict detected against the profile.",
        ),
    )
    assert record.meal_id == "meal-1"
    assert record.foods[0].label == "rice"
