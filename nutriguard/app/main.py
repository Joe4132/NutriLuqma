"""
NutriGuard agent entrypoint — app/main.py

Strands agent backed by Amazon Bedrock (Claude Sonnet, us-west-2).
Wrapped by the AgentCore Runtime via @app.entrypoint.

Rules:
- System prompt must contain the non-diagnosis clause.
- Model is Claude Sonnet in us-west-2.
- Guardrail ID and version come from config.py (SSM), never hardcoded.
- All six tool wrappers registered via NUTRIGUARD_TOOLS.
- suggest_recipe stays commented out until §6 gate is fully green.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# System prompt — defined at module level so tests can import it without
# requiring bedrock_agentcore or strands to be installed.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are NutriGuard, an AI nutrition assistant. Your role is to help users
understand the nutritional content of their meals, check meals against their
dietary profiles, and log meals to their dashboard.

How you work:
1. When a user shares a meal photo or describes a meal, call identify_food to
   identify the items, then estimate_portion for portion sizes, then get_macros
   for the USDA-grounded macro breakdown.
2. Call get_profile to retrieve the user's dietary profile — do this on every
   request; never rely on remembered profile data.
3. Call check_safety with the meal macros and the user's profile. The allergen
   verdict in the result is deterministic — do not second-guess or override it.
   Name the specific allergen and the specific matched food when reporting a conflict.
4. Call log_meal to record the meal to the user's dashboard.
5. Present the results clearly: macros, safety status, and any allergen conflicts.

What you must never do:
- Never diagnose a medical condition (e.g. "you may have diabetes").
- Never recommend treatment, medication, dosing, or management plans.
- Never advise on allergy-reaction management, epinephrine, antihistamines,
  or any clinical intervention.
- Never use the words "safe", "safe to eat", or "allergen-free". The allowed
  phrasing for a clean allergen check is: "no known match for [allergen] in
  the identified items".
- Never invent nutrition numbers. If data is missing, say "unknown".
- Never claim certainty you don't have. State uncertainty out loud.

When data is unavailable or a tool fails, say so clearly and defer to the user's
clinician or the ingredient label for anything safety-critical.

Always include the disclaimer: "This is nutritional information only. It is not
medical advice. Consult your clinician or dietitian before making dietary
decisions based on this information."
"""

# ---------------------------------------------------------------------------
# AgentCore app — only instantiated when the package is available
# ---------------------------------------------------------------------------

try:
    from bedrock_agentcore import BedrockAgentCoreApp  # type: ignore[import-untyped]
    from strands import Agent  # type: ignore[import-untyped]
    from strands.models import BedrockModel  # type: ignore[import-untyped]
    from app.agent_tools import NUTRIGUARD_TOOLS
    _RUNTIME_AVAILABLE = True
except ModuleNotFoundError:
    _RUNTIME_AVAILABLE = False
    BedrockAgentCoreApp = None  # type: ignore[assignment,misc]
    Agent = None  # type: ignore[assignment]
    BedrockModel = None  # type: ignore[assignment]
    NUTRIGUARD_TOOLS = []  # type: ignore[assignment]


if _RUNTIME_AVAILABLE:
    app = BedrockAgentCoreApp()
else:
    app = None  # type: ignore[assignment]


def _build_agent():  # type: ignore[return]
    """Construct the Strands agent. Called at startup and in tests."""
    if not _RUNTIME_AVAILABLE:
        raise RuntimeError(
            "bedrock_agentcore and strands packages are required. "
            "Run: pip install -r requirements.txt"
        )

    try:
        from app import config  # noqa: PLC0415
        guardrail_id = config.get("guardrail_id")
        guardrail_version = config.get("guardrail_version")
        model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-5",
            region_name="us-west-2",
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version,
            guardrail_trace="enabled",
        )
    except Exception:
        # Config unavailable (no credentials / dev mode) — run without guardrail.
        # This path is for local stub testing only; never acceptable in production.
        print(
            "[main] WARNING: config unavailable — running without guardrail. "
            "This is acceptable for local stub testing only."
        )
        model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-5",
            region_name="us-west-2",
        )

    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=NUTRIGUARD_TOOLS,
    )


# ---------------------------------------------------------------------------
# AgentCore entrypoint — only registered when runtime is available
# ---------------------------------------------------------------------------

if _RUNTIME_AVAILABLE and app is not None:
    @app.entrypoint
    def handler(payload: dict, context: dict | None = None) -> dict:
        """
        AgentCore runtime entrypoint.

        Args:
            payload: dict with at least {"prompt": str, "user_id": str}.
            context: Optional runtime context from AgentCore.

        Returns:
            dict with {"response": str}.
        """
        prompt: str = payload.get("prompt", "")
        user_id: str = payload.get("user_id", "demo-1")

        if not prompt:
            return {"response": "No prompt provided."}

        # Inject user_id into the prompt so tools can retrieve the right profile
        full_prompt = f"[user_id: {user_id}] {prompt}"

        agent = _build_agent()
        response = agent(full_prompt)
        return {"response": str(response)}


# ---------------------------------------------------------------------------
# Local dev entry (agentcore dev uses this)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if app is not None:
        app.run()
    else:
        print("ERROR: bedrock_agentcore not installed. Run: pip install -r requirements.txt")
