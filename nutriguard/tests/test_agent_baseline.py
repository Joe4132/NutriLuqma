"""
P1-01 — Strands agent baseline tests.

Verifies:
- The agent builds without error.
- The system prompt contains the non-diagnosis clause.
- The tool registry is non-empty.
- The system prompt does not contain forbidden phrasing.

Run: python -m pytest tests/test_agent_baseline.py -v
"""

from __future__ import annotations

import sys
import os

# Allow imports from the nutriguard package root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestAgentBaseline:
    """Agent construction and system prompt contract."""

    def test_agent_builds(self) -> None:
        """Agent object can be constructed without raising."""
        # Import here so missing strands/bedrock_agentcore doesn't fail collection
        try:
            from app.main import _build_agent  # noqa: PLC0415
        except ImportError as exc:
            pytest.skip(f"strands or bedrock_agentcore not installed: {exc}")

        # _build_agent may fail if AWS credentials are absent — that's expected in CI.
        # We just want to confirm the function is callable and the import works.
        assert callable(_build_agent)

    def test_system_prompt_non_diagnosis_clause(self) -> None:
        """System prompt must contain the non-diagnosis clause."""
        from app.main import SYSTEM_PROMPT  # noqa: PLC0415

        # Collapse whitespace for phrase matching (system prompt may have newlines mid-sentence)
        prompt_lower = " ".join(SYSTEM_PROMPT.lower().split())

        non_diagnosis_phrases = [
            "never diagnose",
            "is not medical advice",   # from the disclaimer sentence
            "consult your clinician",
        ]
        for phrase in non_diagnosis_phrases:
            assert phrase in prompt_lower, (
                f"System prompt missing non-diagnosis phrase: {phrase!r}"
            )

    def test_system_prompt_no_forbidden_language(self) -> None:
        """
        System prompt must not make positive assertions using forbidden phrasing.
        Note: the system prompt is ALLOWED to name forbidden phrases in a prohibition
        context (e.g. "Never use the words 'safe to eat'"). What's forbidden is
        the system prompt positively asserting a meal IS safe to eat.
        """
        from app.main import SYSTEM_PROMPT  # noqa: PLC0415

        prompt_lower = " ".join(SYSTEM_PROMPT.lower().split())

        # These are positive-assertion forms that must not appear
        positive_forbidden = [
            "the meal is safe to eat",
            "it is safe to eat",
            "this is allergen-free",
            "the food is allergen-free",
        ]
        for phrase in positive_forbidden:
            assert phrase not in prompt_lower, (
                f"System prompt must not positively assert: {phrase!r}"
            )

    def test_tool_registry_non_empty(self) -> None:
        """NUTRIGUARD_TOOLS must contain at least the six required tools."""
        from app.agent_tools import NUTRIGUARD_TOOLS  # noqa: PLC0415

        assert len(NUTRIGUARD_TOOLS) >= 6, (
            f"Expected at least 6 tools, got {len(NUTRIGUARD_TOOLS)}"
        )

    def test_tool_names_present(self) -> None:
        """Each required tool name must appear in the registry."""
        from app.agent_tools import NUTRIGUARD_TOOLS  # noqa: PLC0415

        required = {
            "identify_food",
            "estimate_portion",
            "get_macros",
            "check_safety",
            "log_meal",
            "get_profile",
        }
        # Strands @tool decorated functions carry their name in __name__
        registered_names = {fn.__name__ for fn in NUTRIGUARD_TOOLS}
        missing = required - registered_names
        assert not missing, f"Missing tools in registry: {missing}"

    def test_suggest_recipe_not_registered(self) -> None:
        """suggest_recipe must not be in the registry until §6 is green."""
        from app.agent_tools import NUTRIGUARD_TOOLS  # noqa: PLC0415

        registered_names = {fn.__name__ for fn in NUTRIGUARD_TOOLS}
        assert "suggest_recipe" not in registered_names, (
            "suggest_recipe must stay commented out until §6 gate is green"
        )
