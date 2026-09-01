"""USDA-backed macro lookup for identified food items (P2-04).

`get_macros` maps each `FoodItem` label to a `MacroBreakdown` sourced from a
small curated local dataset (`src/nutriguard/data/usda_subset.json`), scaled
by the item's `grams` when known. `aggregate_macros` sums a set of per-food
breakdowns into a single meal-level `MacroBreakdown`.

Per the domain contract's design rule, nutrition values are never invented:
a food label with no dataset match returns a `MacroBreakdown` with every
numeric field `None` and `source="unknown"`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path

from nutriguard.domain.models import FoodItem, MacroBreakdown

_UNKNOWN_SOURCE = "unknown"
_AGGREGATED_SOURCE = "aggregated"

# Fields carried on MacroBreakdown that get summed/scaled numerically.
_NUMERIC_FIELDS: tuple[str, ...] = (
    "calories_kcal",
    "protein_g",
    "carbs_g",
    "fat_g",
    "sugar_g",
)


@lru_cache(maxsize=1)
def _load_usda_subset() -> dict[str, dict[str, float | str]]:
    """Load and cache the curated local USDA subset dataset.

    The dataset lives at `src/nutriguard/data/usda_subset.json`. Its
    `fdc_id` values are Gate A placeholders (see the file's own
    `_provenance_note`) - a real lookup would call the live USDA
    FoodData Central API in Gate B. Keys are normalized (lowercased,
    stripped) so lookups in `get_macros` are case/whitespace insensitive.
    """
    data_path = Path(str(resources.files("nutriguard.data").joinpath("usda_subset.json")))
    with data_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    foods_raw = raw["foods"]
    normalized: dict[str, dict[str, float | str]] = {}
    for label, entry in foods_raw.items():
        normalized[label.strip().lower()] = entry
    return normalized


def _normalize_label(label: str) -> str:
    """Normalize a food label for dataset lookup (case/whitespace insensitive)."""
    return label.strip().lower()


def _macro_for_label(label: str, grams: float | None) -> MacroBreakdown:
    """Look up one food label in the local dataset and build its `MacroBreakdown`.

    Values are per-100g in the dataset. When `grams` is provided, values are
    scaled by `grams / 100`. When `grams` is `None`, per-100g values are
    returned as-is (portion-aware scaling for grams-less items depends on
    Wave 2's portion heuristic landing later - until then this is the best
    available estimate, clearly still keyed to a 100g reference).

    Returns a `MacroBreakdown` with every numeric field `None` and
    `source="unknown"` when the label has no dataset match - never a
    fabricated estimate.
    """
    dataset = _load_usda_subset()
    entry = dataset.get(_normalize_label(label))
    if entry is None:
        return MacroBreakdown(
            calories_kcal=None,
            protein_g=None,
            carbs_g=None,
            fat_g=None,
            sugar_g=None,
            source=_UNKNOWN_SOURCE,
        )

    scale = 1.0 if grams is None else grams / 100.0
    scaled = {field: float(entry[field]) * scale for field in _NUMERIC_FIELDS}
    return MacroBreakdown(
        calories_kcal=scaled["calories_kcal"],
        protein_g=scaled["protein_g"],
        carbs_g=scaled["carbs_g"],
        fat_g=scaled["fat_g"],
        sugar_g=scaled["sugar_g"],
        source=f"usda_fdc:{entry['fdc_id']}",
    )


def get_macros(foods: list[FoodItem]) -> dict[str, MacroBreakdown]:
    """Look up macro/calorie data for a list of identified foods.

    Each `FoodItem.label` is looked up (case/whitespace insensitive)
    against the curated local USDA subset dataset. When a `FoodItem.grams`
    value is present, the per-100g dataset values are scaled accordingly;
    when absent, per-100g values are returned unscaled (see `_macro_for_label`).

    Unmatched labels get a `MacroBreakdown` with all numeric fields `None`
    and `source="unknown"` - nutrition values are never guessed.

    Args:
        foods: Identified food items (from the frozen domain contract) to
            look up macros for.

    Returns:
        A mapping from each food's original (unnormalized) `label` to its
        `MacroBreakdown`. If two `FoodItem`s share the same label, the later
        one in `foods` overwrites the earlier entry in the returned mapping.
    """
    result: dict[str, MacroBreakdown] = {}
    for food in foods:
        result[food.label] = _macro_for_label(food.label, food.grams)
    return result


def aggregate_macros(per_food: dict[str, MacroBreakdown]) -> MacroBreakdown:
    """Sum a set of per-food `MacroBreakdown`s into one meal-level total.

    `sugar_g` is always summed as its own tracked field per the Gate A
    dashboard requirement. If any contributing item has `None` for a given
    field (e.g. an unknown food), the meal total for that field is also
    `None` - a partial sum would misrepresent itself as a complete total.

    Args:
        per_food: Mapping of food label to `MacroBreakdown`, typically the
            output of `get_macros`.

    Returns:
        A single `MacroBreakdown` representing the meal total, with
        `source="aggregated"`. All numeric fields are `None` when
        `per_food` is empty or when any item has a `None` value for that
        field.
    """
    totals: dict[str, float | None] = dict.fromkeys(_NUMERIC_FIELDS, 0.0)

    if not per_food:
        return MacroBreakdown(
            calories_kcal=None,
            protein_g=None,
            carbs_g=None,
            fat_g=None,
            sugar_g=None,
            source=_AGGREGATED_SOURCE,
        )

    for macro in per_food.values():
        for field_name in _NUMERIC_FIELDS:
            if totals[field_name] is None:
                continue
            value = getattr(macro, field_name)
            if value is None:
                totals[field_name] = None
            else:
                totals[field_name] = totals[field_name] + value

    return MacroBreakdown(
        calories_kcal=totals["calories_kcal"],
        protein_g=totals["protein_g"],
        carbs_g=totals["carbs_g"],
        fat_g=totals["fat_g"],
        sugar_g=totals["sugar_g"],
        source=_AGGREGATED_SOURCE,
    )
