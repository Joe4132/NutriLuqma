"""Tests for P2-04: USDA-backed macro lookup with unknown-value fallback.

Written before the implementation (TDD): these tests define the expected
behavior of `get_macros` and `aggregate_macros` in
`nutriguard.nutrition.macros`.
"""

from __future__ import annotations

import pytest

from nutriguard.domain.models import FoodItem, MacroBreakdown
from nutriguard.nutrition.macros import aggregate_macros, get_macros


# --------------------------------------------------------------------------
# get_macros - known foods
# --------------------------------------------------------------------------


def test_known_food_returns_sourced_macros_at_100g() -> None:
    foods = [FoodItem(label="grilled chicken breast", identification_confidence=0.9)]
    result = get_macros(foods)
    macro = result["grilled chicken breast"]
    assert macro.source.startswith("usda_fdc:")
    assert macro.calories_kcal == pytest.approx(165.0)
    assert macro.protein_g == pytest.approx(31.0)
    assert macro.carbs_g == pytest.approx(0.0)
    assert macro.fat_g == pytest.approx(3.6)
    assert macro.sugar_g == pytest.approx(0.0)


def test_known_food_is_case_and_whitespace_insensitive() -> None:
    foods = [FoodItem(label="  Grilled Chicken Breast  ", identification_confidence=0.9)]
    result = get_macros(foods)
    macro = result["  Grilled Chicken Breast  "]
    assert macro.source.startswith("usda_fdc:")
    assert macro.calories_kcal == pytest.approx(165.0)


# --------------------------------------------------------------------------
# get_macros - scaling by grams
# --------------------------------------------------------------------------


def test_known_food_scales_by_grams_when_present() -> None:
    foods = [
        FoodItem(label="white rice, cooked", identification_confidence=0.9, grams=150.0)
    ]
    result = get_macros(foods)
    macro = result["white rice, cooked"]
    # Per-100g: calories 130.0, protein 2.7, carbs 28.0, fat 0.3, sugar 0.1
    assert macro.calories_kcal == pytest.approx(195.0)  # 130 * 1.5
    assert macro.protein_g == pytest.approx(4.05)
    assert macro.carbs_g == pytest.approx(42.0)
    assert macro.fat_g == pytest.approx(0.45)
    assert macro.sugar_g == pytest.approx(0.15)
    assert macro.source.startswith("usda_fdc:")


def test_known_food_without_grams_returns_per_100g_values() -> None:
    foods = [FoodItem(label="white rice, cooked", identification_confidence=0.9)]
    result = get_macros(foods)
    macro = result["white rice, cooked"]
    assert macro.calories_kcal == pytest.approx(130.0)
    assert macro.protein_g == pytest.approx(2.7)


# --------------------------------------------------------------------------
# get_macros - unknown foods
# --------------------------------------------------------------------------


def test_unknown_food_returns_all_none_with_unknown_source() -> None:
    foods = [FoodItem(label="dragonfruit smoothie bowl", identification_confidence=0.5)]
    result = get_macros(foods)
    macro = result["dragonfruit smoothie bowl"]
    assert macro.calories_kcal is None
    assert macro.protein_g is None
    assert macro.carbs_g is None
    assert macro.fat_g is None
    assert macro.sugar_g is None
    assert macro.source == "unknown"


def test_unknown_food_with_grams_still_returns_all_none() -> None:
    foods = [
        FoodItem(
            label="mystery casserole", identification_confidence=0.5, grams=200.0
        )
    ]
    result = get_macros(foods)
    macro = result["mystery casserole"]
    assert macro.calories_kcal is None
    assert macro.source == "unknown"


# --------------------------------------------------------------------------
# get_macros - multiple foods
# --------------------------------------------------------------------------


def test_multiple_foods_each_get_their_own_entry() -> None:
    foods = [
        FoodItem(label="egg", identification_confidence=0.9, grams=50.0),
        FoodItem(label="bread, white", identification_confidence=0.9, grams=60.0),
        FoodItem(label="unobtainium stew", identification_confidence=0.4),
    ]
    result = get_macros(foods)
    assert set(result.keys()) == {"egg", "bread, white", "unobtainium stew"}
    assert result["egg"].source.startswith("usda_fdc:")
    assert result["bread, white"].source.startswith("usda_fdc:")
    assert result["unobtainium stew"].source == "unknown"


# --------------------------------------------------------------------------
# aggregate_macros
# --------------------------------------------------------------------------


def test_aggregate_macros_sums_known_items_including_sugar() -> None:
    per_food = {
        "white rice, cooked": MacroBreakdown(
            calories_kcal=195.0,
            protein_g=4.05,
            carbs_g=42.0,
            fat_g=0.45,
            sugar_g=0.15,
            source="usda_fdc:168878",
        ),
        "grilled chicken breast": MacroBreakdown(
            calories_kcal=165.0,
            protein_g=31.0,
            carbs_g=0.0,
            fat_g=3.6,
            sugar_g=0.0,
            source="usda_fdc:171077",
        ),
    }
    total = aggregate_macros(per_food)
    assert total.calories_kcal == pytest.approx(360.0)
    assert total.protein_g == pytest.approx(35.05)
    assert total.carbs_g == pytest.approx(42.0)
    assert total.fat_g == pytest.approx(4.05)
    assert total.sugar_g == pytest.approx(0.15)


def test_aggregate_macros_with_any_unknown_item_yields_none_for_that_field() -> None:
    # Never fabricate a value: if any item's field is unknown, the meal
    # total for that field is unknown too (a partial sum would misrepresent
    # itself as a complete total).
    per_food = {
        "white rice, cooked": MacroBreakdown(
            calories_kcal=195.0,
            protein_g=4.05,
            carbs_g=42.0,
            fat_g=0.45,
            sugar_g=0.15,
            source="usda_fdc:168878",
        ),
        "mystery casserole": MacroBreakdown(
            calories_kcal=None,
            protein_g=None,
            carbs_g=None,
            fat_g=None,
            sugar_g=None,
            source="unknown",
        ),
    }
    total = aggregate_macros(per_food)
    assert total.calories_kcal is None
    assert total.protein_g is None
    assert total.carbs_g is None
    assert total.fat_g is None
    assert total.sugar_g is None


def test_aggregate_macros_empty_input_returns_all_none() -> None:
    total = aggregate_macros({})
    assert total.calories_kcal is None
    assert total.protein_g is None
    assert total.carbs_g is None
    assert total.fat_g is None
    assert total.sugar_g is None
    assert total.source == "aggregated"
