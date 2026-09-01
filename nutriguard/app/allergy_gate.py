"""
Allergen enforcement layer — app/allergy_gate.py

This is an ENFORCEMENT layer, not business logic. It runs deterministically
in Python inside the wrapper layer. The model receives the already-computed
verdict and is only allowed to phrase it. The model NEVER decides whether
an allergen is present, and it NEVER downgrades a verdict.

Rules (from PERSON1_GATE_A_PLAN.md §3A):
- Verdict escalation is one-way: ok → caution → conflict.
- Implemented as max() over an ordered IntEnum so a downgrade is
  structurally impossible.
- Confidence floor: 0.60. Below this, no "ok" verdict is possible.
- Ambiguity always resolves toward caution.
- Never output "safe", "safe to eat", or "allergen-free".
"""

from __future__ import annotations

import re
import string
from enum import IntEnum
from typing import Any


# ---------------------------------------------------------------------------
# Verdict enum — ordered so max() enforces one-way escalation
# ---------------------------------------------------------------------------

class Verdict(IntEnum):
    OK = 0
    CAUTION = 1
    CONFLICT = 2

    def to_status(self) -> str:
        return self.name.lower()


# ---------------------------------------------------------------------------
# Confidence floor
# ---------------------------------------------------------------------------

CONFIDENCE_FLOOR: float = 0.60

# ---------------------------------------------------------------------------
# Alias table (minimum per §3A — extend, never shrink)
# ---------------------------------------------------------------------------
#
# Format: { canonical_allergen_token: [alias, alias, ...] }
# All values are lowercase. The normaliser handles the rest.

ALLERGEN_ALIASES: dict[str, list[str]] = {
    "milk": [
        "dairy", "cheese", "butter", "yogurt", "cream", "ghee",
        "paneer", "whey", "custard", "ice cream",
    ],
    "dairy": [
        "milk", "cheese", "butter", "yogurt", "cream", "ghee",
        "paneer", "whey", "custard", "ice cream",
    ],
    "egg": [
        "mayonnaise", "mayo", "albumen", "meringue",
        "omelette", "frittata",
    ],
    "peanut": ["groundnut", "peanut butter", "satay"],
    "tree nut": [
        "almond", "cashew", "walnut", "pecan", "pistachio",
        "hazelnut", "macadamia", "praline",
    ],
    "wheat": [
        "gluten", "bread", "pasta", "noodles", "flour", "couscous",
        "semolina", "breadcrumb", "batter", "roti", "tortilla",
    ],
    "gluten": [
        "wheat", "bread", "pasta", "noodles", "flour", "couscous",
        "semolina", "breadcrumb", "batter", "roti", "tortilla",
    ],
    "soy": [
        "soya", "tofu", "edamame", "miso", "tempeh", "soy sauce",
    ],
    "soya": [
        "soy", "tofu", "edamame", "miso", "tempeh", "soy sauce",
    ],
    "fish": ["salmon", "tuna", "cod", "anchovy", "sardine", "fish sauce"],
    "shellfish": [
        "shrimp", "prawn", "crab", "lobster", "crayfish",
        "scallop", "mussel", "clam", "oyster",
    ],
    "sesame": ["tahini", "hummus", "halva", "za'atar"],
    "mustard": ["dijon", "mustard seed"],
    "sulphite": ["wine vinegar", "dried fruit"],
    "sulphites": ["wine vinegar", "dried fruit"],
}

# Composite / sauced dishes that are inherently unverifiable from a photo.
# A match forces match_type = "unverifiable" and caution at minimum.
COMPOSITE_KEYWORDS: list[str] = [
    "curry", "stew", "casserole", "dressing", "marinade",
    "mixed", "sauce", "soup", "broth", "gravy", "pad thai",
    "stir fry", "stir-fry", "fried rice", "noodles", "pasta",
    "salad", "wrap", "sandwich", "burger", "pizza", "taco",
    "burrito", "hash", "medley", "blend",
]

# Disclaimer that must be present on every result
_DISCLAIMER = (
    "This nutritional and allergen information is provided for informational "
    "purposes only. It is not medical advice, a diagnosis, or a treatment "
    "recommendation. Always confirm with your clinician or read the ingredient "
    "label before consuming this food."
)


# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """
    Lowercase, trim, collapse whitespace, drop punctuation,
    naive singularisation (strip trailing 's' if > 3 chars).
    """
    text = text.lower().strip()
    # Drop punctuation except spaces
    text = text.translate(str.maketrans("", "", string.punctuation.replace(" ", "")))
    # Collapse internal whitespace
    text = re.sub(r"\s+", " ", text)
    return text


def _singularise(token: str) -> str:
    """Naive singularisation: strip trailing 's' if word is long enough."""
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> list[str]:
    """Return normalised tokens, including singular variants."""
    norm = _normalise(text)
    words = norm.split()
    result = set(words)
    result.add(norm)  # whole string as one token (catches "ice cream", "soy sauce")
    for w in words:
        result.add(_singularise(w))
    return list(result)


def _is_composite(label: str) -> bool:
    norm = _normalise(label)
    return any(kw in norm for kw in COMPOSITE_KEYWORDS)


# ---------------------------------------------------------------------------
# Core matching logic
# ---------------------------------------------------------------------------

def _allergen_matches_food(
    allergen: str,
    food_label: str,
) -> tuple[bool, str]:
    """
    Return (matched: bool, match_type: "direct" | "alias" | "unverifiable").

    Priority: direct token match > alias match > composite (unverifiable).
    """
    allergen_norm = _normalise(allergen)
    food_tokens = _tokens(food_label)

    # Direct match: allergen token appears in food label tokens
    allergen_tokens = _tokens(allergen)
    for at in allergen_tokens:
        if at in food_tokens:
            if _is_composite(food_label):
                return True, "unverifiable"
            return True, "direct"

    # Alias match: any alias of this allergen appears in food label tokens
    aliases = list(ALLERGEN_ALIASES.get(allergen_norm, []))
    # Also check for any key whose aliases include this allergen
    for key, alias_list in ALLERGEN_ALIASES.items():
        if allergen_norm == key or allergen_norm in [_normalise(a) for a in alias_list]:
            aliases = list(set(aliases + alias_list + [key]))

    for alias in aliases:
        alias_tokens = _tokens(alias)
        for at in alias_tokens:
            if at in food_tokens:
                if _is_composite(food_label):
                    return True, "unverifiable"
                return True, "alias"

    # Composite with no direct match → still unverifiable caution
    if _is_composite(food_label):
        return False, "unverifiable"

    return False, "direct"  # match_type irrelevant when matched=False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_allergy_gate(
    safety_result: dict[str, Any],
    profile: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Enforce the §3A allergen verdict contract on an existing SafetyResult dict.

    This is the LAST thing called inside the check_safety wrapper before
    the result is returned. It may raise the verdict; it may NEVER lower it.

    Args:
        safety_result: The raw SafetyResult dict from business logic / stub.
                       Must contain at least: status, reasons, evidence,
                       disclaimer, allergen_conflicts.
        profile:       The UserProfile dict. May be None or empty.

    Returns:
        A new dict with the same shape, verdict enforced, conflicts populated.
    """
    result = dict(safety_result)

    # Always overwrite disclaimer with the canonical text
    result["disclaimer"] = _DISCLAIMER

    # Ensure allergen_conflicts list exists
    result.setdefault("allergen_conflicts", [])
    existing_conflicts: list[dict[str, Any]] = list(result["allergen_conflicts"])

    # --- Guard: missing or empty profile ---
    if not profile or not profile.get("user_id"):
        final_verdict = max(
            Verdict[result.get("status", "ok").upper()],
            Verdict.CAUTION,
        )
        result["status"] = final_verdict.to_status()
        result["reasons"] = list(result.get("reasons", [])) + [
            "no profile available, allergens not checked"
        ]
        result["allergen_conflicts"] = existing_conflicts
        return result

    allergies: list[str] = profile.get("allergies", [])

    # --- No allergies in profile → ok (unless already raised) ---
    if not allergies:
        result["reasons"] = list(result.get("reasons", [])) + [
            "allergens were not part of this check (no allergies in profile)"
        ]
        # Don't lower whatever verdict came in from business logic
        result["allergen_conflicts"] = existing_conflicts
        return result

    # --- Walk each food item × each allergen ---
    meal: dict[str, Any] = {}
    # safety_result may or may not embed the MacroBreakdown; agent_tools passes it separately
    # Support both calling conventions: gate may receive items embedded or as top-level key
    food_items: list[dict[str, Any]] = (
        result.get("_food_items", [])           # injected by wrapper
        or (result.get("meal", {}) or {}).get("items", [])
        or []
    )

    current_verdict = Verdict[result.get("status", "ok").upper()]
    new_conflicts: list[dict[str, Any]] = list(existing_conflicts)

    for food in food_items:
        label: str = food.get("label", "")
        confidence: float = float(food.get("confidence", 0.0))
        is_approximate: bool = bool(food.get("is_approximate", False))

        for allergen in allergies:
            matched, match_type = _allergen_matches_food(allergen, label)

            if matched and match_type == "unverifiable":
                # Composite / approximate → caution at minimum, regardless of match
                item_verdict = Verdict.CAUTION
                conflict_entry = {
                    "allergen": allergen,
                    "matched_food": label,
                    "match_type": "unverifiable",
                    "confidence": confidence,
                }
                reason = (
                    f"cannot confirm this is free of {allergen!r} — "
                    f"{label!r} is a composite or approximate item"
                )
                current_verdict = max(current_verdict, item_verdict)
                if conflict_entry not in new_conflicts:
                    new_conflicts.append(conflict_entry)
                reasons = list(result.get("reasons", []))
                if reason not in reasons:
                    reasons.append(reason)
                result["reasons"] = reasons

            elif not matched and match_type == "unverifiable":
                # Composite with no direct allergen token match — still unverifiable
                # Force caution because composite dishes cannot be verified from a photo
                item_verdict = Verdict.CAUTION
                current_verdict = max(current_verdict, item_verdict)
                reason = (
                    f"cannot confirm this is free of {allergen!r} — "
                    f"{label!r} is a composite dish and cannot be verified from a photo"
                )
                reasons = list(result.get("reasons", []))
                if reason not in reasons:
                    reasons.append(reason)
                result["reasons"] = reasons

            elif matched and is_approximate:
                # Approximate item with a match → caution
                item_verdict = Verdict.CAUTION
                conflict_entry = {
                    "allergen": allergen,
                    "matched_food": label,
                    "match_type": "unverifiable",
                    "confidence": confidence,
                }
                reason = (
                    f"cannot confirm this is free of {allergen!r} — "
                    f"{label!r} is an approximate item"
                )
                current_verdict = max(current_verdict, item_verdict)
                if conflict_entry not in new_conflicts:
                    new_conflicts.append(conflict_entry)
                reasons = list(result.get("reasons", []))
                if reason not in reasons:
                    reasons.append(reason)
                result["reasons"] = reasons

            elif matched:
                # Direct or alias match on a verified item → conflict
                item_verdict = Verdict.CONFLICT
                conflict_entry = {
                    "allergen": allergen,
                    "matched_food": label,
                    "match_type": match_type,
                    "confidence": confidence,
                }
                reason = (
                    f"allergen conflict: {allergen!r} matched {label!r} "
                    f"(match_type={match_type!r}, confidence={confidence:.2f})"
                )
                current_verdict = max(current_verdict, item_verdict)
                if conflict_entry not in new_conflicts:
                    new_conflicts.append(conflict_entry)
                reasons = list(result.get("reasons", []))
                if reason not in reasons:
                    reasons.append(reason)
                result["reasons"] = reasons

            elif confidence < CONFIDENCE_FLOOR:
                # Low confidence on an unmatched item → caution
                item_verdict = Verdict.CAUTION
                current_verdict = max(current_verdict, item_verdict)
                reason = (
                    f"low confidence ({confidence:.2f}) on {label!r} — "
                    f"cannot confirm absence of {allergen!r}"
                )
                reasons = list(result.get("reasons", []))
                if reason not in reasons:
                    reasons.append(reason)
                result["reasons"] = reasons

    # If we have allergies in the profile and all foods are confident with
    # no matches, and the verdict hasn't been raised, annotate with ok wording.
    if current_verdict == Verdict.OK:
        allergen_list = ", ".join(repr(a) for a in allergies)
        result["reasons"] = list(result.get("reasons", [])) + [
            f"no known match for {allergen_list} in the identified items"
        ]

    result["status"] = current_verdict.to_status()
    result["allergen_conflicts"] = new_conflicts

    # Clean up internal injection key
    result.pop("_food_items", None)

    return result
