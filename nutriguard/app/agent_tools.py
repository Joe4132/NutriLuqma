"""
Typed @tool wrappers — app/agent_tools.py

Rules (from PERSON1_GATE_A_PLAN.md §P1-02):
- One @tool per contract entry in docs/contracts/gate_a_tools.md.
- Wrappers are THIN: validate input → call business logic → normalise → return.
- No business logic lives here.
- Dynamic resolution: try src.nutriguard.* first, fall back to app.stubs.
- A `source` field is always visible in the response — stubs are never silent.
- allergy_gate.run_allergy_gate() is the LAST step inside check_safety,
  before the result is returned.
- suggest_recipe is commented out until §6 gate is fully green.
"""

from __future__ import annotations

import traceback
from typing import Any

# Gracefully handle missing strands package (pre-install / CI environment).
# When strands is not installed, @tool becomes a no-op decorator so the
# module can still be imported and tested against the stub layer.
try:
    from strands import tool  # type: ignore[import-untyped]
except ModuleNotFoundError:
    def tool(fn):  # type: ignore[misc]
        """Shim @tool decorator used when strands package is not installed."""
        fn.__wrapped__ = fn
        return fn

from app.allergy_gate import run_allergy_gate


# ---------------------------------------------------------------------------
# Dynamic resolver helpers
# ---------------------------------------------------------------------------

def _try_import(module_path: str, attr: str) -> Any | None:
    """
    Attempt to import `attr` from `module_path`.
    Returns None (not raises) if unavailable.
    """
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, attr, None)
    except (ImportError, ModuleNotFoundError):
        return None


def _resolve(real_module: str, real_attr: str, stub_attr: str) -> tuple[Any, str]:
    """
    Return (callable, source_label).
    Tries the real module first; falls back to stubs.
    """
    real_fn = _try_import(real_module, real_attr)
    if real_fn is not None:
        return real_fn, real_module

    from app import stubs  # always available
    stub_fn = getattr(stubs, stub_attr, None)
    if stub_fn is None:
        raise RuntimeError(
            f"No implementation found for {real_attr!r} "
            f"in {real_module!r} or stubs."
        )
    return stub_fn, "stub"


# ---------------------------------------------------------------------------
# @tool: identify_food
# ---------------------------------------------------------------------------

@tool
def identify_food(image_path: str) -> dict[str, Any]:
    """
    Identify food items visible in a meal photograph.

    Args:
        image_path: Local file path or S3 URI of the meal image.

    Returns:
        dict with keys:
          - items: list of FoodItem dicts
              (label, confidence, grams, is_approximate, bbox)
          - source: implementation source label
          - error: present only on failure
    """
    if not image_path or not isinstance(image_path, str):
        return {
            "items": [],
            "source": "error",
            "error": "image_path must be a non-empty string",
        }

    fn, source = _resolve(
        "src.nutriguard.vision", "identify_food", "stub_identify_food"
    )
    try:
        items = fn(image_path)
        return {"items": items, "source": source}
    except Exception as exc:
        return {
            "items": [],
            "source": "error",
            "error": f"identify_food failed: {exc}",
        }


# ---------------------------------------------------------------------------
# @tool: estimate_portion
# ---------------------------------------------------------------------------

@tool
def estimate_portion(
    image_path: str,
    foods: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Estimate portion weights (grams) for identified food items.

    Args:
        image_path: Same image used for identification.
        foods: list of FoodItem dicts from identify_food.

    Returns:
        dict with keys:
          - items: list of FoodItem dicts with grams populated
          - source: implementation source label
          - error: present only on failure
    """
    if not image_path or not isinstance(image_path, str):
        return {
            "items": foods,
            "source": "error",
            "error": "image_path must be a non-empty string",
        }
    if not isinstance(foods, list):
        return {
            "items": [],
            "source": "error",
            "error": "foods must be a list",
        }

    fn, source = _resolve(
        "src.nutriguard.vision", "estimate_portion", "stub_estimate_portion"
    )
    try:
        items = fn(image_path, foods)
        return {"items": items, "source": source}
    except Exception as exc:
        return {
            "items": foods,
            "source": "error",
            "error": f"estimate_portion failed: {exc}",
        }


# ---------------------------------------------------------------------------
# @tool: get_macros
# ---------------------------------------------------------------------------

@tool
def get_macros(foods: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Retrieve USDA-grounded macro breakdown for a list of food items.

    Missing values are returned as the string "unknown", never a guess.

    Args:
        foods: list of FoodItem dicts (must include label and grams).

    Returns:
        MacroBreakdown dict:
          calories, protein_g, carbs_g, fat_g, sugar_g (float | "unknown"),
          items (list[FoodItem]), source (str).
    """
    if not isinstance(foods, list) or len(foods) == 0:
        return {
            "calories": "unknown",
            "protein_g": "unknown",
            "carbs_g": "unknown",
            "fat_g": "unknown",
            "sugar_g": "unknown",
            "items": foods if isinstance(foods, list) else [],
            "source": "error",
            "error": "foods must be a non-empty list",
        }

    fn, source = _resolve(
        "src.nutriguard.nutrition", "get_macros", "stub_get_macros"
    )
    try:
        result = fn(foods)
        result["source"] = source
        return result
    except Exception as exc:
        return {
            "calories": "unknown",
            "protein_g": "unknown",
            "carbs_g": "unknown",
            "fat_g": "unknown",
            "sugar_g": "unknown",
            "items": foods,
            "source": "error",
            "error": f"get_macros failed: {exc}",
        }


# ---------------------------------------------------------------------------
# @tool: check_safety
# ---------------------------------------------------------------------------

@tool
def check_safety(
    meal: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """
    Check a meal against the user's dietary profile.

    The allergen verdict is computed deterministically by allergy_gate —
    the model only phrases the result, it never decides it.

    Args:
        meal:    MacroBreakdown dict from get_macros.
        profile: UserProfile dict from get_profile.

    Returns:
        SafetyResult dict:
          status ("ok"|"caution"|"conflict"),
          reasons (list[str]),
          evidence (list[str]),
          disclaimer (str — always present),
          allergen_conflicts (list[AllergenConflict] — empty list is valid).
    """
    # Default safe-shell result for total failure cases
    failure_shell: dict[str, Any] = {
        "status": "caution",
        "reasons": ["allergen check unavailable"],
        "evidence": [],
        "disclaimer": (
            "This nutritional and allergen information is provided for "
            "informational purposes only. It is not medical advice. "
            "Confirm with your clinician or the ingredient label."
        ),
        "allergen_conflicts": [],
        "source": "error",
    }

    if not isinstance(meal, dict) or not isinstance(profile, dict):
        failure_shell["reasons"] = [
            "check_safety received invalid input types; allergen check unavailable"
        ]
        return run_allergy_gate(failure_shell, profile if isinstance(profile, dict) else None)

    fn, source = _resolve(
        "src.nutriguard.safety", "check_safety", "stub_check_safety"
    )
    try:
        raw_result = fn(meal, profile)
    except Exception as exc:
        failure_shell["reasons"] = [
            f"check_safety raised an exception; allergen check unavailable: {exc}"
        ]
        return run_allergy_gate(failure_shell, profile)

    if not isinstance(raw_result, dict):
        failure_shell["reasons"] = [
            "check_safety returned non-dict; allergen check unavailable"
        ]
        return run_allergy_gate(failure_shell, profile)

    # Inject food items so the gate can walk them
    food_items = meal.get("items", [])
    raw_result["_food_items"] = food_items
    raw_result["source"] = source

    # Ensure allergen_conflicts exists before gate runs
    raw_result.setdefault("allergen_conflicts", [])

    # ALLERGY GATE — last step, always runs, may never be removed
    gated_result = run_allergy_gate(raw_result, profile)
    return gated_result


# ---------------------------------------------------------------------------
# @tool: log_meal
# ---------------------------------------------------------------------------

@tool
def log_meal(user_id: str, meal: dict[str, Any]) -> dict[str, Any]:
    """
    Persist a meal record to the data store.

    Args:
        user_id: The user's identifier string.
        meal:    MealRecord dict (meal_id, user_id, timestamp, macros, image_key).

    Returns:
        dict with keys:
          - logged: bool
          - meal_id: str (echoed back for confirmation)
          - source: implementation source label
          - error: present only on failure
    """
    if not user_id or not isinstance(user_id, str):
        return {
            "logged": False,
            "meal_id": meal.get("meal_id", "unknown") if isinstance(meal, dict) else "unknown",
            "source": "error",
            "error": "user_id must be a non-empty string",
        }
    if not isinstance(meal, dict):
        return {
            "logged": False,
            "meal_id": "unknown",
            "source": "error",
            "error": "meal must be a dict",
        }

    fn, source = _resolve(
        "src.nutriguard.persistence", "log_meal", "stub_log_meal"
    )
    try:
        fn(user_id, meal)
        return {
            "logged": True,
            "meal_id": meal.get("meal_id", "unknown"),
            "source": source,
        }
    except Exception as exc:
        return {
            "logged": False,
            "meal_id": meal.get("meal_id", "unknown"),
            "source": "error",
            "error": f"log_meal failed: {exc}",
        }


# ---------------------------------------------------------------------------
# @tool: get_profile
# ---------------------------------------------------------------------------

@tool
def get_profile(user_id: str) -> dict[str, Any]:
    """
    Retrieve the user's dietary profile.

    The profile is the authoritative source for allergens and dietary limits.
    It is re-read on every request; memory never substitutes for this call.

    Args:
        user_id: The user's identifier string.

    Returns:
        UserProfile dict:
          user_id, allergies (list[str]), conditions (list[str]),
          daily_sugar_limit_g (float|None), notes (str).
        On missing profile: returns a caution-flag profile with empty allergies.
    """
    if not user_id or not isinstance(user_id, str):
        return {
            "user_id": "unknown",
            "allergies": [],
            "conditions": [],
            "daily_sugar_limit_g": None,
            "notes": "profile unavailable — invalid user_id",
            "source": "error",
            "error": "user_id must be a non-empty string",
        }

    fn, source = _resolve(
        "src.nutriguard.profiles", "get_profile", "stub_get_profile"
    )
    try:
        profile = fn(user_id)
        profile["source"] = source
        return profile
    except Exception as exc:
        return {
            "user_id": user_id,
            "allergies": [],
            "conditions": [],
            "daily_sugar_limit_g": None,
            "notes": "profile load failed",
            "source": "error",
            "error": f"get_profile failed: {exc}",
        }


# ---------------------------------------------------------------------------
# @tool: suggest_recipe
# COMMENTED OUT — enable only after §6 gate is fully green
# ---------------------------------------------------------------------------

# @tool
# def suggest_recipe(
#     profile: dict[str, Any],
#     remaining: dict[str, Any],
# ) -> dict[str, Any]:
#     """
#     Suggest a recipe that fits the user's remaining macro budget.
#
#     Args:
#         profile:   UserProfile dict.
#         remaining: MacroBreakdown dict representing remaining daily budget.
#
#     Returns:
#         Recipe dict: title, ingredients, instructions, macros.
#     """
#     fn, source = _resolve(
#         "src.nutriguard.recipes", "suggest_recipe", "stub_suggest_recipe"
#     )
#     try:
#         recipe = fn(profile, remaining)
#         recipe["source"] = source
#         return recipe
#     except Exception as exc:
#         return {
#             "title": "unknown",
#             "ingredients": [],
#             "instructions": [],
#             "macros": {},
#             "source": "error",
#             "error": f"suggest_recipe failed: {exc}",
#         }


# ---------------------------------------------------------------------------
# Tool registry (all active wrappers — used by the agent in main.py)
# ---------------------------------------------------------------------------

NUTRIGUARD_TOOLS = [
    identify_food,
    estimate_portion,
    get_macros,
    check_safety,
    log_meal,
    get_profile,
    # suggest_recipe,  # uncomment after §6 gate is green
]
