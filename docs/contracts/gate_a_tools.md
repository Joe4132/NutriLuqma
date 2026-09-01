# Gate A — Frozen Tool Interface Contract

> **Status: FROZEN** — published at T+0:20 per `PERSON1_GATE_A_PLAN.md §3`.
> Renaming any field requires agreement from all three persons. Do not edit unilaterally.
> Person 2: implement these exact field names in `nutriguard/src/nutriguard/`.
> Person 3: build your UI against this shape.
> Person 1: your `@tool` wrappers normalise to this shape before returning.

---

## Function Signatures

```python
identify_food(image_path: str) -> list[FoodItem]
estimate_portion(image_path: str, foods: list[FoodItem]) -> list[FoodItem]
get_macros(foods: list[FoodItem]) -> MacroBreakdown
check_safety(meal: MacroBreakdown, profile: UserProfile) -> SafetyResult
log_meal(user_id: str, meal: MealRecord) -> None
get_profile(user_id: str) -> UserProfile
suggest_recipe(profile: UserProfile, remaining: MacroBreakdown) -> Recipe   # optional — cut first per §8
```

---

## Type Shapes

All field names below are frozen. Missing source data returns the string `"unknown"`, never a guess or `None` substituted silently.

### FoodItem

```
label          : str            # human-readable food name
confidence     : float          # 0.0–1.0; below 0.60 no "ok" allergen verdict is possible
grams          : float | None   # estimated portion weight; None when unknown
is_approximate : bool           # true when grams is an estimate or the dish is composite
bbox           : list[float] | None  # [x, y, w, h] normalised 0–1; None when not available
```

### MacroBreakdown

```
calories   : float | "unknown"
protein_g  : float | "unknown"
carbs_g    : float | "unknown"
fat_g      : float | "unknown"
sugar_g    : float | "unknown"
items      : list[FoodItem]
source     : str   # e.g. "usda", "stub", "kb" — never omitted
```

### SafetyResult

```
status              : "ok" | "caution" | "conflict"
reasons             : list[str]
evidence            : list[str]
disclaimer          : str          # always present, always non-diagnostic
allergen_conflicts  : list[AllergenConflict]   # empty list is a valid answer; missing key is a bug
```

### AllergenConflict

```
allergen      : str                                        # exactly as listed in UserProfile.allergies
matched_food  : str                                        # the FoodItem.label that triggered the match
match_type    : "direct" | "alias" | "unverifiable"
confidence    : float
```

### UserProfile

```
user_id             : str
allergies           : list[str]
conditions          : list[str]
daily_sugar_limit_g : float | None
notes               : str
```

### MealRecord

```
meal_id    : str
user_id    : str
timestamp  : str   # ISO 8601
macros     : MacroBreakdown
image_key  : str | None   # S3 key; None when no image was uploaded
```

### Recipe (optional, Gate A only if §6 is fully green)

```
title        : str
ingredients  : list[str]
instructions : list[str]
macros       : MacroBreakdown
```

---

## Contract Rules (baked into every wrapper)

1. Missing source data → return `"unknown"`, never invent a number.
2. `SafetyResult.disclaimer` must always be present and always non-diagnostic.
3. `SafetyResult.allergen_conflicts` must always be present. An empty list `[]` is a valid answer. A missing key is a bug.
4. No wrapper may return the words "safe", "safe to eat", or "allergen-free" in any field.
5. The allergen verdict is computed deterministically by `app/allergy_gate.py`, not by the model.
6. `source` on `MacroBreakdown` must reflect the actual data origin — stub calls set `source = "stub"`.
7. Every `@tool` wrapper must set a `source` field visible in the response so stubs are never silent.

---

## Handoff Messages

**§10-A** (sent by Person 1 after publishing this file):
> Contract frozen at `docs/contracts/gate_a_tools.md`. Person 2: implement against these exact field names in `nutriguard/src/nutriguard/`. Person 3: build against this shape. Missing values are the string `unknown`, never a guess. Every `SafetyResult` carries a non-diagnostic disclaimer and an `allergen_conflicts` list — empty list is a valid answer, a missing key is a bug. Renaming a field needs all three of us to agree.

**§10-D** (sent by Person 1 with §10-A):
> Allergen verdicts are computed deterministically in `app/allergy_gate.py`, not by the model, and the gate runs on the result of `check_safety` regardless of who implemented it. Person 2: return whatever the KB gives you, including empty — the gate handles escalation, so don't try to decide the verdict yourself, and never return `ok` on a failed lookup. Person 3: render `allergen_conflicts` from the structured output directly, name the allergen and the matched food, and never display "safe" or "allergen-free" anywhere in the UI. Allowed phrasing is in §3A of `PERSON1_GATE_A_PLAN.md`.
