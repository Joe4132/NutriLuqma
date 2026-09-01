"""
Deterministic fixture stubs for all six required tools.

Rules:
- Every stub is clearly labelled SOURCE = "stub" so it is never silent.
- Shapes match docs/contracts/gate_a_tools.md exactly.
- The demo persona carries a real allergy (peanut) so the conflict path
  is exercised from minute one, not discovered at integration.
- Delete or replace each stub once Person 2's real implementation lands.
  The dynamic resolver in agent_tools.py handles the swap automatically.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Stub identity marker — visible in every response so stubs are never silent
# ---------------------------------------------------------------------------
SOURCE = "stub"

# ---------------------------------------------------------------------------
# Demo personas — use these user IDs in dev invokes and tests
# ---------------------------------------------------------------------------

DEMO_PERSONA_WITH_ALLERGY = {
    "user_id": "demo-allergy-1",
    "allergies": ["peanut"],          # real allergy — exercises the conflict path
    "conditions": ["type-2-diabetes"],
    "daily_sugar_limit_g": 30.0,
    "notes": "Demo persona for Gate A allergen-conflict testing.",
}

DEMO_PERSONA_CLEAN = {
    "user_id": "demo-1",
    "allergies": [],
    "conditions": [],
    "daily_sugar_limit_g": None,
    "notes": "Demo persona for baseline journey testing.",
}

# ---------------------------------------------------------------------------
# Stub fixture data — grilled chicken + rice meal, no allergens
# ---------------------------------------------------------------------------

_STUB_FOOD_ITEMS_CLEAN: list[dict[str, Any]] = [
    {
        "label": "grilled chicken breast",
        "confidence": 0.92,
        "grams": 150.0,
        "is_approximate": False,
        "bbox": [0.1, 0.1, 0.4, 0.5],
    },
    {
        "label": "steamed white rice",
        "confidence": 0.88,
        "grams": 180.0,
        "is_approximate": False,
        "bbox": [0.5, 0.2, 0.4, 0.4],
    },
]

# Stub fixture with a peanut-containing item — triggers conflict for demo-allergy-1
_STUB_FOOD_ITEMS_WITH_PEANUT: list[dict[str, Any]] = [
    {
        "label": "pad thai with peanuts",
        "confidence": 0.85,
        "grams": 320.0,
        "is_approximate": True,          # composite dish
        "bbox": [0.0, 0.0, 1.0, 1.0],
    },
    {
        "label": "crushed peanuts",
        "confidence": 0.90,
        "grams": 20.0,
        "is_approximate": False,
        "bbox": [0.3, 0.7, 0.2, 0.2],
    },
]

_STUB_MACRO_CLEAN: dict[str, Any] = {
    "calories": 520.0,
    "protein_g": 48.0,
    "carbs_g": 58.0,
    "fat_g": 8.0,
    "sugar_g": 1.2,
    "items": _STUB_FOOD_ITEMS_CLEAN,
    "source": SOURCE,
}

_STUB_MACRO_WITH_PEANUT: dict[str, Any] = {
    "calories": 680.0,
    "protein_g": 28.0,
    "carbs_g": 82.0,
    "fat_g": 24.0,
    "sugar_g": 12.0,
    "items": _STUB_FOOD_ITEMS_WITH_PEANUT,
    "source": SOURCE,
}

# ---------------------------------------------------------------------------
# Stub implementations
# ---------------------------------------------------------------------------

def stub_identify_food(image_path: str) -> list[dict[str, Any]]:
    """Return deterministic food items based on image path keyword."""
    if "peanut" in image_path.lower() or "allergy" in image_path.lower():
        return _STUB_FOOD_ITEMS_WITH_PEANUT
    return _STUB_FOOD_ITEMS_CLEAN


def stub_estimate_portion(
    image_path: str,
    foods: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return foods with grams filled in (already present in stubs)."""
    # Stubs already carry grams; just return as-is with source marker
    result = []
    for item in foods:
        result.append({**item, "source": SOURCE})
    return result


def stub_get_macros(foods: list[dict[str, Any]]) -> dict[str, Any]:
    """Return macro breakdown; detects peanut items to return the allergy fixture."""
    labels = [f.get("label", "").lower() for f in foods]
    if any("peanut" in lbl or "pad thai" in lbl for lbl in labels):
        return _STUB_MACRO_WITH_PEANUT
    return _STUB_MACRO_CLEAN


def stub_check_safety(
    meal: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """
    Return a raw SafetyResult shape BEFORE allergy_gate runs.

    agent_tools.py calls allergy_gate as the final step inside the
    check_safety wrapper — this stub returns the business-logic result;
    the gate then enforces the verdict. Do not duplicate gate logic here.
    """
    return {
        "status": "ok",
        "reasons": [],
        "evidence": [f"Macro source: {meal.get('source', 'unknown')}"],
        "disclaimer": (
            "This is nutritional information only. "
            "It is not medical advice. Consult your clinician or dietitian "
            "before making dietary decisions."
        ),
        "allergen_conflicts": [],   # gate will populate this
        "source": SOURCE,
    }


def stub_log_meal(user_id: str, meal: dict[str, Any]) -> None:
    """No-op stub — logs to stdout so it's visible in dev server output."""
    print(f"[stub] log_meal: user_id={user_id!r}, meal_id={meal.get('meal_id')!r}")


def stub_get_profile(user_id: str) -> dict[str, Any]:
    """Return the appropriate demo persona by user_id."""
    if user_id == DEMO_PERSONA_WITH_ALLERGY["user_id"]:
        return DEMO_PERSONA_WITH_ALLERGY
    # Default: clean persona (covers demo-1 and any unknown ID)
    return {**DEMO_PERSONA_CLEAN, "user_id": user_id}
