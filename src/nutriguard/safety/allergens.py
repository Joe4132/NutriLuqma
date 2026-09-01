"""Deterministic allergen detection engine (P2-07).

WHY THIS IS DETERMINISTIC AND NOT LLM-BASED:
A missed allergen here is a safety failure, not a quality bug. LLMs are
probabilistic - the same input can, in principle, produce a different
output on a different call (sampling, model version drift, provider-side
changes, latency-driven retries hitting a different replica, etc.), and
they can silently omit a match that a strict term lookup would catch.
That non-reproducibility is unacceptable for a "does this food contain
something that could kill this specific user" check. `check_allergens`
is therefore a pure function over a static, version-controlled lookup
table (`src/nutriguard/data/allergen_map.json`): same inputs always
produce the same outputs, byte-for-byte, with no network calls, no LLM
calls, and no clock/random/env access. This module intentionally does
NOT import `requests`, `boto3`, `urllib`, or any LLM client - there is
nothing in this file that could reach the network, which is itself part
of the safety property being enforced (see
`test_module_has_no_network_dependency` in tests/test_allergens.py).

Downstream (P2-05, the safety composer) is responsible for turning a
low-confidence finding into cautious language. This module's only job is
to never hide a possible match, regardless of how confident the upstream
vision step was.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from nutriguard.domain.models import (
    AllergenFinding,
    AllergenTag,
    FoodItem,
    UserProfile,
)

MatchBasis = Literal["direct", "alias", "category"]

#: Path to the committed allergen reference data. Resolved relative to this
#: file (not the current working directory) so the module works regardless
#: of where the process is launched from.
_ALLERGEN_MAP_PATH = Path(__file__).resolve().parent.parent / "data" / "allergen_map.json"


class AllergenMapEntry:
    """Typed view of one allergen's entry in the reference map."""

    __slots__ = ("aliases", "categories", "direct")

    def __init__(self, direct: list[str], aliases: list[str], categories: list[str]) -> None:
        self.direct = direct
        self.aliases = aliases
        self.categories = categories


def _load_allergen_map(path: Path = _ALLERGEN_MAP_PATH) -> dict[AllergenTag, AllergenMapEntry]:
    """Load and parse the static allergen reference data.

    This is the only file I/O in this module. It reads a file that is
    committed to the repository (not fetched, not generated at runtime),
    so the result is fixed for a given checkout and does not affect the
    determinism guarantee of `check_allergens`. Loaded once at import
    time into `_ALLERGEN_MAP` below.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    parsed: dict[AllergenTag, AllergenMapEntry] = {}
    for key, value in raw.items():
        tag = AllergenTag(key)
        parsed[tag] = AllergenMapEntry(
            direct=list(value.get("direct", [])),
            aliases=list(value.get("aliases", [])),
            categories=list(value.get("categories", [])),
        )
    return parsed


#: Loaded once at import time; treated as immutable for the lifetime of the
#: process. `check_allergens` never mutates this.
_ALLERGEN_MAP: dict[AllergenTag, AllergenMapEntry] = _load_allergen_map()


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for case/format-insensitive matching."""
    return " ".join(text.strip().lower().split())


def _contains_term(normalized_label: str, term: str) -> bool:
    """Return True if `term` appears in `normalized_label` on word boundaries.

    Plain substring containment would let "almond" wrongly match inside
    "salmon" is avoided by anchoring on non-alphanumeric boundaries; this
    still allows multi-word terms (e.g. "peanut butter") to match as a
    contiguous phrase within a longer label.
    """
    pattern = r"(?<![a-z0-9])" + re.escape(_normalize(term)) + r"(?![a-z0-9])"
    return re.search(pattern, normalized_label) is not None


def _match_basis(normalized_label: str, entry: AllergenMapEntry) -> MatchBasis | None:
    """Determine how (if at all) a food label matches one allergen's entry.

    Checked in order of specificity: direct label match first, then a
    hidden-source alias, then a coarse category hint. The first basis
    that matches is returned - a label is not double-counted against the
    same allergen under multiple bases.
    """
    for term in entry.direct:
        if _contains_term(normalized_label, term):
            return "direct"
    for term in entry.aliases:
        if _contains_term(normalized_label, term):
            return "alias"
    for term in entry.categories:
        if _contains_term(normalized_label, term):
            return "category"
    return None


def check_allergens(foods: list[FoodItem], profile: UserProfile) -> list[AllergenFinding]:
    """Deterministically match identified foods against a user's allergy profile.

    Pure function: no network calls, no LLM calls, no randomness, no clock
    access, and no I/O beyond the static reference table loaded once at
    import time. Calling this twice with the same `foods` and `profile`
    always returns an equal (and, for these dataclass/list-of-dataclass
    types, order-and-value-identical) result.

    Args:
        foods: Identified foods for a meal, in the order they were
            identified. Order of the input is preserved in the output
            (findings are emitted per food, in input order).
        profile: The user's structured allergy profile. Only allergens
            present in `profile.allergies` are ever checked.

    Returns:
        A list of `AllergenFinding`, one per (food, allergen) pair that
        matched, in the order foods were supplied and allergies were
        listed on the profile. Empty if no food matches any allergy on
        the profile. `identification_confidence` on each finding is
        copied unchanged from the source `FoodItem` - this function never
        adjusts confidence up or down, and it never drops a match because
        confidence was low. Deciding how to phrase uncertainty is the
        caller's responsibility, not this function's.
    """
    if not profile.allergies:
        return []

    findings: list[AllergenFinding] = []
    for food in foods:
        normalized_label = _normalize(food.label)
        for allergy_entry in profile.allergies:
            entry = _ALLERGEN_MAP.get(allergy_entry.allergen)
            if entry is None:
                # Allergen tag has no reference data; nothing to match against.
                continue
            basis = _match_basis(normalized_label, entry)
            if basis is None:
                continue
            findings.append(
                AllergenFinding(
                    allergen=allergy_entry.allergen,
                    severity=allergy_entry.severity,
                    matched_food=food.label,
                    match_basis=basis,
                    identification_confidence=food.identification_confidence,
                    evidence_source=f"allergen_map:{allergy_entry.allergen.value}:{basis}",
                )
            )
    return findings
