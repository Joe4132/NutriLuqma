"""Portion estimation heuristic (P2-03) - Gate A scope.

GATE A vs GATE B, read this before touching the numbers below:

  Gate A (this file): a single 2D photo, no depth sensor, no trained model.
  There is no honest way to produce a *certain* gram measurement from that
  input, so this module deliberately does not try. Instead it combines:
    1. the identified food's normalized bbox area (from P2-02's
       `identify_food`) as a crude proxy for how much of the plate/frame
       the food occupies, and
    2. a small hand-authored lookup of "typical full-plate portion" grams
       per broad food category (protein, grain, vegetable, sauce/condiment,
       fruit, dairy, generic fallback).
  The two are combined by scaling the category's typical portion by the
  bbox area relative to a "typical" reference area, clamped to a sane
  range. This is a rough, honest stand-in - not a hidden shortcut - and
  every single estimate it produces is unconditionally flagged
  `portion_is_approximate=True` because that is the truth of what a single
  photo can support.

  Gate B (future work, NOT implemented here): Depth Anything V2 for
  monocular depth estimation to recover actual volume from the image, feeding
  a trained volume-to-grams regression model per food category. That is a
  real measurement pipeline; this heuristic is not, and should not be
  mistaken for one.

Public entry point: `estimate_portion`.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from nutriguard.domain.models import FoodItem

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Category lookup: typical grams for a "full plate portion" of each broad
# food category, i.e. the amount you'd expect if that category occupied
# essentially the whole plate/frame. This is intentionally coarse - Gate A
# has no nutrition-database-backed serving size lookup per specific dish,
# just a handful of buckets that make peanut sauce (small, dense, used
# sparingly) look nothing like white rice (large, staple, fills the plate).
# --------------------------------------------------------------------------

FoodCategory = str

CATEGORY_FULL_PLATE_GRAMS: dict[FoodCategory, float] = {
    "protein": 180.0,  # e.g. chicken breast, salmon, steak, tofu block
    "grain": 200.0,  # e.g. white rice, pasta, bread, noodles
    "vegetable": 150.0,  # e.g. broccoli, mixed greens, salad
    "fruit": 150.0,  # e.g. sliced fruit, berries
    "dairy": 120.0,  # e.g. yogurt, cheese portion
    "sauce_or_condiment": 40.0,  # e.g. peanut sauce, dressing, dips
    "generic": 100.0,  # fallback for anything we can't categorize at all
}

# Flat default serving grams used when bbox is None, i.e. we have no area
# signal at all and must fall back to "a typical serving of this category",
# independent of any other food in the frame.
CATEGORY_FLAT_DEFAULT_GRAMS: dict[FoodCategory, float] = {
    "protein": 120.0,
    "grain": 150.0,
    "vegetable": 80.0,
    "fruit": 80.0,
    "dairy": 100.0,
    "sauce_or_condiment": 30.0,
    "generic": 80.0,
}

# Keyword -> category. Matched as a substring against the lowercased food
# label. Order matters: more specific keywords should come before broader
# ones so e.g. "peanut sauce" resolves to sauce_or_condiment rather than a
# hypothetical broader "peanut" match.
_LABEL_KEYWORD_CATEGORIES: tuple[tuple[str, FoodCategory], ...] = (
    # sauces / condiments (checked first: many are named "X sauce")
    ("sauce", "sauce_or_condiment"),
    ("dressing", "sauce_or_condiment"),
    ("dip", "sauce_or_condiment"),
    ("condiment", "sauce_or_condiment"),
    ("syrup", "sauce_or_condiment"),
    ("gravy", "sauce_or_condiment"),
    # proteins
    ("chicken", "protein"),
    ("beef", "protein"),
    ("steak", "protein"),
    ("pork", "protein"),
    ("salmon", "protein"),
    ("fish", "protein"),
    ("shrimp", "protein"),
    ("tofu", "protein"),
    ("egg", "protein"),
    ("turkey", "protein"),
    ("meat", "protein"),
    ("bacon", "protein"),
    # grains / starches
    ("rice", "grain"),
    ("pasta", "grain"),
    ("noodle", "grain"),
    ("bread", "grain"),
    ("potato", "grain"),
    ("tortilla", "grain"),
    ("quinoa", "grain"),
    ("oat", "grain"),
    # vegetables
    ("salad", "vegetable"),
    ("greens", "vegetable"),
    ("broccoli", "vegetable"),
    ("spinach", "vegetable"),
    ("vegetable", "vegetable"),
    ("veggie", "vegetable"),
    ("carrot", "vegetable"),
    ("pepper", "vegetable"),
    ("onion", "vegetable"),
    # fruit
    ("fruit", "fruit"),
    ("berry", "fruit"),
    ("berries", "fruit"),
    ("apple", "fruit"),
    ("banana", "fruit"),
    ("orange", "fruit"),
    # dairy
    ("yogurt", "dairy"),
    ("cheese", "dairy"),
    ("milk", "dairy"),
)

# Reference bbox area treated as "occupies the whole plate/frame" for
# purposes of scaling a category's full-plate grams down (or up) by the
# food's actual bbox area. Chosen as a moderate fraction of the frame
# rather than 1.0, since a real plate rarely fills the entire photo edge
# to edge.
_REFERENCE_FULL_PLATE_AREA = 0.35

# Clamp bounds for the bbox-area scaling factor, so a tiny sliver of bbox
# doesn't zero out the estimate and a bbox spanning the whole frame doesn't
# produce an absurd multiple of the category's typical portion.
_MIN_AREA_SCALE = 0.25
_MAX_AREA_SCALE = 1.75


def _categorize(label: str) -> FoodCategory:
    """Map a free-text food label to a coarse category via keyword match.

    Falls back to "generic" (and logs why) when no keyword matches, per the
    Gate A rule that every identified food gets *some* estimate rather than
    being left with `grams=None`.
    """
    lowered = label.lower()
    for keyword, category in _LABEL_KEYWORD_CATEGORIES:
        if keyword in lowered:
            return category
    logger.debug(
        "portion: no category keyword matched label %r, using generic fallback",
        label,
    )
    return "generic"


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    """Return the normalized area (w * h) of a bbox in (x, y, w, h) form."""
    _x, _y, w, h = bbox
    return max(w, 0.0) * max(h, 0.0)


def _estimate_grams_for_item(item: FoodItem) -> float:
    """Estimate grams for a single food item using the Gate A heuristic.

    If `bbox` is present, scale the category's typical full-plate grams by
    how much of the reference plate area the bbox covers (clamped). If
    `bbox` is None, use the category's flat default serving instead.
    """
    category = _categorize(item.label)

    if item.bbox is None:
        return CATEGORY_FLAT_DEFAULT_GRAMS[category]

    area = _bbox_area(item.bbox)
    scale = area / _REFERENCE_FULL_PLATE_AREA
    scale = min(max(scale, _MIN_AREA_SCALE), _MAX_AREA_SCALE)
    return CATEGORY_FULL_PLATE_GRAMS[category] * scale


def estimate_portion(image_path: str, food_items: list[FoodItem]) -> list[FoodItem]:
    """Estimate portion grams for each identified food item (Gate A heuristic).

    Combines each item's normalized `bbox` area (a proxy for relative plate
    coverage) with a per-category "typical full plate portion" lookup. When
    `bbox` is None, falls back to a flat per-category default serving size.
    Every returned item always has `grams` populated and
    `portion_is_approximate` set to True - a single 2D photo cannot yield a
    certain gram measurement, so every estimate here is approximate by
    construction, and the flag reflects that honestly regardless of input.

    `image_path` is accepted for interface symmetry with `identify_food` and
    to leave room for Gate B (which will need the actual image for depth
    estimation) but is not otherwise used by this Gate A heuristic.

    Args:
        image_path: Path to the source image. Unused in Gate A beyond
            interface consistency with `identify_food`.
        food_items: Food items previously identified by `identify_food`,
            with `grams=None` and `bbox` from vision identification.

    Returns:
        A new list of `FoodItem` instances (inputs are never mutated - and
        `FoodItem` is a frozen dataclass, so mutation would raise anyway)
        with `grams` populated and `portion_is_approximate=True`. All other
        fields (`label`, `identification_confidence`, `bbox`, `source`) are
        carried over unchanged from the corresponding input item.
    """
    del image_path  # Unused in Gate A; kept for interface symmetry, see docstring.

    estimated: list[FoodItem] = []
    for item in food_items:
        grams = _estimate_grams_for_item(item)
        estimated.append(
            replace(item, grams=grams, portion_is_approximate=True)
        )
    return estimated
