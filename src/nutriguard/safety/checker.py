"""Safety verdict composer (P2-05).

`check_safety` is the single place that turns the deterministic allergen
engine's output (`check_allergens`, P2-07), a pre-aggregated macro total,
and (optionally) simulated knowledge-base evidence into the one
`SafetyResult` shown to the user.

Precedence is read from `SAFETY_VERDICT_PRECEDENCE` in the frozen domain
contract, not hardcoded here - see `_evaluate_conditions` below. If that
tuple's order ever changes, this module's behavior changes with it
automatically; nothing in this file re-declares "allergen beats macro
caution" as its own fact.

Non-diagnostic language: every explanation string produced here is
plain-language and describes what was checked, not a medical directive.
No explanation ever tells the user to take, dose, or apply a treatment,
and no explanation ever claims a meal is "safe" or "allergen-free" - the
domain contract's `SafetyVerdict` deliberately has no such variant,
because a photo cannot rule out hidden ingredients.
"""

from __future__ import annotations

from nutriguard.domain.models import (
    SAFETY_VERDICT_PRECEDENCE,
    AllergenFinding,
    FoodItem,
    MacroBreakdown,
    SafetyResult,
    SafetyVerdict,
    UserProfile,
)
from nutriguard.safety.allergens import _ALLERGEN_MAP, _contains_term, _normalize, check_allergens

#: Below this identification confidence, a food that merely *resembles* an
#: allergen-bearing term (even with no confirmed profile match) is treated
#: as unverifiable rather than cleared. Deliberately conservative per the
#: task spec: "favor CANNOT_VERIFY rather than clever."
_CANNOT_VERIFY_CONFIDENCE_THRESHOLD = 0.5


def _is_plausible_allergen_bearing(label: str) -> bool:
    """Heuristic: does `label` resemble ANY term in the allergen reference map?

    This checks against every allergen's direct/alias/category term lists
    in `allergens._ALLERGEN_MAP` - not just the allergens on the user's
    profile. The intent is narrow: "this food's name resembles something
    that is *sometimes* allergen-bearing, so a low-confidence
    identification of it is worth flagging as unverifiable" - it is not a
    claim that the food matches the user's specific allergies (that
    determination is `check_allergens`'s job and always takes precedence).

    Deliberately simple and over-inclusive by design: a false positive
    here just means an extra CANNOT_VERIFY on a low-confidence food, which
    is the conservative failure mode this heuristic is supposed to have.
    """
    normalized_label = _normalize(label)
    for entry in _ALLERGEN_MAP.values():
        for term in (*entry.direct, *entry.aliases, *entry.categories):
            if _contains_term(normalized_label, term):
                return True
    return False


def _low_confidence_plausible_allergen_foods(foods: list[FoodItem]) -> list[FoodItem]:
    """Foods below the confidence threshold that also look allergen-bearing.

    Iterates the raw `foods` list (never a `get_macros`-style dict keyed
    by label) so that two items sharing a label are both considered - the
    same reason the composer must not build its own per-item correlation
    off of `get_macros`'s return value (see the macros.py known
    label-collision issue carried forward from Wave 1).
    """
    return [
        food
        for food in foods
        if food.identification_confidence < _CANNOT_VERIFY_CONFIDENCE_THRESHOLD
        and _is_plausible_allergen_bearing(food.label)
    ]


def _sugar_exceeds_limit(meal_macros: MacroBreakdown, profile: UserProfile) -> bool:
    """True only when both a measured sugar total and a set limit exist and it's over."""
    if meal_macros.sugar_g is None:
        return False
    if profile.daily_sugar_limit_g is None:
        return False
    return meal_macros.sugar_g > profile.daily_sugar_limit_g


def _explain_allergen_conflict(findings: tuple[AllergenFinding, ...]) -> str:
    """Non-diagnostic explanation for ALLERGEN_CONFLICT.

    Names the allergen, matched food, and severity for each finding, and
    ends with a direction to verify independently - never a treatment
    instruction (no medication names, no dosing, no medical directives).
    """
    per_finding = [
        f'possible {finding.allergen.value} ({finding.severity.value}) in "{finding.matched_food}"'
        for finding in findings
    ]
    joined = "; ".join(per_finding)
    return (
        f"Allergen conflict detected against your profile: {joined}. "
        "This is a match against your listed profile, not a medical determination - "
        "please confirm with your doctor or a trusted label check before eating."
    )


def _explain_cannot_verify(uncertain_foods: list[FoodItem]) -> str:
    """Non-diagnostic explanation for CANNOT_VERIFY.

    Explicitly states the system could not confirm from the photo alone,
    and that hidden ingredients are possible - this is the point of the
    verdict, so the wording says so directly rather than implying it.
    """
    labels = ", ".join(f'"{food.label}"' for food in uncertain_foods)
    return (
        f"The system could not confirm from the photo alone whether {labels} conflicts with "
        "your profile - identification confidence was too low to be sure, and hidden "
        "ingredients are possible. Please confirm with your doctor or a trusted label check "
        "before eating."
    )


def _explain_macro_caution(meal_macros: MacroBreakdown, profile: UserProfile) -> str:
    """Non-diagnostic explanation for MACRO_CAUTION.

    Still reminds the user that no conflict was detected against their
    allergy profile specifically, and that a photo cannot rule out hidden
    ingredients - the sugar caution does not imply anything stronger about
    allergen safety.
    """
    sugar_g = meal_macros.sugar_g
    limit_g = profile.daily_sugar_limit_g
    assert sugar_g is not None and limit_g is not None  # guaranteed by _sugar_exceeds_limit
    return (
        f"This meal's sugar content ({sugar_g:.1f}g) exceeds your daily sugar limit "
        f"({limit_g:.1f}g). No conflict was detected against your allergy profile, but a "
        "photo cannot rule out hidden ingredients."
    )


def _explain_no_conflict_detected() -> str:
    """Non-diagnostic explanation for NO_CONFLICT_DETECTED.

    Deliberately never says "safe" or "allergen-free" - it states what was
    checked (no conflict detected against the profile) and explicitly
    flags what a photo cannot do (rule out hidden ingredients), matching
    the domain contract's design rule.
    """
    return (
        "No conflict was detected against your profile. A photo cannot rule out hidden "
        "ingredients, so this is not a guarantee - use a trusted label check if you want to "
        "be certain."
    )


def _build_macro_notes(meal_macros: MacroBreakdown, profile: UserProfile) -> tuple[str, ...]:
    """Structured (non-prose) macro notes, populated only when sugar is over the limit."""
    if not _sugar_exceeds_limit(meal_macros, profile):
        return ()
    sugar_g = meal_macros.sugar_g
    limit_g = profile.daily_sugar_limit_g
    assert sugar_g is not None and limit_g is not None
    return (f"sugar_g={sugar_g:.1f} exceeds daily_sugar_limit_g={limit_g:.1f}",)


def _select_verdict(
    *,
    has_allergen_findings: bool,
    has_uncertain_foods: bool,
    sugar_exceeds: bool,
) -> SafetyVerdict:
    """Pick the winning verdict by walking `SAFETY_VERDICT_PRECEDENCE` in order.

    This is the mechanism that keeps precedence data-driven: each verdict's
    trigger condition is computed independently above, then the *first*
    verdict in `SAFETY_VERDICT_PRECEDENCE` whose condition holds wins. If
    the domain contract's tuple order ever changes, this function's
    behavior changes with it - nothing here re-encodes "allergen conflict
    beats everything else" as a separate fact.

    `NO_CONFLICT_DETECTED`'s condition is unconditionally `True`, which is
    safe only because it is the last entry in `SAFETY_VERDICT_PRECEDENCE`;
    it is the fallback that is reached when nothing higher-precedence
    triggered.
    """
    conditions: dict[SafetyVerdict, bool] = {
        SafetyVerdict.ALLERGEN_CONFLICT: has_allergen_findings,
        SafetyVerdict.CANNOT_VERIFY: has_uncertain_foods,
        SafetyVerdict.MACRO_CAUTION: sugar_exceeds,
        SafetyVerdict.NO_CONFLICT_DETECTED: True,
    }
    for verdict in SAFETY_VERDICT_PRECEDENCE:
        if conditions.get(verdict, False):
            return verdict
    # Unreachable as long as NO_CONFLICT_DETECTED (condition True) is a
    # member of SAFETY_VERDICT_PRECEDENCE, which the domain contract
    # guarantees.
    raise AssertionError("no verdict in SAFETY_VERDICT_PRECEDENCE matched any condition")


def check_safety(
    foods: list[FoodItem],
    profile: UserProfile,
    meal_macros: MacroBreakdown,
    kb_evidence: list[str] | None = None,
) -> SafetyResult:
    """Compose the top-level safety verdict shown to the user.

    `check_allergens` is the deterministic core and always runs first,
    unconditionally - nothing below can prevent it from running or
    override an allergen match once found. This function then layers a
    conservative "unverifiable" heuristic and a macro caution check on
    top, resolved by precedence order from `SAFETY_VERDICT_PRECEDENCE`
    (see `_select_verdict`).

    Args:
        foods: Identified food items for this meal. Passed straight
            through to `check_allergens` and used (as the raw list, not a
            label-keyed dict) for the CANNOT_VERIFY confidence heuristic.
            Callers should note the known `get_macros` label-collision
            issue: this function intentionally never derives its own
            per-item macro correlation from a `get_macros`-style dict; it
            only consumes the already-aggregated `meal_macros` total,
            which the caller is expected to have built via
            `aggregate_macros(get_macros(foods))`.
        profile: The user's structured profile (allergies + optional daily
            sugar limit).
        meal_macros: The meal-level aggregated `MacroBreakdown` (e.g. from
            `nutrition.macros.aggregate_macros`). Only `sugar_g` is
            consulted here, per the Gate A macro-caution rule.
        kb_evidence: Optional list of evidence strings simulating a
            knowledge-base retrieval step (the real Bedrock Knowledge Base
            is not wired up yet in Gate A). When `None` or empty - which
            simulates a retrieval failure - this function's verdict and
            explanation logic are completely unaffected: only deterministic
            allergen/macro logic decides the verdict, and `evidence_refs`
            on the result is simply empty. Retrieval succeeding or failing
            must never weaken or strengthen a safety claim.

    Returns:
        A `SafetyResult` with `verdict` chosen per
        `SAFETY_VERDICT_PRECEDENCE`, the full list of `allergen_findings`
        from `check_allergens` (always populated regardless of which
        verdict wins), a non-diagnostic `explanation`, `macro_notes`
        (only non-empty for `MACRO_CAUTION`), and `evidence_refs` set from
        `kb_evidence` (or empty when none was supplied).
    """
    # Deterministic allergen core - always runs first, no matter what else
    # follows or fails.
    findings = tuple(check_allergens(foods, profile))

    uncertain_foods = _low_confidence_plausible_allergen_foods(foods) if not findings else []
    sugar_exceeds = _sugar_exceeds_limit(meal_macros, profile) if not findings else False

    verdict = _select_verdict(
        has_allergen_findings=bool(findings),
        has_uncertain_foods=bool(uncertain_foods),
        sugar_exceeds=sugar_exceeds,
    )

    explanation: str
    macro_notes: tuple[str, ...] = ()
    if verdict == SafetyVerdict.ALLERGEN_CONFLICT:
        explanation = _explain_allergen_conflict(findings)
    elif verdict == SafetyVerdict.CANNOT_VERIFY:
        explanation = _explain_cannot_verify(uncertain_foods)
    elif verdict == SafetyVerdict.MACRO_CAUTION:
        explanation = _explain_macro_caution(meal_macros, profile)
        macro_notes = _build_macro_notes(meal_macros, profile)
    else:
        explanation = _explain_no_conflict_detected()

    # kb_evidence is attached as-is; a None/empty retrieval never changes
    # anything computed above.
    evidence_refs: tuple[str, ...] = tuple(kb_evidence) if kb_evidence else ()

    return SafetyResult(
        verdict=verdict,
        allergen_findings=findings,
        explanation=explanation,
        macro_notes=macro_notes,
        evidence_refs=evidence_refs,
    )
