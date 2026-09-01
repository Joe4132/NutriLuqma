# Person 2 -> Person 1 / Person 3 Contract (Gate A)

Published after Task 4. This is the frozen tool surface Person 1's
Strands/AgentCore agent registers, and the shape Person 3's UI should mock
against. Backing types live in `src/nutriguard/domain/models.py`
(read-only outside Person 2's slice); tool functions live in
`src/nutriguard/tools/agent_tools.py`.

Every tool returns either the documented success shape or `{"error": "..."}`
- never raises. Callers should check for the `"error"` key before reading
any other field.

## Tool call sequence (Gate A demo journey)

```text
identify_food(image_path)
  -> estimate_portion(image_path, foods)
    -> get_macros_tool(foods)
      -> check_safety_tool(foods, profile, meal_total_macros, kb_evidence?)
        -> log_meal_tool(meal_id, user_id, logged_at_iso, foods, meal_total_macros, safety_result)

get_profile_tool(user_id)  # called whenever a profile is needed as input above
```

## Tools

### `identify_food(image_path: str, backend: str = "fixture") -> dict`
- Success: `{"foods": [FoodItem, ...]}`
- Error: `{"error": str}`
- `backend="fixture"` works with zero AWS setup - use this for UI/demo work
  before AWS credentials exist.

### `estimate_portion(image_path: str, foods: list[FoodItem]) -> dict`
- Success: `{"foods": [FoodItem, ...]}` - same foods, `grams` and
  `portion_is_approximate=True` now populated.
- Error: `{"error": str}`

### `get_macros_tool(foods: list[FoodItem]) -> dict`
- Success: `{"per_food": {label: MacroBreakdown}, "meal_total": MacroBreakdown}`
- Error: `{"error": str}`
- `meal_total.sugar_g` is the field to highlight on the dashboard.
- An unmatched food yields `MacroBreakdown.source == "unknown"` and all
  numeric fields `null` - render this as "unknown", never a guessed number.

### `check_safety_tool(foods, profile, meal_total_macros, kb_evidence=None) -> dict`
- Success: `{"safety_result": SafetyResult}`
- Error: `{"error": str}`
- `verdict` is one of `"allergen_conflict"`, `"cannot_verify"`,
  `"macro_caution"`, `"no_conflict_detected"` - **never** render any of
  these as "safe" or "allergen-free" in the UI; use the `explanation` text
  as-is, it is already written to avoid that framing.

### `log_meal_tool(meal_id, user_id, logged_at_iso, foods, meal_total_macros, safety_result) -> dict`
- Success: `{"status": "logged", "meal_id": str}`
- Error: `{"error": str}`

### `get_profile_tool(user_id: str) -> dict`
- Success: `{"profile": UserProfile}` or `{"profile": null}` if not found.
- Error: `{"error": str}`

## JSON shapes

```jsonc
// FoodItem
{
  "label": "peanut sauce",
  "identification_confidence": 0.4,       // 0.0-1.0
  "bbox": [0.55, 0.2, 0.3, 0.3] | null,    // normalized x, y, w, h
  "grams": 40.0 | null,                    // null until estimate_portion runs
  "portion_is_approximate": true,
  "source": "fixture" | "bedrock_vision" | "local_model"
}

// MacroBreakdown
{
  "calories_kcal": 120.0 | null,
  "protein_g": 5.0 | null,
  "carbs_g": 10.0 | null,
  "fat_g": 3.0 | null,
  "sugar_g": 2.0 | null,                   // always its own field - dashboard highlight
  "source": "usda_fdc:167512" | "unknown" | "aggregated"
}

// AllergyEntry (part of UserProfile.allergies)
{
  "allergen": "peanut",                    // one of the FDA Big 9, see below
  "severity": "intolerance" | "allergy" | "anaphylaxis",
  "notes": "string" | null
}

// UserProfile
{
  "user_id": "demo-user-1",
  "display_name": "Sam",
  "allergies": [AllergyEntry, ...],
  "daily_sugar_limit_g": 30.0 | null,
  "notes": "string" | null
}

// AllergenFinding (part of SafetyResult.allergen_findings)
{
  "allergen": "peanut",
  "severity": "anaphylaxis",
  "matched_food": "peanut sauce",
  "match_basis": "direct" | "alias" | "category",
  "identification_confidence": 0.95,
  "evidence_source": "string" | null
}

// SafetyResult
{
  "verdict": "allergen_conflict" | "cannot_verify" | "macro_caution" | "no_conflict_detected",
  "allergen_findings": [AllergenFinding, ...],   // populated regardless of which verdict won
  "explanation": "string",                       // non-diagnostic, safe to render directly
  "macro_notes": ["string", ...],                // only non-empty for macro_caution
  "evidence_refs": ["string", ...]                // KB evidence, may be empty
}
```

## Allergen vocabulary (FDA Big 9)

`milk`, `egg`, `fish`, `crustacean_shellfish`, `tree_nut`, `peanut`, `wheat`,
`soy`, `sesame`.

## Fixtures available now

- `fixtures/profiles.json` - sample `UserProfile` records (valid + invalid),
  including a peanut-anaphylaxis profile and a milk-intolerance profile.
- `fixtures/identify_fixtures.json` - `identify_food(backend="fixture")`
  inputs: `chicken_rice_bowl.jpg`, `garden_salad.jpg`,
  `pad_thai_with_peanut_sauce.jpg` (the last includes a low-confidence
  "peanut sauce" entry at 0.4 confidence, useful for demoing the
  `cannot_verify`/allergen-conflict paths).

## Demo recommendation

Use `pad_thai_with_peanut_sauce.jpg` + the peanut-anaphylaxis profile from
`fixtures/profiles.json` for the primary demo - it drives the full chain to
`allergen_conflict`, which is the most visually compelling verdict, and
exercises the alias/hidden-source matching Person 2 built (peanut sauce is
matched directly; the same map also catches hidden peanut via aliases like
"satay" if that food label ever appears).
