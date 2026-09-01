# Fixtures

Shared test/demo fixtures for the Person 2 (vision/nutrition/safety/data) slice.
Persons 1 and 3 can code against these immediately after Task 1 lands - they
are the frozen contract made concrete.

- `profiles.json` - sample `UserProfile` records, valid and invalid.
- `identify_*.json` - sample `identify_food` outputs (owned by Wave 1 agent A).
- `meal_demo.json` - the one representative demo meal referenced by the plan.

Do not hand-edit generated fixture files owned by a Wave 1/2 agent; regenerate
via that subsystem's tests instead.
