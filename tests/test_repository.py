"""Tests for the DynamoDB-backed meal/profile repository (P2-06).

All AWS calls in this suite are made against moto's mocked DynamoDB - no
real AWS credentials or network access are required to run this file.
"""

from __future__ import annotations

from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from nutriguard.domain.models import (
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


@pytest.fixture
def dynamodb_tables(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Stand up mocked DynamoDB tables matching the repository's env config.

    Uses moto's `mock_aws` context manager so no real AWS calls are made,
    and sets dummy credentials so boto3 never tries to load real ones.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("NUTRIGUARD_MEALS_TABLE", "test-nutriguard-meals")
    monkeypatch.setenv("NUTRIGUARD_PROFILES_TABLE", "test-nutriguard-profiles")

    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-west-2")
        client.create_table(
            TableName="test-nutriguard-meals",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "meal_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "meal_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName="test-nutriguard-profiles",
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


def _sample_meal(user_id: str = "user-1", meal_id: str = "meal-1") -> MealRecord:
    return MealRecord(
        meal_id=meal_id,
        user_id=user_id,
        logged_at_iso="2024-01-15T12:30:00Z",
        foods=(
            FoodItem(
                label="grilled chicken",
                identification_confidence=0.92,
                bbox=(0.1, 0.2, 0.3, 0.4),
                grams=150.0,
                portion_is_approximate=True,
                source="bedrock_vision",
            ),
            FoodItem(label="rice", identification_confidence=0.8),
        ),
        macros=MacroBreakdown(
            calories_kcal=450.0,
            protein_g=35.0,
            carbs_g=40.0,
            fat_g=10.0,
            sugar_g=1.0,
            source="usda_fdc:167512",
        ),
        safety_result=SafetyResult(
            verdict=SafetyVerdict.NO_CONFLICT_DETECTED,
            allergen_findings=(),
            explanation="No allergens detected in identified foods.",
            macro_notes=("within daily sugar limit",),
            evidence_refs=("usda_fdc:167512",),
        ),
    )


def _sample_profile(user_id: str = "user-1") -> UserProfile:
    return UserProfile(
        user_id=user_id,
        display_name="Test User",
        allergies=(
            AllergyEntry(
                allergen=AllergenTag.PEANUT,
                severity=AllergySeverity.ANAPHYLAXIS,
                notes="carries epi-pen",
            ),
        ),
        daily_sugar_limit_g=25.0,
        notes="test profile",
    )


class TestMealRoundTrip:
    def test_log_and_get_meal_round_trip(self, dynamodb_tables: None) -> None:
        from nutriguard.data.repository import get_meal, log_meal

        meal = _sample_meal()
        log_meal(meal)

        fetched = get_meal(user_id="user-1", meal_id="meal-1")

        assert fetched == meal

    def test_get_meal_returns_none_when_missing(self, dynamodb_tables: None) -> None:
        from nutriguard.data.repository import get_meal

        assert get_meal(user_id="nobody", meal_id="nothing") is None


class TestProfileRoundTrip:
    def test_save_and_get_profile_round_trip(self, dynamodb_tables: None) -> None:
        from nutriguard.data.repository import get_profile, save_profile

        profile = _sample_profile()
        save_profile(profile)

        fetched = get_profile(user_id="user-1")

        assert fetched == profile
        assert fetched is not None
        assert fetched.allergies[0].allergen == AllergenTag.PEANUT

    def test_get_profile_returns_none_when_missing(self, dynamodb_tables: None) -> None:
        from nutriguard.data.repository import get_profile

        assert get_profile(user_id="nobody") is None


class TestFailureBehavior:
    def test_log_meal_raises_typed_error_when_table_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A write against a nonexistent table must raise a typed exception,
        not a bare Exception, and must not silently swallow the failure."""
        from nutriguard.data.repository import RepositoryWriteError, log_meal

        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
        monkeypatch.setenv("NUTRIGUARD_MEALS_TABLE", "table-that-does-not-exist")

        with mock_aws():
            with pytest.raises(RepositoryWriteError):
                log_meal(_sample_meal())


def test_no_hardcoded_resource_identifiers() -> None:
    """Guard against literal table names/ARNs/bucket names in the module
    source. Resource identifiers must come from env vars or SSM only."""
    import inspect

    from nutriguard.data import repository

    source = inspect.getsource(repository)
    forbidden_literals = [
        "arn:aws:",
        '"nutriguard-meals"',
        '"nutriguard-profiles"',
    ]
    for literal in forbidden_literals:
        assert literal not in source, f"found forbidden hardcoded literal: {literal}"
