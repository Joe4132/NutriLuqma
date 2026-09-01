# Gate A — Person 1 Subagent Execution Prompt

> **Instructions for use:** Once the setup checklist in `GATE_A_PERSON1_HANDOFF.md` is fully cleared, paste the content of §2 below into a fresh Kiro session (Autopilot mode). Do not paste this preamble — paste only the block marked "START PASTE HERE".
>
> This prompt does NOT restate `PERSON1_GATE_A_PLAN.md`. It tells the agent how to sequence subagent delegation against that plan. Read the plan before reading this prompt so you understand the constraints each wave enforces.

---

## 1. Reading Order Before You Start

1. `PERSON1_GATE_A_PLAN.md` — authoritative task definitions, timebox, lane contract, §3A safety rules
2. `GATE_A_PERSON1_HANDOFF.md` — what Session 1 verified and what it left for you
3. `docs/contracts/gate_a_tools.md` — frozen interface contract (do not change without consensus)
4. `EVIDENCE_P1.md` — append your findings per task as you go
5. `nutriguard/app/` — the scaffold is already on disk; read the files before any subagent touches them

---

## 2. Execution Prompt

---

### START PASTE HERE

You are the Person 1 implementation agent for the NutriGuard Gate A build. Your authoritative task list is `PERSON1_GATE_A_PLAN.md`. Your lane contract, hard stops, and §3A allergen safety rules are all in that file — read it completely before doing anything else.

The scaffold (all `nutriguard/` source and test files) is already on disk from Session 1. Do not re-create files that exist. Read them first, then act.

---

#### Standing Rules (apply to every action this session)

1. **MCP first, every task.** Before writing or editing any code for a task, query the MCP servers named in that task's header. Record the doc titles in `EVIDENCE_P1.md`. "Prior knowledge is sufficient" is never an acceptable reason to skip this step.

2. **§3A allergen contract is non-negotiable.** No subagent output, no model response, and no integration change may:
   - Let the model decide an allergen verdict
   - Lower a verdict (`conflict → caution`, `caution → ok`)
   - Remove or skip the `allergy_gate` call from inside `check_safety`
   - Output the words "safe", "safe to eat", or "allergen-free"
   - Silence or blank an allergen conflict (including via guardrail)
   If a subagent returns code that violates any of these, **reject the output, do not merge it, and redo the task yourself.**

3. **You own your files only.** `nutriguard/agentcore/**`, `nutriguard/app/**`, `nutriguard/tests/test_agent_*.py`, `test_tool_contracts.py`, `test_config_ssm.py`, `test_safety_*.py`, `docs/contracts/gate_a_tools.md`, `EVIDENCE_P1.md`. Nothing else. Stub missing dependencies; never edit Person 2's or Person 3's files.

4. **No hardcoded identifiers.** Every ARN, bucket name, table name, KB ID, guardrail ID must come from SSM via `config.py`. If a subagent returns a hardcoded value, replace it with the SSM call before accepting.

5. **Commit small.** Commit at the end of each wave, not at the end of the session. Do not squash, do not force-push, do not bypass hooks.

6. **Evidence log.** Append to `EVIDENCE_P1.md` after every task. The format is in §9 of the plan. A task without evidence is not done.

---

#### Pre-Execution: Live Preflight (do this yourself, not a subagent)

Do not trust `GATE_A_PERSON1_HANDOFF.md`'s diagnostics. Re-run the preflight live:

```powershell
aws sts get-caller-identity --no-cli-pager
aws configure get region
aws bedrock list-foundation-models --region us-west-2 --no-cli-pager --query "length(modelSummaries)"
node --version
python --version
agentcore --help
git ls-files | Select-String -Pattern "\.env|credentials|\.pem"
```

All must pass. If any fail, stop and tell the user exactly which step failed and what the error is. Do not proceed past a failed preflight.

After preflight passes, also verify MCP connectivity by sending one test query to each of `aws-documentation`, `bedrock-agentcore`, and `strands-agents`.

Record all results in `EVIDENCE_P1.md` under `## PREFLIGHT`.

---

#### Wave 1 — Run in parallel (both are independent)

Dispatch two subagents simultaneously:

**Subagent 1A — P1-01 Strands Agent Baseline**
- Reads: `nutriguard/app/main.py`, `nutriguard/agentcore/agentcore.json`
- Task: Run `agentcore create --name nutriguard --framework Strands --model-provider Bedrock --memory shortTerm --build CodeZip` (or confirm the scaffold already satisfies this). Record the real generated entrypoint path. Confirm the NutriGuard system prompt is in place. Run `agentcore dev --logs` and `agentcore dev "Log a plate of grilled chicken and rice for user demo-1"`. Run `tests/test_agent_baseline.py` — watch it fail first if it does, then make it pass.
- Must produce: local invoke response, passing baseline test, entrypoint path recorded in `EVIDENCE_P1.md`.
- Must NOT: change the system prompt's non-diagnosis clause, add Gate B features, hardcode anything.

**Subagent 1B — P1-03 SSM Configuration Loader**
- Reads: `nutriguard/app/config.py`, `nutriguard/tests/test_config_ssm.py`
- Task: Write the five SSM parameters under `/nutriguard/gate-a/` prefix. Verify the loader in `config.py` is correct. Run `tests/test_config_ssm.py`. Confirm no hardcoded identifiers remain in `nutriguard/app/`.
- Must produce: five SSM parameters verified by `aws ssm get-parameters-by-path`, passing config tests.
- Must NOT: put any value in `.env.local` that SSM can hold, hardcode region anywhere other than `us-west-2` in the loader.

Wait for both to complete before Wave 2.

**After Wave 1 — you do this yourself:**
- Review both subagent outputs.
- Confirm entrypoint paths are consistent between `agentcore.json` and the actual file.
- Grep `nutriguard/app/` for any hardcoded identifiers. Remove any found.
- Append Wave 1 results to `EVIDENCE_P1.md`.
- Commit: `git add nutriguard/ && git commit -m "wave-1: agent baseline + SSM loader"`

---

#### Wave 2 — Run in parallel (both are independent of each other, both depend on Wave 1)

**Subagent 2A — P1-02 Typed @tool Wrappers**
- Reads: `nutriguard/app/agent_tools.py`, `nutriguard/app/stubs.py`, `docs/contracts/gate_a_tools.md`
- Task: Verify all six `@tool` wrappers are complete and match the §3 contract exactly. Each wrapper must: validate input, call business logic or stub, normalise, return structured output with `source` field. Run `tests/test_tool_contracts.py`.
- Must produce: all contract tests passing, `allergen_conflicts` key present in every `check_safety` return.
- Must NOT: add business logic inside wrappers, change any field name in the contract, wire allergy_gate (that's the merge step below).

**Subagent 2B — P1-02A Allergen Gate**
- Reads: `nutriguard/app/allergy_gate.py`, `nutriguard/app/stubs.py`, `nutriguard/tests/test_safety_allergy.py`
- Task: Verify `allergy_gate.py` implements the ordered enum, one-way escalation via `max()`, the normaliser, the alias table from §3A, and the `0.60` confidence floor. The demo persona in `stubs.py` must carry a real allergy (e.g. `allergies: ["peanut"]`). Run all nine `test_safety_allergy.py` cases — watch the downgrade test and the "no safe wording" test fail first, then ensure they pass.
- Must produce: all nine §3A test cases passing. No output path can produce `ok` from a failed or low-confidence check.
- Must NOT: let the model decide any verdict, lower any verdict, use the word "safe" in any output, skip the confidence floor.

Wait for both to complete before the Wave 2 merge step.

**After Wave 2 — you do this yourself (merge point, not delegatable):**
The allergy gate must be wired as the **final step** inside the `check_safety` wrapper in `agent_tools.py`. This is a cross-file judgment call — subagent 2A doesn't know 2B's exact enum API, and subagent 2B doesn't know 2A's return shape. You wire them:

1. Open `nutriguard/app/agent_tools.py`.
2. Inside the `check_safety` wrapper, after the business logic call (or stub call), add:
   ```python
   from app.allergy_gate import run_allergy_gate
   result = run_allergy_gate(result, profile)
   ```
   (Adjust to match the actual function signature in `allergy_gate.py`.)
3. Run `tests/test_safety_allergy.py` and `tests/test_tool_contracts.py` together. Both must pass.
4. Run `agentcore dev "<demo allergen prompt for the demo persona>"` — confirm the conflict names both the allergen and the matched food in the structured output.
5. Publish the handoff messages §10-A and §10-D from `PERSON1_GATE_A_PLAN.md` to the team.
6. Append Wave 2 results to `EVIDENCE_P1.md`.
7. Commit: `git add nutriguard/ docs/ && git commit -m "wave-2: tool wrappers + allergen gate wired"`

---

#### Wave 3 — Sequential (depends on Wave 2 merge being complete)

**Subagent 3A — P1-05 Guardrails**
- Reads: `nutriguard/app/main.py`, `nutriguard/app/config.py`, `nutriguard/tests/test_safety_guardrail.py`
- Task: Create a Bedrock Guardrail with denied topics covering medical diagnosis, treatment plans, dosage advice, and allergy-reaction treatment. Publish a version. Write the guardrail ID and version to SSM via `config.py`. Wire into `BedrockModel` in `main.py`. Run `tests/test_safety_guardrail.py` — both the redirect case AND the allergen-conflict-survives case.
- Critical test: the demo persona's allergen-conflict meal through the guarded agent must still surface the conflict with the allergen and food named. A guardrail that blanks the allergen warning is a failure. This test must pass before the subagent signs off.
- Must produce: redirect confirmed for diagnostic prompt, benign nutrition question still answers, allergen conflict survives intact.
- Must NOT: create a guardrail that silences allergen conflicts, hardcode the guardrail ID.

Wait for completion before Wave 4.

**After Wave 3 — you do this yourself:**
- Re-run `agentcore dev "Based on this meal do I have diabetes and what medication should I take?"` — confirm redirect.
- Re-run the allergen-conflict dev invoke — confirm conflict intact with allergen and food named.
- Append Wave 3 results to `EVIDENCE_P1.md`.
- Commit: `git add nutriguard/ && git commit -m "wave-3: guardrails + allergen interaction verified"`

**Checkpoint — confirm with the user before Wave 4:**
> "Guardrail is live and billable from this point. Allergen conflict survives the guardrail. Ready to proceed to Memory integration (Wave 4)? Note: Memory is the first cuttable item per §8 of the plan — confirm you want it, or I'll skip to Wave 5."

---

#### Wave 4 — Memory integration (cuttable, cut first if behind)

If the user confirms and you are within the P1-04 timebox (2:05 hard stop):

**Subagent 4A — P1-04 Memory**
- Reads: `nutriguard/app/main.py`, the plan's P1-04 task definition
- Task: Run `agentcore add memory --name NutriGuardMemory --strategies SEMANTIC`. Attach memory to the agent so allergy and sugar-limit context survives a second turn in the same session. Do NOT store medical documents or images. Keep §3A intact: the allergen gate re-reads the profile every request, never uses the memory as the authoritative allergy list.
- Must produce: two-turn `agentcore dev` invoke where the second turn reflects context from the first.
- Must NOT: let remembered allergen data substitute for a fresh `get_profile` call, persist allergy data as a medical record.

If the user says skip, or if you are past the timebox: log the cut in `EVIDENCE_P1.md` as "P1-04 cut — demo uses `get_profile` for profile context" and move directly to Wave 5.

**After Wave 4:**
- Append results or cut record to `EVIDENCE_P1.md`.
- Commit: `git add nutriguard/ && git commit -m "wave-4: memory integration"` (or `"wave-4: memory cut, get_profile demo path"`)

---

#### Wave 5 — Integration (you lead, subagents assist)

This wave is primarily yours because it requires cross-branch judgment.

```powershell
git checkout main
git pull
git merge feature/vision-data
python -m pytest -q
git merge feature/agentcore-platform
python -m pytest -q
git merge feature/product-ui
python -m pytest -q
```

After each merge, if tests fail:
- Failures in `nutriguard/src/nutriguard/**` → post §10-B message, keep the stub, do not fix.
- Failures in your files → fix them.
- Failures in `web/**` → post §10-B message, do not fix.

Once merges are clean, dispatch:

**Subagent 5A — Stub Audit**
- Task: Grep `nutriguard/app/agent_tools.py` and `nutriguard/app/stubs.py` for `SOURCE = "stub"`. For each, check whether `src/nutriguard/` now has the real implementation. If yes, confirm the dynamic resolver in `agent_tools.py` picks it up. Report which stubs remain and whether any of them back a demo claim.
- Must produce: a list of remaining stubs with a yes/no on whether each backs a demo claim.

You then decide: replace stubs that back demo claims before P1-06, or remove the claim from the demo narrative.

**After Wave 5:**
- Walk the full journey locally: `upload → identify → confirm/edit → portion → macros → safety → log → dashboard`
- Append Wave 5 results to `EVIDENCE_P1.md`.
- Commit: `git add -p && git commit -m "wave-5: integration, stub audit"`

---

#### Wave 6 — Pre-Demo Verification Gate (you run this yourself)

Work through §6 of `PERSON1_GATE_A_PLAN.md` line by line. Every item must be green:

```powershell
python -m pytest tests/ -q                          # unit + contract
python -m mypy nutriguard/app/                      # type check
python -m flake8 nutriguard/app/                    # lint
# then agentcore dev end-to-end
# then all safety checks from §6
```

Do not delegate this wave. You are certifying the gate.

Append the full §6 checklist with green/red status to `EVIDENCE_P1.md`.

Only after all items are green: proceed to Wave 7.

---

#### Wave 7 — Deployment (requires explicit user confirmation)

**Checkpoint — confirm with the user:**
> "Pre-demo gate is green. Ready to deploy with `agentcore deploy`? This creates live AWS resources and will incur charges. Confirm to proceed."

Only after confirmation:

**Subagent 7A — P1-06 Deploy**
- Task: Run `agentcore validate`, `agentcore deploy --dry-run`, then `agentcore deploy -v`. Confirm the execution role has: SSM read on `/nutriguard/*`, KB access, DynamoDB table access, S3 bucket access, guardrail access. Add missing permissions. Run `agentcore status`. Run `agentcore invoke "<exact demo prompt>"`.
- Must produce: a successful deployed invoke with a valid structured response. If deploy fails after 10 minutes, stop, capture the error, report back — do not keep trying.
- Must NOT: add permissions beyond what the plan requires, bypass the 10-minute hard stop rule.

**After Wave 7:**
- Append deploy result or fallback to `EVIDENCE_P1.md`.
- Commit: `git add nutriguard/ && git commit -m "wave-7: deploy"`

---

#### Wave 8 — Observability Evidence

**Subagent 8A — P1-07 CloudWatch / Traces**
- Task: Enable Transaction Search if not on. Run `agentcore logs` and `agentcore traces list`. Capture the multi-tool chain trace. Redact all account IDs, ARNs, and user data before saving the screenshot or log snippet.
- Must produce: a visible tool sequence in logs or traces, nothing sensitive on screen.
- Fallback: if deployed invoke failed in Wave 7, capture the dev-server log of the local tool chain instead.

**After Wave 8 — final steps (you do these yourself, they are the session close):**

1. Run the §6 gate one final time against the deployed (or local fallback) agent.
2. Append the final gate status to `EVIDENCE_P1.md`.
3. Identify any remaining stubs and confirm none of them back a demo claim.
4. Final commit: `git add . && git commit -m "gate-a: all waves complete, evidence captured"`
5. Hand to Person 3:
   - The allergen-conflict `agentcore dev` transcript (the strongest safety moment in the demo)
   - The §6 gate checklist screenshot
   - The deployed invoke URL (or local fallback note)
   - The §10-A and §10-D handoff messages
6. Freeze code. Do not touch Gate B.

---

#### Cut Order If Behind (from §8 of the plan)

1. `suggest_recipe` — never implement
2. Memory (Wave 4) — skip entirely, log the cut
3. Managed Guardrails → prompt-level refusal only (log it)
4. Live deployment → verified local demo (log it)
5. CloudWatch screenshot → dev-server log (log it)

**Never cut:** P1-01, P1-02, P1-03, the allergy gate, the nine §3A tests, the local end-to-end journey, the non-diagnosis safety behaviour.

---

### END PASTE HERE

---

## Sources

- [Get started with the AgentCore CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html)
- [Get started with AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-get-started.html)
- [Strands Agents — Bedrock model provider API](https://strandsagents.com/docs/api/python/strands.models.bedrock/)
- [Strands Agents — deploy to AgentCore Runtime (Python)](https://strandsagents.com/docs/user-guide/deploy/deploy_to_bedrock_agentcore/python/)

Content was rephrased for compliance with licensing restrictions.
