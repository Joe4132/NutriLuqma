"""Tests for the Gate A portion estimation heuristic (P2-03).

These tests pin down the honesty contract of `estimate_portion`:
- every returned item always has a non-None `grams`
- every returned item always has `portion_is_approximate=True`
- the input list/items are never mutated (FoodItem is frozen, but we still
  verify the returned instances are new objects with everything except
  `grams` preserved)
- larger bbox area -> larger gram estimate, for the same category
- a missing bbox still produces an estimate via the flat category default
"""

from __future__ import annotations

import dataclasses

from nutriguard.domain.models import FoodItem
from nutriguard.vision.portion import estimate_portion


def _food(
    label: str,
    bbox: tuple[float, float, float, float] | None,
    confidence: float = 0.9,
) -> FoodItem:
    return FoodItem(
        label=label,
        identification_confidence=confidence,
        bbox=bbox,
        source="fixture",
    )


# --------------------------------------------------------------------------
# Core honesty contract: grams always set, always flagged approximate
# --------------------------------------------------------------------------


def test_every_returned_item_has_grams_set() -> None:
    items = [
        _food("white rice", (0.1, 0.1, 0.4, 0.4)),
        _food("grilled chicken breast", (0.5, 0.1, 0.3, 0.3)),
        _food("peanut sauce", (0.1, 0.6, 0.1, 0.1)),
        _food("some completely unrecognized dish", (0.2, 0.2, 0.2, 0.2)),
    ]
    result = estimate_portion("some_image.jpg", items)
    assert len(result) == len(items)
    for item in result:
        assert item.grams is not None
        assert item.grams > 0


def test_every_returned_item_is_flagged_approximate() -> None:
    items = [_food("white rice", (0.1, 0.1, 0.4, 0.4))]
    result = estimate_portion("some_image.jpg", items)
    for item in result:
        assert item.portion_is_approximate is True


def test_unrecognized_food_still_gets_a_generic_default_estimate() -> None:
    items = [_food("mystery casserole", (0.1, 0.1, 0.3, 0.3))]
    result = estimate_portion("some_image.jpg", items)
    assert result[0].grams is not None
    assert result[0].grams > 0
    assert result[0].portion_is_approximate is True


# --------------------------------------------------------------------------
# bbox area -> relative grams sanity
# --------------------------------------------------------------------------


def test_larger_bbox_area_gives_larger_estimate_same_category() -> None:
    small = _food("white rice", (0.1, 0.1, 0.1, 0.1))  # area 0.01
    large = _food("white rice", (0.1, 0.1, 0.5, 0.5))  # area 0.25
    result = estimate_portion("some_image.jpg", [small, large])
    small_grams, large_grams = result[0].grams, result[1].grams
    assert small_grams is not None and large_grams is not None
    assert large_grams > small_grams


def test_bbox_none_fallback_still_produces_grams() -> None:
    items = [_food("white rice", None)]
    result = estimate_portion("some_image.jpg", items)
    assert result[0].grams is not None
    assert result[0].grams > 0
    assert result[0].portion_is_approximate is True


def test_bbox_none_fallback_is_flat_default_regardless_of_other_items() -> None:
    """The bbox=None fallback should not depend on sibling bbox areas."""
    a = _food("white rice", None)
    b = _food("white rice", None)
    result = estimate_portion("some_image.jpg", [a, b])
    assert result[0].grams == result[1].grams


# --------------------------------------------------------------------------
# Category lookup sanity: protein/grain typical portions differ from
# small condiment/sauce portions.
# --------------------------------------------------------------------------


def test_sauce_category_gets_smaller_default_than_grain_category() -> None:
    sauce = _food("peanut sauce", None)
    grain = _food("white rice", None)
    result = estimate_portion("some_image.jpg", [sauce, grain])
    sauce_grams, grain_grams = result[0].grams, result[1].grams
    assert sauce_grams is not None and grain_grams is not None
    assert sauce_grams < grain_grams


# --------------------------------------------------------------------------
# No mutation of input list/items
# --------------------------------------------------------------------------


def test_does_not_mutate_input_list_or_items() -> None:
    original_bbox = (0.2, 0.2, 0.3, 0.3)
    original = _food("grilled chicken breast", original_bbox)
    items = [original]

    result = estimate_portion("some_image.jpg", items)

    # Input list is untouched.
    assert items == [original]
    assert items[0].grams is None
    assert items[0] is original

    # Result is a new list with new FoodItem instance(s).
    assert result is not items
    assert result[0] is not original

    # Everything except grams/portion_is_approximate matches the original.
    original_dict = dataclasses.asdict(original)
    result_dict = dataclasses.asdict(result[0])
    for field_name in ("label", "identification_confidence", "bbox", "source"):
        assert result_dict[field_name] == original_dict[field_name]


def test_returns_new_list_not_same_object() -> None:
    items = [_food("white rice", (0.1, 0.1, 0.2, 0.2))]
    result = estimate_portion("some_image.jpg", items)
    assert result is not items
