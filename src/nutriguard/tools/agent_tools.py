"""Strands `@tool` surface for the Person 2 (vision/nutrition/safety/data) slice.

Every function here is a thin adapter: convert JSON-in, call exactly one
business-logic function from `vision`, `nutrition`, `safety`, or `data`,
convert JSON-out. No allergen matching, macro math, portion heuristics, or
persistence logic is implemented in this file - see the module docstrings
of `nutriguard.safety.allergens`, `nutriguard.nutrition.macros`,
`nutriguard.vision.portion`, and `nutriguard.data.repository` for that.

This is the exact surface Person 1's AgentCore/Strands agent registers as
tools. Tool names, argument names, and return shapes here are the frozen
contract published to Persons 1 and 3 (see fixtures/contract.md).

Failure behavior is explicit and uniform: a tool never raises an unhandled
exception up through the agent. Domain/validation errors are caught and
returned as a structured `{"error": ...}` dict so the agent can react to a
failure instead of crashing the turn.
"""

from __future__ import annotations

from typing import Any

from strands import tool

from nutriguard.data import repository
from nutriguard.domain.models import MealRecord
from nutriguard.nutrition.macros import aggregate_macros, get_macros
from nutriguard.safety.checker import check_safety
from nutriguard.tools.serde import (
    food_item_from_dict,
    food_item_to_dict,
    macro_breakdown_from_dict,
    macro_breakdown_to_dict,
    safety_result_from_dict,
    safety_result_to_dict,
    user_profile_from_dict,
    user_profile_to_dict,
)
from nutriguard.vision.identify import identify_food as _identify_food
from nutriguard.vision.portion import estimate_portion as _estimate_portion


@tool
def identify_food(image_path: str, backend: str = "fixture") -> dict[str, Any]:
    """Identify food items in a photo.

    Args:
        image_path: Path to the meal photo.
        backend: Identification backend - "fixture" (default, deterministic,
            no network calls) or "bedrock" (real Bedrock vision call, only
            usable when NUTRIGUARD_VISION_BACKEND=bedrock is set).

    Returns:
        {"foods": [FoodItem-as-dict, ...]} on success, each with `label`,
        `identification_confidence` (0.0-1.0), `bbox`, and `source`.
        `grams`/`portion_is_approximate` are not yet set at this stage -
        call `estimate_portion` next.
        {"error": "..."} if identification fails (e.g. unknown backend,
        missing fixture entry, or a Bedrock call error).
    """
    try:
        foods = _identify_food(image_path, backend=backend)  # type: ignore[arg-type]
    except (KeyError, ValueError, RuntimeError) as exc:
        return {"error": str(exc)}
    return {"foods": [food_item_to_dict(food) for food in foods]}


@tool
def estimate_portion(image_path: str, foods: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate approximate portion sizes (grams) for identified foods.

    Gate A uses a bbox-area + food-category heuristic (see
    `nutriguard.vision.portion`) - every estimate is approximate by
    construction, never a certain measurement from a single photo.

    Args:
        image_path: Path to the meal photo (kept for interface symmetry
            with `identify_food`; unused by the Gate A heuristic).
        foods: List of FoodItem-as-dict, typically `identify_food`'s
            `"foods"` output.

    Returns:
        {"foods": [FoodItem-as-dict, ...]} with `grams` populated and
        `portion_is_approximate` always `True`.
        {"error": "..."} if any input food dict is malformed.
    """
    try:
        food_items = [food_item_from_dict(food) for food in foods]
    except (KeyError, ValueError) as exc:
        return {"error": f"Invalid food item: {exc}"}
    estimated = _estimate_portion(image_path, food_items)
    return {"foods": [food_item_to_dict(food) for food in estimated]}


@tool
def get_macros_tool(foods: list[dict[str, Any]]) -> dict[str, Any]:
    """Look up USDA-backed macro/calorie data for identified foods.

    Never fabricates a value: a food with no dataset match returns
    `source="unknown"` and all numeric fields `None`.

    Args:
        foods: List of FoodItem-as-dict, ideally after `estimate_portion`
            so gram-scaled values can be computed.

    Returns:
        {"per_food": {label: MacroBreakdown-as-dict, ...},
         "meal_total": MacroBreakdown-as-dict} on success. `meal_total`'s
        `sugar_g` is always present as its own field when computable, per
        the dashboard's sugar-highlight requirement.
        {"error": "..."} if any input food dict is malformed.
    """
    try:
        food_items = [food_item_from_dict(food) for food in foods]
    except (KeyError, ValueError) as exc:
        return {"error": f"Invalid food item: {exc}"}
    per_food = get_macros(food_items)
    meal_total = aggregate_macros(per_food)
    return {
        "per_food": {label: macro_breakdown_to_dict(macro) for label, macro in per_food.items()},
        "meal_total": macro_breakdown_to_dict(meal_total),
    }


@tool
def check_safety_tool(
    foods: list[dict[str, Any]],
    profile: dict[str, Any],
    meal_total_macros: dict[str, Any],
    kb_evidence: list[str] | None = None,
) -> dict[str, Any]:
    """Check a meal against a user's profile for allergen and macro concerns.

    Allergen matching is deterministic (never LLM-derived) and always runs
    first; the verdict follows the precedence order allergen conflict >
    cannot-verify > macro caution > no-conflict-detected. The output never
    claims a meal is "safe" or "allergen-free" - a photo cannot rule out
    hidden ingredients, so the strongest positive result is
    "no_conflict_detected".

    Args:
        foods: List of FoodItem-as-dict (post-identification, ideally
            post-portion-estimation).
        profile: UserProfile-as-dict, e.g. from `get_profile_tool`.
        meal_total_macros: MacroBreakdown-as-dict for the whole meal,
            typically `get_macros_tool`'s `"meal_total"`.
        kb_evidence: Optional list of retrieved evidence strings (Bedrock
            Knowledge Base retrieval). A missing/empty list never weakens
            or strengthens the verdict - it only leaves `evidence_refs` empty.

    Returns:
        {"safety_result": SafetyResult-as-dict} on success, with `verdict`,
        `allergen_findings`, a non-diagnostic `explanation`, `macro_notes`,
        and `evidence_refs`.
        {"error": "..."} if any input dict is malformed.
    """
    try:
        food_items = [food_item_from_dict(food) for food in foods]
        user_profile = user_profile_from_dict(profile)
        macros = macro_breakdown_from_dict(meal_total_macros)
    except (KeyError, ValueError) as exc:
        return {"error": f"Invalid input: {exc}"}

    result = check_safety(food_items, user_profile, macros, kb_evidence=kb_evidence)
    return {"safety_result": safety_result_to_dict(result)}


@tool
def log_meal_tool(
    meal_id: str,
    user_id: str,
    logged_at_iso: str,
    foods: list[dict[str, Any]],
    meal_total_macros: dict[str, Any],
    safety_result: dict[str, Any],
) -> dict[str, Any]:
    """Persist a completed meal (foods, macros, safety verdict) for a user.

    Args:
        meal_id: Unique id for this meal (caller-generated).
        user_id: The owning user's id.
        logged_at_iso: ISO-8601 timestamp string for when the meal was logged.
        foods: List of FoodItem-as-dict for the logged meal.
        meal_total_macros: MacroBreakdown-as-dict for the whole meal.
        safety_result: SafetyResult-as-dict, typically
            `check_safety_tool`'s `"safety_result"`.

    Returns:
        {"status": "logged", "meal_id": meal_id} on success.
        {"error": "..."} if any input is malformed or the write fails.
    """
    try:
        record = MealRecord(
            meal_id=meal_id,
            user_id=user_id,
            logged_at_iso=logged_at_iso,
            foods=tuple(food_item_from_dict(food) for food in foods),
            macros=macro_breakdown_from_dict(meal_total_macros),
            safety_result=safety_result_from_dict(safety_result),
        )
    except (KeyError, ValueError) as exc:
        return {"error": f"Invalid input: {exc}"}

    try:
        repository.log_meal(record)
    except repository.RepositoryError as exc:
        return {"error": f"Failed to log meal: {exc}"}
    return {"status": "logged", "meal_id": meal_id}


@tool
def get_profile_tool(user_id: str) -> dict[str, Any]:
    """Fetch a user's structured profile (allergies, sugar limit).

    Args:
        user_id: The user's id.

    Returns:
        {"profile": UserProfile-as-dict} if found.
        {"profile": None} if no profile exists for `user_id`.
        {"error": "..."} if the read fails for a reason other than
            "not found" (e.g. the table is unreachable).
    """
    try:
        profile = repository.get_profile(user_id)
    except repository.RepositoryError as exc:
        return {"error": f"Failed to fetch profile: {exc}"}
    if profile is None:
        return {"profile": None}
    return {"profile": user_profile_to_dict(profile)}
