"""JSON-friendly dict <-> domain-model conversions for the agent tool surface.

Strands `@tool` functions receive and return JSON-serializable values (the
agent calls tools with plain dicts/lists/primitives, not frozen dataclasses
or `StrEnum` members directly). This module is the single place that
translates between that JSON boundary and the frozen domain contract in
`nutriguard.domain.models`.

Deliberately separate from `nutriguard.data.repository`'s `*_to_item`/
`*_from_item` converters: those exist to satisfy DynamoDB's storage
constraints (e.g. `Decimal` instead of `float`), while these exist to
satisfy the agent-facing JSON contract. The two happen to look similar
because they convert the same domain types, but they serve different
callers and are kept independent so a change to one does not silently
change the other.
"""

from __future__ import annotations

from typing import Any

from nutriguard.domain.models import (
    AllergenFinding,
    AllergenTag,
    AllergyEntry,
    AllergySeverity,
    FoodItem,
    MacroBreakdown,
    SafetyResult,
    SafetyVerdict,
    UserProfile,
)


def food_item_to_dict(food: FoodItem) -> dict[str, Any]:
    """Convert a `FoodItem` into a JSON-serializable dict."""
    return {
        "label": food.label,
        "identification_confidence": food.identification_confidence,
        "bbox": list(food.bbox) if food.bbox is not None else None,
        "grams": food.grams,
        "portion_is_approximate": food.portion_is_approximate,
        "source": food.source,
    }


def food_item_from_dict(data: dict[str, Any]) -> FoodItem:
    """Reconstruct a `FoodItem` from a JSON-serializable dict.

    Raises:
        KeyError: If a required field (`label`, `identification_confidence`)
            is missing.
        ValueError: If a field has an invalid value (delegated to
            `FoodItem.__post_init__`).
    """
    bbox_raw = data.get("bbox")
    bbox = tuple(float(v) for v in bbox_raw) if bbox_raw is not None else None
    return FoodItem(
        label=data["label"],
        identification_confidence=float(data["identification_confidence"]),
        bbox=bbox,  # type: ignore[arg-type]
        grams=float(data["grams"]) if data.get("grams") is not None else None,
        portion_is_approximate=bool(data.get("portion_is_approximate", True)),
        source=data.get("source", "fixture"),
    )


def macro_breakdown_to_dict(macros: MacroBreakdown) -> dict[str, Any]:
    """Convert a `MacroBreakdown` into a JSON-serializable dict."""
    return {
        "calories_kcal": macros.calories_kcal,
        "protein_g": macros.protein_g,
        "carbs_g": macros.carbs_g,
        "fat_g": macros.fat_g,
        "sugar_g": macros.sugar_g,
        "source": macros.source,
    }


def macro_breakdown_from_dict(data: dict[str, Any]) -> MacroBreakdown:
    """Reconstruct a `MacroBreakdown` from a JSON-serializable dict."""

    def _opt_float(key: str) -> float | None:
        value = data.get(key)
        return float(value) if value is not None else None

    return MacroBreakdown(
        calories_kcal=_opt_float("calories_kcal"),
        protein_g=_opt_float("protein_g"),
        carbs_g=_opt_float("carbs_g"),
        fat_g=_opt_float("fat_g"),
        sugar_g=_opt_float("sugar_g"),
        source=data["source"],
    )


def allergy_entry_to_dict(entry: AllergyEntry) -> dict[str, Any]:
    """Convert an `AllergyEntry` into a JSON-serializable dict."""
    return {
        "allergen": entry.allergen.value,
        "severity": entry.severity.value,
        "notes": entry.notes,
    }


def allergy_entry_from_dict(data: dict[str, Any]) -> AllergyEntry:
    """Reconstruct an `AllergyEntry` from a JSON-serializable dict."""
    return AllergyEntry(
        allergen=AllergenTag(data["allergen"]),
        severity=AllergySeverity(data["severity"]),
        notes=data.get("notes"),
    )


def user_profile_to_dict(profile: UserProfile) -> dict[str, Any]:
    """Convert a `UserProfile` into a JSON-serializable dict."""
    return {
        "user_id": profile.user_id,
        "display_name": profile.display_name,
        "allergies": [allergy_entry_to_dict(entry) for entry in profile.allergies],
        "daily_sugar_limit_g": profile.daily_sugar_limit_g,
        "notes": profile.notes,
    }


def user_profile_from_dict(data: dict[str, Any]) -> UserProfile:
    """Reconstruct a `UserProfile` from a JSON-serializable dict.

    Raises:
        KeyError: If `user_id` or `display_name` is missing.
        ValueError: If validation fails (empty user_id, duplicate allergen)
            - delegated to `UserProfile.__post_init__`.
    """
    return UserProfile(
        user_id=data["user_id"],
        display_name=data["display_name"],
        allergies=tuple(
            allergy_entry_from_dict(entry) for entry in data.get("allergies", [])
        ),
        daily_sugar_limit_g=(
            float(data["daily_sugar_limit_g"])
            if data.get("daily_sugar_limit_g") is not None
            else None
        ),
        notes=data.get("notes"),
    )


def allergen_finding_to_dict(finding: AllergenFinding) -> dict[str, Any]:
    """Convert an `AllergenFinding` into a JSON-serializable dict."""
    return {
        "allergen": finding.allergen.value,
        "severity": finding.severity.value,
        "matched_food": finding.matched_food,
        "match_basis": finding.match_basis,
        "identification_confidence": finding.identification_confidence,
        "evidence_source": finding.evidence_source,
    }


def allergen_finding_from_dict(data: dict[str, Any]) -> AllergenFinding:
    """Reconstruct an `AllergenFinding` from a JSON-serializable dict."""
    return AllergenFinding(
        allergen=AllergenTag(data["allergen"]),
        severity=AllergySeverity(data["severity"]),
        matched_food=data["matched_food"],
        match_basis=data["match_basis"],
        identification_confidence=float(data["identification_confidence"]),
        evidence_source=data.get("evidence_source"),
    )


def safety_result_to_dict(result: SafetyResult) -> dict[str, Any]:
    """Convert a `SafetyResult` into a JSON-serializable dict."""
    return {
        "verdict": result.verdict.value,
        "allergen_findings": [
            allergen_finding_to_dict(finding) for finding in result.allergen_findings
        ],
        "explanation": result.explanation,
        "macro_notes": list(result.macro_notes),
        "evidence_refs": list(result.evidence_refs),
    }


def safety_result_from_dict(data: dict[str, Any]) -> SafetyResult:
    """Reconstruct a `SafetyResult` from a JSON-serializable dict.

    Used by `log_meal_tool`, which receives a `SafetyResult`-as-dict back
    from an earlier tool call (`check_safety_tool`) and needs to
    reconstruct the frozen domain type before persisting it.
    """
    return SafetyResult(
        verdict=SafetyVerdict(data["verdict"]),
        allergen_findings=tuple(
            allergen_finding_from_dict(f) for f in data.get("allergen_findings", [])
        ),
        explanation=data["explanation"],
        macro_notes=tuple(data.get("macro_notes", [])),
        evidence_refs=tuple(data.get("evidence_refs", [])),
    )


def safety_verdict_from_str(value: str) -> SafetyVerdict:
    """Parse a `SafetyVerdict` from its string value. Raises `ValueError` if invalid."""
    return SafetyVerdict(value)
