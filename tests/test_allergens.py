"""Tests for the deterministic allergen engine (P2-07).

Safety-critical: a missed allergen is a safety failure, not a quality bug.
These tests exist to prove `check_allergens` is a pure, deterministic
function that never silently drops a possible match, even when the
upstream vision identification confidence is low.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from nutriguard.domain.models import (
    AllergenTag,
    AllergyEntry,
    AllergySeverity,
    FoodItem,
    UserProfile,
)
from nutriguard.safety.allergens import _ALLERGEN_MAP_PATH, check_allergens

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _profile_with(*entries: AllergyEntry, user_id: str = "test-user") -> UserProfile:
    return UserProfile(user_id=user_id, display_name="Test User", allergies=tuple(entries))


# --------------------------------------------------------------------------
# Direct match
# --------------------------------------------------------------------------


def test_direct_match_peanut() -> None:
    foods = [FoodItem(label="peanuts", identification_confidence=0.95)]
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS)
    )
    findings = check_allergens(foods, profile)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.allergen == AllergenTag.PEANUT
    assert finding.match_basis == "direct"
    assert finding.matched_food == "peanuts"
    assert finding.identification_confidence == 0.95
    assert finding.severity == AllergySeverity.ANAPHYLAXIS


# --------------------------------------------------------------------------
# Alias / hidden-source match
# --------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["casein", "whey protein shake", "lactose powder"])
def test_alias_match_milk_hidden_source(label: str) -> None:
    foods = [FoodItem(label=label, identification_confidence=0.8)]
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.MILK, severity=AllergySeverity.INTOLERANCE)
    )
    findings = check_allergens(foods, profile)
    assert len(findings) == 1
    assert findings[0].allergen == AllergenTag.MILK
    assert findings[0].match_basis == "alias"


def test_alias_match_wheat_semolina() -> None:
    foods = [FoodItem(label="semolina pudding", identification_confidence=0.7)]
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.WHEAT, severity=AllergySeverity.ALLERGY)
    )
    findings = check_allergens(foods, profile)
    assert len(findings) == 1
    assert findings[0].match_basis == "alias"


def test_alias_match_sesame_tahini() -> None:
    foods = [FoodItem(label="tahini dip", identification_confidence=0.6)]
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.SESAME, severity=AllergySeverity.ALLERGY)
    )
    findings = check_allergens(foods, profile)
    assert len(findings) == 1
    assert findings[0].match_basis == "alias"


# --------------------------------------------------------------------------
# Category match
# --------------------------------------------------------------------------


def test_category_match_seafood_implies_fish_risk() -> None:
    foods = [FoodItem(label="seafood platter", identification_confidence=0.5)]
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.FISH, severity=AllergySeverity.ALLERGY)
    )
    findings = check_allergens(foods, profile)
    assert len(findings) == 1
    assert findings[0].match_basis == "category"


# --------------------------------------------------------------------------
# No false positives
# --------------------------------------------------------------------------


def test_no_match_returns_empty_list() -> None:
    foods = [
        FoodItem(label="grilled chicken", identification_confidence=0.9),
        FoodItem(label="white rice", identification_confidence=0.95),
    ]
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS)
    )
    assert check_allergens(foods, profile) == []


def test_no_allergies_on_profile_returns_empty_list() -> None:
    foods = [FoodItem(label="peanut butter sandwich", identification_confidence=0.9)]
    profile = _profile_with()
    assert check_allergens(foods, profile) == []


def test_empty_foods_returns_empty_list() -> None:
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS)
    )
    assert check_allergens([], profile) == []


# --------------------------------------------------------------------------
# Low confidence must never be silently dropped
# --------------------------------------------------------------------------


def test_low_confidence_identification_still_flags_match() -> None:
    """A low-confidence peanut identification must still produce a finding.

    Hiding a possible allergen because the vision step was unsure is a
    safety failure - deciding how to phrase that uncertainty belongs to
    the caller downstream, not to this function.
    """
    foods = [FoodItem(label="peanut sauce", identification_confidence=0.4)]
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS)
    )
    findings = check_allergens(foods, profile)
    assert len(findings) == 1
    assert findings[0].identification_confidence == 0.4
    assert findings[0].allergen == AllergenTag.PEANUT


# --------------------------------------------------------------------------
# Confidence passthrough (not inflated or deflated)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("confidence", [0.0, 0.1, 0.5, 0.99, 1.0])
def test_confidence_is_carried_through_unchanged(confidence: float) -> None:
    foods = [FoodItem(label="peanuts", identification_confidence=confidence)]
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS)
    )
    findings = check_allergens(foods, profile)
    assert findings[0].identification_confidence == confidence


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_determinism_repeated_calls_are_byte_identical() -> None:
    foods = [
        FoodItem(label="peanut sauce", identification_confidence=0.4),
        FoodItem(label="grilled salmon", identification_confidence=0.85),
        FoodItem(label="casein protein bar", identification_confidence=0.6),
    ]
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.PEANUT, severity=AllergySeverity.ANAPHYLAXIS),
        AllergyEntry(allergen=AllergenTag.MILK, severity=AllergySeverity.INTOLERANCE),
    )
    first = check_allergens(foods, profile)
    second = check_allergens(foods, profile)
    assert first == second
    # "Byte-identical" for our purposes: identical JSON serialization of the
    # findings, which requires identical field values and identical order.
    encode = lambda findings: json.dumps(
        [
            {
                "allergen": f.allergen.value,
                "severity": f.severity.value,
                "matched_food": f.matched_food,
                "match_basis": f.match_basis,
                "identification_confidence": f.identification_confidence,
                "evidence_source": f.evidence_source,
            }
            for f in findings
        ]
    )
    assert encode(first) == encode(second)


def test_determinism_many_repeated_calls() -> None:
    foods = [FoodItem(label="shrimp cocktail", identification_confidence=0.77)]
    profile = _profile_with(
        AllergyEntry(allergen=AllergenTag.CRUSTACEAN_SHELLFISH, severity=AllergySeverity.ALLERGY)
    )
    results = [check_allergens(foods, profile) for _ in range(10)]
    assert all(result == results[0] for result in results)


# --------------------------------------------------------------------------
# No network/LLM dependency (safety property, not just a style preference)
# --------------------------------------------------------------------------


def test_module_has_no_network_dependency() -> None:
    """Statically prove allergens.py never imports a network/LLM client.

    Parses the module source with `ast` (rather than just grepping text)
    so the check is robust to comments/strings that happen to mention
    these names, and inspects only real `import` / `from ... import`
    statements.
    """
    source_path = Path(__file__).parent.parent / "src" / "nutriguard" / "safety" / "allergens.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    forbidden_modules = {"requests", "boto3", "urllib", "httpx", "aiohttp", "socket"}
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    offenders = imported_roots & forbidden_modules
    assert not offenders, f"allergens.py must not import network/LLM modules, found: {offenders}"


# --------------------------------------------------------------------------
# Big 9 coverage
# --------------------------------------------------------------------------


def test_allergen_map_covers_all_big9_with_direct_and_alias_entries() -> None:
    raw = json.loads(_ALLERGEN_MAP_PATH.read_text(encoding="utf-8"))
    for tag in AllergenTag:
        assert tag.value in raw, f"missing allergen map entry for {tag.value}"
        entry = raw[tag.value]
        assert entry.get("direct"), f"{tag.value} has no direct matches"
        assert entry.get("aliases"), f"{tag.value} has no alias matches"


# --------------------------------------------------------------------------
# Fixture profiles integration
# --------------------------------------------------------------------------


def test_fixture_peanut_anaphylaxis_profile_flags_peanut_food() -> None:
    data = json.loads((FIXTURES_DIR / "profiles.json").read_text())
    payload = next(p for p in data["valid"] if p["user_id"] == "demo-user-1")
    profile = UserProfile(
        user_id=payload["user_id"],
        display_name=payload["display_name"],
        allergies=tuple(
            AllergyEntry(
                allergen=AllergenTag(entry["allergen"]),
                severity=AllergySeverity(entry["severity"]),
                notes=entry["notes"],
            )
            for entry in payload["allergies"]
        ),
        daily_sugar_limit_g=payload["daily_sugar_limit_g"],
        notes=payload["notes"],
    )
    foods = [FoodItem(label="pad thai with peanut sauce", identification_confidence=0.6)]
    findings = check_allergens(foods, profile)
    assert len(findings) == 1
    assert findings[0].allergen == AllergenTag.PEANUT
    assert findings[0].severity == AllergySeverity.ANAPHYLAXIS


def test_fixture_milk_intolerance_profile_flags_hidden_dairy() -> None:
    data = json.loads((FIXTURES_DIR / "profiles.json").read_text())
    payload = next(p for p in data["valid"] if p["user_id"] == "demo-user-2")
    profile = UserProfile(
        user_id=payload["user_id"],
        display_name=payload["display_name"],
        allergies=tuple(
            AllergyEntry(
                allergen=AllergenTag(entry["allergen"]),
                severity=AllergySeverity(entry["severity"]),
                notes=entry["notes"],
            )
            for entry in payload["allergies"]
        ),
        daily_sugar_limit_g=payload["daily_sugar_limit_g"],
        notes=payload["notes"],
    )
    foods = [FoodItem(label="protein bar with whey", identification_confidence=0.7)]
    findings = check_allergens(foods, profile)
    assert len(findings) == 1
    assert findings[0].allergen == AllergenTag.MILK
    assert findings[0].match_basis == "alias"
