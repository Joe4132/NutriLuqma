"""Contract tests for the Strands @tool surface (Task 4).

Each test calls a `@tool`-decorated function directly (Strands wraps the
underlying function in a `DecoratedFunctionTool` that remains callable) and
asserts the JSON-in/JSON-out contract published to Persons 1 and 3. One
orchestration test walks the full identify -> portion -> macros -> safety ->
log chain end to end, entirely offline.
"""

from __future__ import annotations

import pytest

from nutriguard.data import repository
from nutriguard.tools.agent_tools import (
    check_safety_tool,
    estimate_portion,
    get_macros_tool,
    get_profile_tool,
    identify_food,
    log_meal_tool,
)

PEANUT_PROFILE: dict[str, object] = {
    "user_id": "demo-user-1",
    "display_name": "Sam",
    "allergies": [
        {"allergen": "peanut", "severity": "anaphylaxis", "notes": None},
    ],
    "daily_sugar_limit_g": 30.0,
    "notes": None,
}

CLEAN_PROFILE: dict[str, object] = {
    "user_id": "demo-user-3",
    "display_name": "Jordan",
    "allergies": [],
    "daily_sugar_limit_g": 40.0,
    "notes": None,
}


@pytest.fixture(autouse=True)
def _moto_dynamodb_tables(monkeypatch: pytest.MonkeyPatch):
    """Spin up mocked DynamoDB tables for every test in this module."""
    from moto import mock_aws

    monkeypatch.setenv("NUTRIGUARD_MEALS_TABLE", "test-meals")
    monkeypatch.setenv("NUTRIGUARD_PROFILES_TABLE", "test-profiles")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")

    with mock_aws():
        import boto3

        client = boto3.client("dynamodb", region_name="us-west-2")
        client.create_table(
            TableName="test-meals",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "meal_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "meal_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName="test-profiles",
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


# --------------------------------------------------------------------------
# identify_food
# --------------------------------------------------------------------------


def test_identify_food_returns_foods_list() -> None:
    result = identify_food("chicken_rice_bowl.jpg")
    assert "foods" in result
    assert len(result["foods"]) == 2
    for food in result["foods"]:
        assert 0.0 <= food["identification_confidence"] <= 1.0
        assert food["grams"] is None


def test_identify_food_unknown_image_returns_error_not_exception() -> None:
    result = identify_food("does_not_exist.jpg")
    assert "error" in result


def test_identify_food_rejects_unknown_backend_as_error() -> None:
    result = identify_food("chicken_rice_bowl.jpg", backend="not-real")
    assert "error" in result


# --------------------------------------------------------------------------
# estimate_portion
# --------------------------------------------------------------------------


def test_estimate_portion_always_sets_grams_and_approximate_flag() -> None:
    identified = identify_food("pad_thai_with_peanut_sauce.jpg")
    result = estimate_portion("pad_thai_with_peanut_sauce.jpg", identified["foods"])
    assert "foods" in result
    for food in result["foods"]:
        assert food["grams"] is not None
        assert food["grams"] > 0
        assert food["portion_is_approximate"] is True


def test_estimate_portion_malformed_food_returns_error() -> None:
    result = estimate_portion("some.jpg", [{"label": "rice"}])  # missing confidence
    assert "error" in result


# --------------------------------------------------------------------------
# get_macros_tool
# --------------------------------------------------------------------------


def test_get_macros_tool_returns_per_food_and_meal_total() -> None:
    identified = identify_food("chicken_rice_bowl.jpg")
    portioned = estimate_portion("chicken_rice_bowl.jpg", identified["foods"])
    result = get_macros_tool(portioned["foods"])
    assert "per_food" in result
    assert "meal_total" in result
    assert "sugar_g" in result["meal_total"]


def test_get_macros_tool_unknown_food_yields_unknown_source() -> None:
    result = get_macros_tool(
        [
            {
                "label": "a totally novel dish nobody has heard of",
                "identification_confidence": 0.9,
                "bbox": None,
                "grams": 100.0,
                "portion_is_approximate": True,
                "source": "fixture",
            }
        ]
    )
    assert result["per_food"]["a totally novel dish nobody has heard of"]["source"] == "unknown"
    assert result["per_food"]["a totally novel dish nobody has heard of"]["calories_kcal"] is None


# --------------------------------------------------------------------------
# check_safety_tool
# --------------------------------------------------------------------------


def test_check_safety_tool_allergen_conflict() -> None:
    foods = [
        {
            "label": "peanut sauce",
            "identification_confidence": 0.95,
            "bbox": None,
            "grams": 40.0,
            "portion_is_approximate": True,
            "source": "fixture",
        }
    ]
    macros = get_macros_tool(foods)
    result = check_safety_tool(foods, PEANUT_PROFILE, macros["meal_total"])
    assert "safety_result" in result
    assert result["safety_result"]["verdict"] == "allergen_conflict"
    assert len(result["safety_result"]["allergen_findings"]) == 1
    assert "safe" not in result["safety_result"]["explanation"].lower()


def test_check_safety_tool_no_conflict_detected() -> None:
    foods = [
        {
            "label": "grilled chicken breast",
            "identification_confidence": 0.95,
            "bbox": None,
            "grams": 150.0,
            "portion_is_approximate": True,
            "source": "fixture",
        }
    ]
    macros = get_macros_tool(foods)
    result = check_safety_tool(foods, CLEAN_PROFILE, macros["meal_total"])
    assert result["safety_result"]["verdict"] == "no_conflict_detected"
    assert "no conflict was detected" in result["safety_result"]["explanation"].lower()


def test_check_safety_tool_malformed_profile_returns_error() -> None:
    result = check_safety_tool(
        [],
        {"user_id": "", "display_name": "Bad"},  # empty user_id -> ValueError
        {
            "calories_kcal": 0.0,
            "protein_g": 0.0,
            "carbs_g": 0.0,
            "fat_g": 0.0,
            "sugar_g": 0.0,
            "source": "aggregated",
        },
    )
    assert "error" in result


# --------------------------------------------------------------------------
# log_meal_tool / get_profile_tool
# --------------------------------------------------------------------------


def test_log_meal_tool_and_round_trip() -> None:
    foods = [
        {
            "label": "grilled chicken breast",
            "identification_confidence": 0.95,
            "bbox": None,
            "grams": 150.0,
            "portion_is_approximate": True,
            "source": "fixture",
        }
    ]
    macros = get_macros_tool(foods)
    safety = check_safety_tool(foods, CLEAN_PROFILE, macros["meal_total"])

    result = log_meal_tool(
        meal_id="meal-1",
        user_id="demo-user-3",
        logged_at_iso="2026-09-01T12:00:00Z",
        foods=foods,
        meal_total_macros=macros["meal_total"],
        safety_result=safety["safety_result"],
    )
    assert result == {"status": "logged", "meal_id": "meal-1"}

    stored = repository.get_meal("demo-user-3", "meal-1")
    assert stored is not None
    assert stored.meal_id == "meal-1"
    assert stored.safety_result.verdict.value == "no_conflict_detected"


def test_log_meal_tool_malformed_input_returns_error() -> None:
    result = log_meal_tool(
        meal_id="meal-x",
        user_id="demo-user-3",
        logged_at_iso="2026-09-01T12:00:00Z",
        foods=[{"label": "rice"}],  # missing identification_confidence
        meal_total_macros={
            "calories_kcal": 0.0,
            "protein_g": 0.0,
            "carbs_g": 0.0,
            "fat_g": 0.0,
            "sugar_g": 0.0,
            "source": "aggregated",
        },
        safety_result={
            "verdict": "no_conflict_detected",
            "allergen_findings": [],
            "explanation": "No conflict was detected against your profile.",
            "macro_notes": [],
            "evidence_refs": [],
        },
    )
    assert "error" in result


def test_get_profile_tool_not_found_returns_none_profile() -> None:
    result = get_profile_tool("nonexistent-user")
    assert result == {"profile": None}


def test_get_profile_tool_returns_saved_profile() -> None:
    from nutriguard.tools.serde import user_profile_from_dict

    repository.save_profile(user_profile_from_dict(PEANUT_PROFILE))
    result = get_profile_tool("demo-user-1")
    assert "profile" in result
    assert result["profile"]["user_id"] == "demo-user-1"
    assert result["profile"]["allergies"][0]["allergen"] == "peanut"


# --------------------------------------------------------------------------
# Full orchestration: identify -> portion -> macros -> safety -> log
# --------------------------------------------------------------------------


def test_full_chain_identify_to_log_with_allergen_conflict() -> None:
    """Walk the exact tool sequence Person 1's agent will call, offline."""
    identified = identify_food("pad_thai_with_peanut_sauce.jpg")
    assert "foods" in identified

    portioned = estimate_portion("pad_thai_with_peanut_sauce.jpg", identified["foods"])
    assert all(f["grams"] is not None for f in portioned["foods"])

    macros = get_macros_tool(portioned["foods"])
    assert "meal_total" in macros

    safety = check_safety_tool(portioned["foods"], PEANUT_PROFILE, macros["meal_total"])
    assert safety["safety_result"]["verdict"] == "allergen_conflict"

    logged = log_meal_tool(
        meal_id="meal-chain-1",
        user_id="demo-user-1",
        logged_at_iso="2026-09-01T12:30:00Z",
        foods=portioned["foods"],
        meal_total_macros=macros["meal_total"],
        safety_result=safety["safety_result"],
    )
    assert logged["status"] == "logged"

    stored = repository.get_meal("demo-user-1", "meal-chain-1")
    assert stored is not None
    assert stored.safety_result.verdict.value == "allergen_conflict"
    assert len(stored.safety_result.allergen_findings) == 1
    assert stored.safety_result.allergen_findings[0].allergen.value == "peanut"


# --------------------------------------------------------------------------
# One safety test for a diagnosis/treatment-shaped request path
# --------------------------------------------------------------------------


def test_safety_explanation_never_contains_diagnosis_or_treatment_language() -> None:
    """Even in the highest-severity allergen path, the tool's explanation
    must stay non-diagnostic (this mirrors the checker.py-level test but
    verifies it survives the JSON round-trip through the tool boundary)."""
    foods = [
        {
            "label": "peanut sauce",
            "identification_confidence": 0.95,
            "bbox": None,
            "grams": 40.0,
            "portion_is_approximate": True,
            "source": "fixture",
        }
    ]
    macros = get_macros_tool(foods)
    result = check_safety_tool(foods, PEANUT_PROFILE, macros["meal_total"])
    explanation = result["safety_result"]["explanation"].lower()
    for forbidden in ("take a", "dose", "medication", "diagnose", "treatment", "antihistamine"):
        assert forbidden not in explanation
