"""Strands `@tool` wrappers over the Person 2 business logic (Task 4).

Per the project steering conventions, `@tool` wrappers are kept separate
from business logic: every function in `agent_tools` only (a) converts
between JSON-friendly dicts and the frozen domain types, (b) calls exactly
one function from `vision`, `nutrition`, `safety`, or `data`, and
(c) reports failure explicitly. No allergen matching, macro math, portion
heuristics, or persistence logic lives in this package - all of that stays
in the modules built during Wave 1/Wave 2.
"""
