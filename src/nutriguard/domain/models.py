"""Frozen domain contract for the Person 2 (vision/nutrition/safety/data) slice.

These types are the shared interface between this slice, Person 1's AgentCore
tool wrappers, and Person 3's UI fixtures. Once committed, this file is
READ-ONLY for downstream sub-agents. A needed change escalates to the
controller rather than being edited directly, because every other file in
this slice is dispatched to a sub-agent under the assumption this contract
will not move under it.

Design rules enforced by these types:
- Never invent nutrition values: absent data is `None`, not a guess.
- Allergen detection is deterministic and structured; free-text allergies
  are not accepted (`UserProfile.allergies` is a tuple of `AllergyEntry`).
- Portion estimates always carry an explicit uncertainty flag.
- Safety verdicts never use the word "safe" - `NO_CONFLICT_DETECTED` says
  what was checked, not what is guaranteed, because a photo cannot reveal
  hidden ingredients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class AllergenTag(StrEnum):
    """FDA "Big 9" major food allergens."""

    MILK = "milk"
    EGG = "egg"
    FISH = "fish"
    CRUSTACEAN_SHELLFISH = "crustacean_shellfish"
    TREE_NUT = "tree_nut"
    PEANUT = "peanut"
    WHEAT = "wheat"
    SOY = "soy"
    SESAME = "sesame"


class AllergySeverity(StrEnum):
    """Clinical severity, used to drive message urgency only - never diagnosis."""

    INTOLERANCE = "intolerance"
    ALLERGY = "allergy"
    ANAPHYLAXIS = "anaphylaxis"


class SafetyVerdict(StrEnum):
    """Outcome of a meal safety check.

    Deliberately excludes any variant meaning "safe" or "allergen-free" -
    a meal photo cannot rule out hidden ingredients (e.g. peanut in a sauce),
    so the best the system can assert is that no conflict was *detected*.
    """

    ALLERGEN_CONFLICT = "allergen_conflict"
    MACRO_CAUTION = "macro_caution"
    NO_CONFLICT_DETECTED = "no_conflict_detected"
    CANNOT_VERIFY = "cannot_verify"


# Verdict precedence, highest first. Used by the safety composer (P2-05) to
# resolve which verdict wins when multiple conditions are true at once.
SAFETY_VERDICT_PRECEDENCE: tuple[SafetyVerdict, ...] = (
    SafetyVerdict.ALLERGEN_CONFLICT,
    SafetyVerdict.CANNOT_VERIFY,
    SafetyVerdict.MACRO_CAUTION,
    SafetyVerdict.NO_CONFLICT_DETECTED,
)


@dataclass(frozen=True, slots=True)
class FoodItem:
    """A single identified food item, with optional portion/confidence data.

    `identification_confidence` is required because every downstream safety
    decision needs to know how sure the vision step was. `grams` and
    `portion_is_approximate` are optional because they are filled in by the
    portion-estimation step (P2-03), not the identification step (P2-02).
    """

    label: str
    identification_confidence: float  # 0.0-1.0
    bbox: tuple[float, float, float, float] | None = None  # x, y, w, h (normalized)
    grams: float | None = None
    portion_is_approximate: bool = True
    source: Literal["fixture", "bedrock_vision", "local_model"] = "fixture"

    def __post_init__(self) -> None:
        if not 0.0 <= self.identification_confidence <= 1.0:
            raise ValueError(
                f"identification_confidence must be in [0.0, 1.0], "
                f"got {self.identification_confidence}"
            )
        if self.grams is not None and self.grams < 0:
            raise ValueError(f"grams must be non-negative, got {self.grams}")


@dataclass(frozen=True, slots=True)
class MacroBreakdown:
    """Macro/calorie totals for a food item or an entire meal.

    Every field is `None` when the source data does not have it - never a
    fabricated estimate. `sugar_g` is always broken out as its own field
    per the Gate A dashboard requirement (sugar is highlighted separately).
    """

    calories_kcal: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    sugar_g: float | None
    source: str  # e.g. "usda_fdc:167512" or "unknown"

    def __post_init__(self) -> None:
        for field_name in ("calories_kcal", "protein_g", "carbs_g", "fat_g", "sugar_g"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative, got {value}")


@dataclass(frozen=True, slots=True)
class AllergyEntry:
    """One structured allergy/intolerance entry on a user profile.

    Structured, not free text - free-text allergy entry is how allergens
    get missed by naive string matching.
    """

    allergen: AllergenTag
    severity: AllergySeverity
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UserProfile:
    """A user's structured profile. No medical-document parsing in Gate A."""

    user_id: str
    display_name: str
    allergies: tuple[AllergyEntry, ...] = field(default_factory=tuple)
    daily_sugar_limit_g: float | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("user_id must not be empty")
        allergens_seen = [entry.allergen for entry in self.allergies]
        if len(allergens_seen) != len(set(allergens_seen)):
            raise ValueError("duplicate allergen entries in profile")


@dataclass(frozen=True, slots=True)
class AllergenFinding:
    """One deterministic allergen match between identified foods and a profile.

    Produced only by the pure-function rule engine (P2-07) - never by an
    LLM or a retrieval step. `identification_confidence` is carried through
    so the safety composer can distinguish a confident match from a
    possible match riding on an uncertain identification.
    """

    allergen: AllergenTag
    severity: AllergySeverity
    matched_food: str
    match_basis: Literal["direct", "alias", "category"]
    identification_confidence: float
    evidence_source: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.identification_confidence <= 1.0:
            raise ValueError(
                f"identification_confidence must be in [0.0, 1.0], "
                f"got {self.identification_confidence}"
            )


@dataclass(frozen=True, slots=True)
class SafetyResult:
    """Composed output of the safety check (P2-05).

    `verdict` follows `SAFETY_VERDICT_PRECEDENCE`. `explanation` must never
    contain diagnosis or treatment language - that is a hard test
    requirement, not a style preference.
    """

    verdict: SafetyVerdict
    allergen_findings: tuple[AllergenFinding, ...]
    explanation: str
    macro_notes: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class MealRecord:
    """A logged meal, as persisted by the data layer (P2-06)."""

    meal_id: str
    user_id: str
    logged_at_iso: str
    foods: tuple[FoodItem, ...]
    macros: MacroBreakdown
    safety_result: SafetyResult
