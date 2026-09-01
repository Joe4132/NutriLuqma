# Evidence Log — Person 1 Gate A

> Append one section per task, immediately after the task is done.
> Format: `## <TASK ID> — <name>` followed by the fields below.
> Do not delete entries. A task without evidence is not done.

---

## PREFLIGHT

Docs consulted: N/A (system commands only)

| Command | Result |
|---|---|
| `aws sts get-caller-identity` | PENDING — credentials not yet configured |
| `aws configure get region` | PENDING |
| `aws bedrock list-foundation-models` | PENDING |
| `node --version` | PASS (present) |
| `python --version` | PASS (present) |
| `agentcore --help` | FAIL — not installed |
| `git ls-files \| findstr .env` | PASS — no secrets tracked |

MCP connectivity: NOT VERIFIED (requires credentials)

Status: **BLOCKED — clear `GATE_A_PERSON1_HANDOFF.md` setup checklist before proceeding**

Notes: Scaffold files written to disk in Session 1. No AWS resources created yet.

---

## P1-01 — Strands Agent Baseline

Docs consulted: `bedrock-agentcore` → [pending], `strands-agents` → [pending]

Command:
```
agentcore create --name nutriguard --framework Strands --model-provider Bedrock --memory shortTerm --build CodeZip
agentcore dev --logs
agentcore dev "Log a plate of grilled chicken and rice for user demo-1"
```

Result: PENDING

Real generated paths:
- Entrypoint: `nutriguard/app/main.py` (scaffold; confirm after `agentcore create`)
- Config: `nutriguard/agentcore/agentcore.json`

Status: **PENDING**

Notes: Scaffold entrypoint written at `nutriguard/app/main.py`. Run `agentcore create` to confirm or regenerate.

---

## P1-02 — Typed @tool Wrappers

Docs consulted: `strands-agents` → [pending]

Command:
```
python -m pytest tests/test_tool_contracts.py -v
agentcore dev "What's in this photo: tests/fixtures/demo_meal.jpg"
```

Result: PENDING

Status: **PENDING**

Notes: Wrappers written to `nutriguard/app/agent_tools.py`. Stubs in `nutriguard/app/stubs.py`.

---

## P1-02A — Allergen Gate

Docs consulted: N/A (pure local logic)

Command:
```
python -m pytest tests/test_safety_allergy.py -v
agentcore dev "<demo allergen prompt>"
```

Result: PENDING

Status: **PENDING**

Notes: Gate written to `nutriguard/app/allergy_gate.py`. Demo persona has `allergies: ["peanut"]` in stubs.

---

## P1-03 — SSM Configuration Loader

Docs consulted: `aws-documentation` → [pending]

Command:
```
aws ssm put-parameter --name /nutriguard/gate-a/table_name ...
aws ssm get-parameters-by-path --path /nutriguard/gate-a --region us-west-2 --no-cli-pager
python -m pytest tests/test_config_ssm.py -v
```

Result: PENDING

Status: **PENDING**

Notes: Loader written to `nutriguard/app/config.py`. Requires credentials to write SSM parameters.

---

## P1-05 — Guardrails

Docs consulted: `aws-documentation` → [pending], `strands-agents` → [pending]

Command:
```
aws bedrock create-guardrail ...
python -m pytest tests/test_safety_guardrail.py -v
agentcore dev "Based on this meal do I have diabetes and what medication should I take?"
```

Result: PENDING

Status: **PENDING**

Notes: Guardrail not yet created. Test file written at `nutriguard/tests/test_safety_guardrail.py`.

---

## P1-04 — Memory Integration

Docs consulted: `bedrock-agentcore` → [pending]

Command:
```
agentcore add memory --name NutriGuardMemory --strategies SEMANTIC
```

Result: PENDING — **first cut if behind per §8**

Status: **PENDING / CUT CANDIDATE**

Notes: Cut this before any other task if past timebox 2:05.

---

## P1-06 — Runtime Deployment

Docs consulted: `bedrock-agentcore` → [pending]

Command:
```
agentcore validate
agentcore deploy --dry-run
agentcore deploy -v
agentcore status
agentcore invoke "<demo prompt>"
```

Result: PENDING

Status: **PENDING**

Notes: Deploy requires all of P1-02, P1-03, integration §5 to be complete first.

---

## P1-07 — CloudWatch / Trace Evidence

Docs consulted: `aws-documentation` → [pending]

Command:
```
agentcore logs
agentcore traces list
```

Result: PENDING

Status: **PENDING**

Notes: Depends on P1-06 deploy succeeding.

---

## §6 Pre-Demo Verification Gate

| Check | Status |
|---|---|
| Unit + contract tests pass | PENDING |
| Type check passes on `nutriguard/app/**` | PENDING |
| Lint passes on `nutriguard/app/**` | PENDING |
| Local end-to-end photo→dashboard works | PENDING |
| Diagnostic prompt redirected (P1-05) | PENDING |
| All nine §3A allergy tests pass | PENDING |
| Allergen conflict names allergen AND matched food in structured output | PENDING |
| No output path returns `ok` from failed/missing-profile/low-confidence check | PENDING |
| Grep confirms no meal output uses "safe", "safe to eat", "allergen-free" | PENDING |
| Allergen conflict survives the guardrail | PENDING |
| Malformed image / missing profile / unknown food degrade gracefully | PENDING |
| `git ls-files` shows no credentials, tokens, medical data, photos | PENDING |
| Zero hardcoded ARNs / IDs / buckets / tables in your files | PENDING |
| Every AWS CLI command used `--no-cli-pager` and `--region us-west-2` | PENDING |
| Deployed invoke succeeded OR local fallback documented with real error | PENDING |
| Remaining stubs listed; none backs a demo claim | PENDING |

---

## Cuts Taken

_None yet. Log any cut here with: task, reason, fallback taken._

---

## Stubs Remaining

_Fill this in during Wave 5 stub audit._

| Stub | Backs a demo claim? | Resolution |
|---|---|---|
| `identify_food` | TBD | Waiting for Person 2 |
| `estimate_portion` | TBD | Waiting for Person 2 |
| `get_macros` | TBD | Waiting for Person 2 |
| `check_safety` (business logic) | TBD | Waiting for Person 2 |
| `log_meal` | TBD | Waiting for Person 2 |
| `get_profile` | TBD | Waiting for Person 2 |
