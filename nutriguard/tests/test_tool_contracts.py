"""
P1-02 — @tool wrapper contract tests.

Verifies that every tool returns the required keys, correct types,
handles unknown/missing data, and behaves on malformed input.
Also verifies that check_safety always returns allergen_conflicts.

Run: python -m pytest tests/test_tool_contracts.py -v
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.stubs import (
    DEMO_PERSONA_CLEAN,
    DEMO_PERSONA_WITH_ALLERGY,
    _STUB_FOOD_ITEMS_CLEAN,
    _STUB_MACRO_CLEAN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(fn_name: str, *args, **kwargs):
    """Call a tool wrapper by name, bypassing the @tool decorator."""
    import app.agent_tools as at  # noqa: PLC0415
    fn = getattr(at, fn_name)
    # Strands @tool wraps the function; get the underlying callable
    underlying = getattr(fn, "__wrapped__", fn)
    return underlying(*args, **kwargs)


# ---------------------------------------------------------------------------
# identify_food
# ---------------------------------------------------------------------------

class TestIdentifyFood:
    def test_returns_items_and_source(self) -> None:
        result = _call("identify_food", "tests/fixtures/demo_meal.jpg")
        assert "items" in result
        assert "source" in result

    def test_items_is_list(self) -> None:
        result = _call("identify_food", "tests/fixtures/demo_meal.jpg")
        assert isinstance(result["items"], list)

    def test_each_item_has_required_keys(self) -> None:
        result = _call("identify_food", "tests/fixtures/demo_meal.jpg")
        for item in result["items"]:
            for key in ("label", "confidence", "grams", "is_approximate", "bbox"):
                assert key in item, f"FoodItem missing key: {key!r}"

    def test_malformed_image_path(self) -> None:
        result = _call("identify_food", "")
        assert "error" in result
        assert result["items"] == []

    def test_source_not_empty(self) -> None:
        result = _call("identify_food", "tests/fixtures/demo_meal.jpg")
        assert result["source"]


# ---------------------------------------------------------------------------
# estimate_portion
# ---------------------------------------------------------------------------

class TestEstimatePortion:
    def test_returns_items_and_source(self) -> None:
        result = _call("estimate_portion", "tests/fixtures/demo_meal.jpg", _STUB_FOOD_ITEMS_CLEAN)
        assert "items" in result
        assert "source" in result

    def test_items_have_grams(self) -> None:
        result = _call("estimate_portion", "tests/fixtures/demo_meal.jpg", _STUB_FOOD_ITEMS_CLEAN)
        for item in result["items"]:
            assert "grams" in item

    def test_malformed_image_path(self) -> None:
        result = _call("estimate_portion", "", _STUB_FOOD_ITEMS_CLEAN)
        assert "error" in result

    def test_malformed_foods(self) -> None:
        result = _call("estimate_portion", "tests/fixtures/demo_meal.jpg", "not_a_list")
        assert "error" in result


# ---------------------------------------------------------------------------
# get_macros
# ---------------------------------------------------------------------------

class TestGetMacros:
    MACRO_KEYS = ("calories", "protein_g", "carbs_g", "fat_g", "sugar_g", "items", "source")

    def test_returns_required_keys(self) -> None:
        result = _call("get_macros", _STUB_FOOD_ITEMS_CLEAN)
        for key in self.MACRO_KEYS:
            assert key in result, f"MacroBreakdown missing key: {key!r}"

    def test_unknown_path_empty_list(self) -> None:
        """Empty list → unknown macros, not an exception."""
        result = _call("get_macros", [])
        for key in ("calories", "protein_g", "carbs_g", "fat_g", "sugar_g"):
            assert result[key] == "unknown", f"Expected 'unknown' for {key!r}"

    def test_unknown_path_invalid_type(self) -> None:
        result = _call("get_macros", "not_a_list")
        assert result["calories"] == "unknown"

    def test_source_present(self) -> None:
        result = _call("get_macros", _STUB_FOOD_ITEMS_CLEAN)
        assert result["source"]


# ---------------------------------------------------------------------------
# check_safety
# ---------------------------------------------------------------------------

class TestCheckSafety:
    SAFETY_KEYS = ("status", "reasons", "evidence", "disclaimer", "allergen_conflicts")

    def test_returns_required_keys(self) -> None:
        result = _call("check_safety", _STUB_MACRO_CLEAN, DEMO_PERSONA_CLEAN)
        for key in self.SAFETY_KEYS:
            assert key in result, f"SafetyResult missing key: {key!r}"

    def test_allergen_conflicts_is_list(self) -> None:
        """allergen_conflicts is always a list — empty is valid, missing key is a bug."""
        result = _call("check_safety", _STUB_MACRO_CLEAN, DEMO_PERSONA_CLEAN)
        assert isinstance(result["allergen_conflicts"], list)

    def test_allergen_conflicts_present_even_when_clean(self) -> None:
        result = _call("check_safety", _STUB_MACRO_CLEAN, DEMO_PERSONA_CLEAN)
        assert "allergen_conflicts" in result

    def test_disclaimer_always_present(self) -> None:
        result = _call("check_safety", _STUB_MACRO_CLEAN, DEMO_PERSONA_CLEAN)
        assert result["disclaimer"]
        assert len(result["disclaimer"]) > 10

    def test_status_is_valid(self) -> None:
        result = _call("check_safety", _STUB_MACRO_CLEAN, DEMO_PERSONA_CLEAN)
        assert result["status"] in ("ok", "caution", "conflict")

    def test_missing_profile_returns_caution(self) -> None:
        result = _call("check_safety", _STUB_MACRO_CLEAN, {})
        assert result["status"] in ("caution", "conflict"), (
            "Missing profile must not return 'ok'"
        )

    def test_malformed_meal_returns_caution_not_exception(self) -> None:
        result = _call("check_safety", "not_a_dict", DEMO_PERSONA_CLEAN)
        assert result["status"] in ("caution", "conflict")
        assert "allergen_conflicts" in result

    def test_no_safe_wording_in_any_field(self) -> None:
        """The word 'safe' must not appear in any string field of the result."""
        result = _call("check_safety", _STUB_MACRO_CLEAN, DEMO_PERSONA_CLEAN)
        for key, val in result.items():
            if isinstance(val, str):
                assert "safe" not in val.lower() or "not safe" in val.lower() or key == "disclaimer", (
                    f"Forbidden word 'safe' found in SafetyResult field {key!r}: {val!r}"
                )
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        assert "safe to eat" not in item.lower(), (
                            f"Forbidden phrase 'safe to eat' in reasons/evidence: {item!r}"
                        )
                        assert "allergen-free" not in item.lower(), (
                            f"Forbidden phrase 'allergen-free' in reasons/evidence: {item!r}"
                        )


# ---------------------------------------------------------------------------
# log_meal
# ---------------------------------------------------------------------------

class TestLogMeal:
    MEAL_RECORD = {
        "meal_id": "test-meal-001",
        "user_id": "demo-1",
        "timestamp": "2026-09-01T12:00:00Z",
        "macros": _STUB_MACRO_CLEAN,
        "image_key": None,
    }

    def test_returns_logged_true(self) -> None:
        result = _call("log_meal", "demo-1", self.MEAL_RECORD)
        assert result["logged"] is True

    def test_returns_meal_id(self) -> None:
        result = _call("log_meal", "demo-1", self.MEAL_RECORD)
        assert result["meal_id"] == "test-meal-001"

    def test_invalid_user_id(self) -> None:
        result = _call("log_meal", "", self.MEAL_RECORD)
        assert result["logged"] is False
        assert "error" in result

    def test_invalid_meal(self) -> None:
        result = _call("log_meal", "demo-1", "not_a_dict")
        assert result["logged"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------

class TestGetProfile:
    PROFILE_KEYS = ("user_id", "allergies", "conditions", "daily_sugar_limit_g", "notes")

    def test_returns_required_keys(self) -> None:
        result = _call("get_profile", "demo-1")
        for key in self.PROFILE_KEYS:
            assert key in result, f"UserProfile missing key: {key!r}"

    def test_allergies_is_list(self) -> None:
        result = _call("get_profile", "demo-1")
        assert isinstance(result["allergies"], list)

    def test_demo_allergy_persona_has_peanut(self) -> None:
        result = _call("get_profile", "demo-allergy-1")
        assert "peanut" in result["allergies"]

    def test_invalid_user_id_returns_caution_profile(self) -> None:
        result = _call("get_profile", "")
        assert result["user_id"] in ("unknown", "")
        assert "error" in result

    def test_source_present(self) -> None:
        result = _call("get_profile", "demo-1")
        assert "source" in result
