# Gate A — Person 1 Handoff Document

> **Purpose:** What happened in Session 1, exactly what was verified, and the numbered checklist the next person must clear before any code can run.
> **Do not modify this file.** It is a snapshot. The living log is `EVIDENCE_P1.md`.

---

## 1. Session Summary

Session 1 was a diagnostic and scaffolding session. No application code was deployed. The following was established:

- The repository exists at `c:\awshack` with the full plan documents in place.
- AWS CLI is present on the machine.
- Node.js and Python are present on the machine.
- **AWS credentials are NOT configured.** Every `aws sts get-caller-identity` call returns `NoCredentialsError`.
- **The AgentCore CLI (`@aws/agentcore`) is NOT installed.** `agentcore --help` fails.
- The full implementation scaffold for Person 1's slice has been written to disk (see §4 below).
- No AWS resources have been created, no parameters have been written to SSM, no CDK bootstrap has been run.

---

## 2. Exact Diagnostic Commands and Results

These were the preflight commands from §1 of `PERSON1_GATE_A_PLAN.md` and their outcomes:

| Command | Result |
|---|---|
| `aws sts get-caller-identity` | **FAIL — `NoCredentialsError`: Unable to locate credentials |
| `aws configure get region` | Empty / not set |
| `aws bedrock list-foundation-models ...` | **FAIL** — same credentials error |
| `node --version` | **PASS** — Node present |
| `python --version` | **PASS** — Python present |
| `npm install -g @aws/agentcore` | **NOT RUN** — credentials required to validate; CLI not installed |
| `agentcore --help` | **FAIL** — command not found |
| `git ls-files \| findstr .env` | **PASS** — no secrets tracked |

**MCP servers** (`aws-documentation`, `bedrock-agentcore`, `strands-agents`) were not tested because credentials are required for any live query.

---

## 3. Current Repository State

```
c:\awshack\
  PERSON1_GATE_A_PLAN.md              ← authoritative execution plan
  NUTRIGUARD_3_PERSON_EXECUTION_PLAN.md
  NutriGuard_AI_Merged_Build_Plan.md
  GATE_A_PERSON1_HANDOFF.md           ← this file
  GATE_A_PERSON1_SUBAGENT_SYSTEM_PROMPT.md ← execution prompt for next session
  EVIDENCE_P1.md                      ← evidence log (skeleton, ready to fill)
  docs/contracts/gate_a_tools.md      ← FROZEN interface contract (§3)
  nutriguard/
    .gitignore
    requirements.txt
    agentcore/
      agentcore.json
      aws-targets.json
    app/
      __init__.py
      main.py                         ← Strands agent entrypoint + system prompt
      agent_tools.py                  ← @tool wrappers (stub-backed)
      allergy_gate.py                 ← deterministic allergen enforcement (§3A)
      config.py                       ← SSM loader with caching
      stubs.py                        ← fixtures incl. demo persona with real allergy
    tests/
      __init__.py
      fixtures/
        demo_meal_profile.json
      test_agent_baseline.py
      test_tool_contracts.py
      test_config_ssm.py
      test_safety_allergy.py          ← all 9 §3A verdict-table cases
      test_safety_guardrail.py
```

**Branch:** `feature/agentcore-platform` has NOT been created yet — credentials are needed to push. The files are on disk, ready to be committed once credentials are in place.

**No AWS resources exist yet.** Nothing in SSM, no guardrail, no CDK bootstrap.

---

## 4. Numbered Setup Checklist

Clear every item in order before running any code. Do not skip ahead.

### Step 1 — Configure AWS credentials

```powershell
aws configure
# Enter: AWS Access Key ID, Secret Access Key, region = us-west-2, output = json
aws sts get-caller-identity --no-cli-pager
# Must return: Account, UserId, Arn — no error
```

The identity that gets configured must have these IAM permissions (at minimum):
- `bedrock:*` in `us-west-2`
- `ssm:PutParameter`, `ssm:GetParameter`, `ssm:GetParametersByPath` on `/nutriguard/*`
- `bedrock:CreateGuardrail`, `bedrock:CreateGuardrailVersion`, `bedrock:GetGuardrail`
- `cloudformation:*`, `iam:*` (for CDK bootstrap and AgentCore deploy)
- `s3:*`, `ecr:*`, `lambda:*` (AgentCore deploy dependencies)

### Step 2 — Set the default region

```powershell
aws configure set region us-west-2
aws configure get region
# Must return: us-west-2
```

### Step 3 — Install the AgentCore CLI

```powershell
npm install -g @aws/agentcore
agentcore --help
# Must print the AgentCore command list
```

If `@aws/agentcore` is unavailable on npm, fall back:
```powershell
pip install bedrock-agentcore-starter-toolkit
agentcore configure
agentcore launch
```
Record which path was taken in `EVIDENCE_P1.md`.

### Step 4 — Confirm Bedrock model access

1. Open the AWS Console → Amazon Bedrock → Model access (us-west-2).
2. Confirm **Claude Sonnet** (the model referenced in `agentcore.json`) shows status **Access granted**.
3. If not, request access and wait for approval before proceeding. This can take minutes to hours.

```powershell
aws bedrock list-foundation-models --region us-west-2 --no-cli-pager \
  --query "modelSummaries[?contains(modelId,'claude')].{id:modelId,status:modelLifecycle.status}"
# Claude Sonnet entry must be present
```

### Step 5 — Bootstrap CDK (required by `agentcore deploy`)

```powershell
npm install -g aws-cdk
cdk --version
# Then bootstrap:
cdk bootstrap aws://<ACCOUNT_ID>/us-west-2
# Must end with: Environment aws://<ACCOUNT_ID>/us-west-2 bootstrapped
```

Replace `<ACCOUNT_ID>` with the value from Step 1's `get-caller-identity` output.

### Step 6 — Verify MCP server connectivity

The plan requires querying MCP servers before each task. Confirm the three servers listed in `.kiro/settings/mcp.json` are reachable:
- `aws-documentation`
- `bedrock-agentcore`
- `strands-agents`

Send a test query to each from the Kiro IDE before starting P1-01.

### Step 7 — Install Python dependencies

```powershell
cd c:\awshack\nutriguard
pip install -r requirements.txt
```

### Step 8 — Create the git branch

```powershell
cd c:\awshack
git checkout -b feature/agentcore-platform
git status
# Working tree should show all new nutriguard/ files as untracked
```

### Step 9 — Confirm no secrets are tracked

```powershell
git ls-files | Select-String -Pattern "\.env|credentials|\.pem|\.key"
# Must return nothing
```

### Step 10 — Run the test suite (expect failures until AWS is wired)

```powershell
cd c:\awshack\nutriguard
python -m pytest tests/ -q
```

The SSM-dependent tests will fail until Step 1–5 are complete. The `allergy_gate` tests and contract tests should pass immediately with stubs.

---

## 5. What the Next Session Should Do First

1. Clear Steps 1–10 above in order.
2. Open `GATE_A_PERSON1_SUBAGENT_SYSTEM_PROMPT.md` and paste its contents into a fresh Kiro session.
3. The subagent prompt will re-verify preflight live (not trust this doc) and then execute the 8 dispatch waves.

---

## Sources

- [Get started with the AgentCore CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html)
- [Get started with AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-get-started.html)
- [Strands Agents — Bedrock model provider API](https://strandsagents.com/docs/api/python/strands.models.bedrock/)
- [Strands Agents — deploy to AgentCore Runtime (Python)](https://strandsagents.com/docs/user-guide/deploy/deploy_to_bedrock_agentcore/python/)

Content was rephrased for compliance with licensing restrictions.
