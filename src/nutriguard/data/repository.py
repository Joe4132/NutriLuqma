"""DynamoDB-backed persistence for meals and user profiles (P2-06).

This module is the only place in the data slice that talks to DynamoDB.
It provides:

- `log_meal` / `get_meal` for `MealRecord` persistence.
- `save_profile` / `get_profile` for `UserProfile` persistence.
- `get_config_value` as a small resource-identifier loader that reads from
  environment variables (and can be pointed at SSM in a real deployment)
  so that no table name, ARN, or bucket name is ever hardcoded here.

Conventions followed (see .kiro/steering/workshop-guidelines.md):
- AWS region defaults to us-west-2.
- Resource identifiers are loaded from environment/SSM, never literals.
- Reads that find nothing return `None`; writes that fail raise a typed
  exception (`RepositoryWriteError`), never a bare `Exception`.

`MealRecord` and `UserProfile` are frozen dataclasses containing nested
dataclasses and `StrEnum` members, which DynamoDB's Python SDK cannot
serialize directly. This module therefore defines explicit to-dict/from-dict
conversion helpers for both types.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Final

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from nutriguard.domain.models import (
    AllergenFinding,
    AllergenTag,
    AllergyEntry,
    AllergySeverity,
    FoodItem,
    MacroBreakdown,
    MealRecord,
    SafetyResult,
    SafetyVerdict,
    UserProfile,
)

# Default AWS region per workshop steering conventions. Overridable via the
# standard AWS_DEFAULT_REGION/AWS_REGION environment variables.
_DEFAULT_REGION: Final[str] = "us-west-2"

# Environment variable names used to look up resource identifiers. The
# *values* behind these names are never hardcoded; only these key names are.
_MEALS_TABLE_ENV_VAR: Final[str] = "NUTRIGUARD_MEALS_TABLE"
_PROFILES_TABLE_ENV_VAR: Final[str] = "NUTRIGUARD_PROFILES_TABLE"

# Local-only fallback identifiers, used solely so the module is importable
# and runnable against moto/local DynamoDB without any environment set up.
# These are TEST-ONLY DEFAULTS and must never be relied on in a deployed
# environment - deployments must set NUTRIGUARD_MEALS_TABLE /
# NUTRIGUARD_PROFILES_TABLE explicitly (e.g. via SSM-backed env injection).
_TEST_ONLY_DEFAULT_MEALS_TABLE: Final[str] = "local-dev-nutriguard-meals"
_TEST_ONLY_DEFAULT_PROFILES_TABLE: Final[str] = "local-dev-nutriguard-profiles"


class RepositoryError(Exception):
    """Base class for all errors raised by the persistence layer."""


class RepositoryWriteError(RepositoryError):
    """Raised when a write (put_item) to DynamoDB fails.

    Wraps the underlying boto3/botocore error so callers get a stable,
    typed exception from this module rather than having to catch
    `botocore.exceptions.ClientError` directly.
    """


class RepositoryReadError(RepositoryError):
    """Raised when a read (get_item) fails for a reason other than
    "item not found" (e.g. the table is missing or unreachable).

    A missing item is not an error - `get_meal`/`get_profile` return
    `None` for that case. This exception is reserved for genuine failures.
    """


def get_config_value(key: str, default: str | None = None) -> str:
    """Resolve a resource identifier (table name, etc.) by key.

    Looks up `key` in the process environment first. In a deployed
    environment, the environment is expected to be populated from AWS
    Systems Manager Parameter Store (SSM) rather than baked into code or
    config files, keeping this module free of hardcoded resource names.

    Args:
        key: The environment variable name to look up, e.g.
            "NUTRIGUARD_MEALS_TABLE".
        default: Value to fall back to when `key` is unset. Should only be
            used for local/test defaults - real deployments must set the
            environment variable explicitly.

    Returns:
        The resolved string value.

    Raises:
        RepositoryError: If `key` is unset and no `default` was provided.
    """
    value = os.environ.get(key)
    if value is not None and value != "":
        return value
    if default is not None:
        return default
    raise RepositoryError(
        f"Missing required configuration value for '{key}' and no default "
        "was provided. Set the environment variable (typically populated "
        "from SSM) before calling the repository."
    )


def _aws_region() -> str:
    """Resolve the AWS region, defaulting to us-west-2 per steering docs."""
    return os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or _DEFAULT_REGION


def _meals_table_name() -> str:
    return get_config_value(_MEALS_TABLE_ENV_VAR, default=_TEST_ONLY_DEFAULT_MEALS_TABLE)


def _profiles_table_name() -> str:
    return get_config_value(_PROFILES_TABLE_ENV_VAR, default=_TEST_ONLY_DEFAULT_PROFILES_TABLE)


def _dynamodb_resource() -> Any:
    """Create a boto3 DynamoDB resource bound to the configured region.

    A fresh resource is created per call rather than cached at import time
    so that tests can freely swap credentials/region/mocked backends
    (e.g. via moto) between test cases without stale client state.
    """
    return boto3.resource("dynamodb", region_name=_aws_region())


def _meals_table() -> Any:
    return _dynamodb_resource().Table(_meals_table_name())


def _profiles_table() -> Any:
    return _dynamodb_resource().Table(_profiles_table_name())


def _floats_to_decimals(value: Any) -> Any:
    """Recursively convert `float` values to `Decimal` for DynamoDB storage.

    boto3's DynamoDB resource API rejects native Python `float` values
    (it requires `Decimal` for numeric types), so every numeric field
    produced by the `*_to_item` converters is walked and converted here
    rather than sprinkling Decimal conversions through each converter.
    """
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _floats_to_decimals(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_floats_to_decimals(val) for val in value]
    return value


def _decimals_to_floats(value: Any) -> Any:
    """Recursively convert `Decimal` values back to `float` after a read.

    Mirrors `_floats_to_decimals` so the `*_from_item` converters can work
    with plain Python floats regardless of how DynamoDB returned them.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _decimals_to_floats(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_decimals_to_floats(val) for val in value]
    return value


# ---------------------------------------------------------------------------
# FoodItem <-> dict
# ---------------------------------------------------------------------------


def _food_item_to_item(food: FoodItem) -> dict[str, Any]:
    return {
        "label": food.label,
        "identification_confidence": food.identification_confidence,
        "bbox": list(food.bbox) if food.bbox is not None else None,
        "grams": food.grams,
        "portion_is_approximate": food.portion_is_approximate,
        "source": food.source,
    }


def _food_item_from_item(item: dict[str, Any]) -> FoodItem:
    bbox_raw = item.get("bbox")
    bbox = tuple(float(v) for v in bbox_raw) if bbox_raw is not None else None
    return FoodItem(
        label=item["label"],
        identification_confidence=float(item["identification_confidence"]),
        bbox=bbox,  # type: ignore[arg-type]
        grams=float(item["grams"]) if item.get("grams") is not None else None,
        portion_is_approximate=bool(item["portion_is_approximate"]),
        source=item["source"],
    )


# ---------------------------------------------------------------------------
# MacroBreakdown <-> dict
# ---------------------------------------------------------------------------


def _macro_breakdown_to_item(macros: MacroBreakdown) -> dict[str, Any]:
    return {
        "calories_kcal": macros.calories_kcal,
        "protein_g": macros.protein_g,
        "carbs_g": macros.carbs_g,
        "fat_g": macros.fat_g,
        "sugar_g": macros.sugar_g,
        "source": macros.source,
    }


def _macro_breakdown_from_item(item: dict[str, Any]) -> MacroBreakdown:
    def _opt_float(key: str) -> float | None:
        value = item.get(key)
        return float(value) if value is not None else None

    return MacroBreakdown(
        calories_kcal=_opt_float("calories_kcal"),
        protein_g=_opt_float("protein_g"),
        carbs_g=_opt_float("carbs_g"),
        fat_g=_opt_float("fat_g"),
        sugar_g=_opt_float("sugar_g"),
        source=item["source"],
    )


# ---------------------------------------------------------------------------
# AllergenFinding <-> dict
# ---------------------------------------------------------------------------


def _allergen_finding_to_item(finding: AllergenFinding) -> dict[str, Any]:
    return {
        "allergen": finding.allergen.value,
        "severity": finding.severity.value,
        "matched_food": finding.matched_food,
        "match_basis": finding.match_basis,
        "identification_confidence": finding.identification_confidence,
        "evidence_source": finding.evidence_source,
    }


def _allergen_finding_from_item(item: dict[str, Any]) -> AllergenFinding:
    return AllergenFinding(
        allergen=AllergenTag(item["allergen"]),
        severity=AllergySeverity(item["severity"]),
        matched_food=item["matched_food"],
        match_basis=item["match_basis"],
        identification_confidence=float(item["identification_confidence"]),
        evidence_source=item.get("evidence_source"),
    )


# ---------------------------------------------------------------------------
# SafetyResult <-> dict
# ---------------------------------------------------------------------------


def _safety_result_to_item(safety_result: SafetyResult) -> dict[str, Any]:
    return {
        "verdict": safety_result.verdict.value,
        "allergen_findings": [
            _allergen_finding_to_item(finding) for finding in safety_result.allergen_findings
        ],
        "explanation": safety_result.explanation,
        "macro_notes": list(safety_result.macro_notes),
        "evidence_refs": list(safety_result.evidence_refs),
    }


def _safety_result_from_item(item: dict[str, Any]) -> SafetyResult:
    return SafetyResult(
        verdict=SafetyVerdict(item["verdict"]),
        allergen_findings=tuple(
            _allergen_finding_from_item(f) for f in item.get("allergen_findings", [])
        ),
        explanation=item["explanation"],
        macro_notes=tuple(item.get("macro_notes", [])),
        evidence_refs=tuple(item.get("evidence_refs", [])),
    )


# ---------------------------------------------------------------------------
# MealRecord <-> DynamoDB item
# ---------------------------------------------------------------------------


def meal_record_to_item(meal: MealRecord) -> dict[str, Any]:
    """Convert a `MealRecord` into a DynamoDB-storable item dict."""
    return {
        "meal_id": meal.meal_id,
        "user_id": meal.user_id,
        "logged_at_iso": meal.logged_at_iso,
        "foods": [_food_item_to_item(food) for food in meal.foods],
        "macros": _macro_breakdown_to_item(meal.macros),
        "safety_result": _safety_result_to_item(meal.safety_result),
    }


def meal_record_from_item(item: dict[str, Any]) -> MealRecord:
    """Reconstruct a `MealRecord` from a DynamoDB item dict."""
    return MealRecord(
        meal_id=item["meal_id"],
        user_id=item["user_id"],
        logged_at_iso=item["logged_at_iso"],
        foods=tuple(_food_item_from_item(food) for food in item["foods"]),
        macros=_macro_breakdown_from_item(item["macros"]),
        safety_result=_safety_result_from_item(item["safety_result"]),
    )


# ---------------------------------------------------------------------------
# UserProfile <-> DynamoDB item
# ---------------------------------------------------------------------------


def _allergy_entry_to_item(entry: AllergyEntry) -> dict[str, Any]:
    return {
        "allergen": entry.allergen.value,
        "severity": entry.severity.value,
        "notes": entry.notes,
    }


def _allergy_entry_from_item(item: dict[str, Any]) -> AllergyEntry:
    return AllergyEntry(
        allergen=AllergenTag(item["allergen"]),
        severity=AllergySeverity(item["severity"]),
        notes=item.get("notes"),
    )


def user_profile_to_item(profile: UserProfile) -> dict[str, Any]:
    """Convert a `UserProfile` into a DynamoDB-storable item dict."""
    return {
        "user_id": profile.user_id,
        "display_name": profile.display_name,
        "allergies": [_allergy_entry_to_item(entry) for entry in profile.allergies],
        "daily_sugar_limit_g": profile.daily_sugar_limit_g,
        "notes": profile.notes,
    }


def user_profile_from_item(item: dict[str, Any]) -> UserProfile:
    """Reconstruct a `UserProfile` from a DynamoDB item dict."""
    return UserProfile(
        user_id=item["user_id"],
        display_name=item["display_name"],
        allergies=tuple(_allergy_entry_from_item(entry) for entry in item.get("allergies", [])),
        daily_sugar_limit_g=(
            float(item["daily_sugar_limit_g"])
            if item.get("daily_sugar_limit_g") is not None
            else None
        ),
        notes=item.get("notes"),
    )


# ---------------------------------------------------------------------------
# Public repository API
# ---------------------------------------------------------------------------


def log_meal(meal: MealRecord) -> None:
    """Persist a `MealRecord` to DynamoDB.

    Args:
        meal: The meal record to store. Overwrites any existing record with
            the same (user_id, meal_id).

    Raises:
        RepositoryWriteError: If the underlying DynamoDB put_item call fails
            (e.g. the table does not exist or the request is rejected).
    """
    try:
        _meals_table().put_item(Item=_floats_to_decimals(meal_record_to_item(meal)))
    except (ClientError, BotoCoreError) as exc:
        raise RepositoryWriteError(
            f"Failed to log meal {meal.meal_id!r} for user {meal.user_id!r}: {exc}"
        ) from exc


def get_meal(user_id: str, meal_id: str) -> MealRecord | None:
    """Fetch a `MealRecord` by its (user_id, meal_id) key.

    Args:
        user_id: The owning user's id.
        meal_id: The meal's id.

    Returns:
        The `MealRecord` if found, otherwise `None`.

    Raises:
        RepositoryReadError: If the read fails for a reason other than the
            item simply not existing (e.g. the table is missing).
    """
    try:
        response = _meals_table().get_item(Key={"user_id": user_id, "meal_id": meal_id})
    except (ClientError, BotoCoreError) as exc:
        raise RepositoryReadError(
            f"Failed to fetch meal {meal_id!r} for user {user_id!r}: {exc}"
        ) from exc

    item = response.get("Item")
    if item is None:
        return None
    return meal_record_from_item(_decimals_to_floats(item))


def save_profile(profile: UserProfile) -> None:
    """Persist a `UserProfile` to DynamoDB.

    Args:
        profile: The user profile to store. Overwrites any existing profile
            with the same user_id.

    Raises:
        RepositoryWriteError: If the underlying DynamoDB put_item call fails
            (e.g. the table does not exist or the request is rejected).
    """
    try:
        _profiles_table().put_item(Item=_floats_to_decimals(user_profile_to_item(profile)))
    except (ClientError, BotoCoreError) as exc:
        raise RepositoryWriteError(
            f"Failed to save profile for user {profile.user_id!r}: {exc}"
        ) from exc


def get_profile(user_id: str) -> UserProfile | None:
    """Fetch a `UserProfile` by user_id.

    Args:
        user_id: The user's id.

    Returns:
        The `UserProfile` if found, otherwise `None`.

    Raises:
        RepositoryReadError: If the read fails for a reason other than the
            item simply not existing (e.g. the table is missing).
    """
    try:
        response = _profiles_table().get_item(Key={"user_id": user_id})
    except (ClientError, BotoCoreError) as exc:
        raise RepositoryReadError(f"Failed to fetch profile for user {user_id!r}: {exc}") from exc

    item = response.get("Item")
    if item is None:
        return None
    return user_profile_from_item(_decimals_to_floats(item))
