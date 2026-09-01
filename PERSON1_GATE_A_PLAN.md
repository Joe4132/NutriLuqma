# Person 1 — Gate A Implementation Pathway (AgentCore & Integration Lead)

> **Audience:** the AI agent executing Person 1's slice.
> **Parent plan:** `NUTRIGUARD_3_PERSON_EXECUTION_PLAN.md` (Gate A scope, §3 roles, §9 task ledger).
> **How to use:** work tasks strictly in the order below. Do not start a task until the previous one has recorded evidence in §9. Re-read §0 before every file write.

---

## 0. Lane Contract (read before every write)

### You own
- `nutriguard/agentcore/**` — AgentCore project config
- `nutriguard/app/**` — entrypoint, agent construction, system prompt, `@tool` wrappers, SSM config loader, temporary stubs
- `nutriguard/app/allergy_gate.py` — deterministic allergen enforcement layer (§3A)
- `nutriguard/tests/test_agent_*.py`, `test_tool_contracts.py`, `test_config_ssm.py`, `test_safety_*.py`
- `docs/contracts/gate_a_tools.md` — the frozen interface contract
- `EVIDENCE_P1.md` — your evidence log
- Branch `feature/agentcore-platform`

### You do not touch
- `nutriguard/src/nutriguard/**` (Person 2: models, vision, nutrition, USDA, KB, persistence)
- `web/**` or any UI code (Person 3)
- Person 2's or Person 3's tests and fixtures

If a subsystem you don't own is broken or missing, you **stub it behind your own wrapper** and post a message from §10. You never edit it yourself.

### Hard stops — abandon and fall back immediately
| Trigger | Action |
|---|---|
| Any task exceeds its timebox | Take the task's fallback, log it, move on |
| A task needs Person 2/3 code that doesn't exist | Use `app/stubs.py`, keep going |
| Deploy fails for 10 minutes | Freeze the verified local path, capture the error, stop deploying |
| A change would edit files outside "You own" | Stop, post handoff message, continue elsewhere |
| Gate A checklist (§6) not green | Do not touch anything Gate B. Ever. |

### Never
- Hardcode ARNs, bucket names, table names, KB IDs, guardrail IDs → SSM only
- Commit credentials, tokens, medical data, or meal photos
- Invent nutrition numbers or add diagnosis/treatment language
- Let the model decide an allergen verdict, or let any code path downgrade one (§3A)
- Emit the word "safe" about a meal — the allowed phrasing is in §3A
- Add SAM 2, Grounding DINO, depth models, OCR, barcode, voice, trend charts (all Gate B)
- Rewrite another person's subsystem during integration

### Mandatory documentation step
Before writing code for **each** task, query the MCP servers named in that task (`aws-documentation`, `bedrock-agentcore`, `strands-agents` from `.kiro/settings/mcp.json`). Prior knowledge is not sufficient. Record the doc titles you consulted in the evidence log.

---

## 1. Preflight — T+0:00 → 0:15 (hard stop 0:15)

Run these and record output. Every line must pass before P1-01 starts.

```cmd
git checkout -b feature/agentcore-platform
aws sts get-caller-identity --no-cli-pager
aws configure get region
aws bedrock list-foundation-models --region us-west-2 --no-cli-pager --query "length(modelSummaries)"
node --version
python --version
npm install -g @aws/agentcore
agentcore --help
git ls-files | findstr /I ".env credentials .pem"
```

Checklist:
- [ ] Identity resolves, region is `us-west-2`
- [ ] Node 20+, Python 3.10+
- [ ] `agentcore --help` prints the command list
- [ ] Claude Sonnet model access enabled in the Bedrock console (us-west-2)
- [ ] CDK available and account bootstrapped (`cdk bootstrap` if unsure) — required by `agentcore deploy`
- [ ] Last command returns **nothing** (no secrets tracked)
- [ ] MCP servers `aws-documentation`, `bedrock-agentcore`, `strands-agents` respond to a test query

If `@aws/agentcore` is unavailable, fall back to the starter toolkit (`pip install bedrock-agentcore-starter-toolkit`, then `agentcore configure` / `agentcore launch`) and note the substitution in the evidence log.

---

## 2. Target Layout

```
nutriguard/                          # agentcore CLI project root  (YOU)
  agentcore/agentcore.json           # project + agent config      (YOU)
  agentcore/aws-targets.json         # account/region targets       (YOU)
  agentcore/.env.local               # gitignored, never committed
  app/
    <entrypoint>.py                  # agent + entrypoint           (YOU)
    agent_tools.py                   # thin @tool wrappers          (YOU)
    allergy_gate.py                  # deterministic allergen gate  (YOU)
    config.py                        # SSM loader                   (YOU)
    stubs.py                         # temp fixtures, deleted later (YOU)
  src/nutriguard/                    # models, vision, nutrition    (PERSON 2)
  tests/                             # your tests only              (YOU)
web/                                 # UI                           (PERSON 3)
docs/contracts/gate_a_tools.md       # frozen contract              (YOU)
EVIDENCE_P1.md                       # evidence log                 (YOU)
```

`agentcore create` generates the real entrypoint filename. **Inspect the generated tree, record the actual paths in §9, and use those** — do not assume a name.

---

## 3. Frozen Interface Contract (publish at 0:20, then freeze)

Write `docs/contracts/gate_a_tools.md` with exactly these signatures. Person 2's `src/nutriguard/models.py` is the authoritative implementation of the types; your contract file is the authoritative *shape*. Until Person 2's models land, `app/stubs.py` returns dicts matching this shape so you are never blocked.

```python
identify_food(image_path: str) -> list[FoodItem]
estimate_portion(image_path: str, foods: list[FoodItem]) -> list[FoodItem]
get_macros(foods: list[FoodItem]) -> MacroBreakdown
check_safety(meal: MacroBreakdown, profile: UserProfile) -> SafetyResult
log_meal(user_id: str, meal: MealRecord) -> None
get_profile(user_id: str) -> UserProfile
suggest_recipe(profile: UserProfile, remaining: MacroBreakdown) -> Recipe   # optional, cut first
```

Field shape (freeze these key names; a rename requires agreement from all three):

```text
FoodItem       : label:str, confidence:float, grams:float|None, is_approximate:bool, bbox:list[float]|None
MacroBreakdown : calories, protein_g, carbs_g, fat_g, sugar_g  (each float | "unknown"), items:list[FoodItem], source:str
SafetyResult   : status:"ok"|"caution"|"conflict", reasons:list[str], evidence:list[str],
                 disclaimer:str, allergen_conflicts:list[AllergenConflict]
AllergenConflict: allergen:str, matched_food:str, match_type:"direct"|"alias"|"unverifiable", confidence:float
UserProfile    : user_id:str, allergies:list[str], conditions:list[str], daily_sugar_limit_g:float|None, notes:str
MealRecord     : meal_id:str, user_id:str, timestamp:str, macros:MacroBreakdown, image_key:str|None
```

Rules baked into every wrapper: missing source data returns `"unknown"`, never a guess. `SafetyResult.disclaimer` always present, always non-diagnostic. `allergen_conflicts` is always present — an empty list is a real answer, a missing key is a bug.

After writing the file, post handoff message §10-A.

---

## 3A. Allergy Safety Contract (non-negotiable)

Allergen handling is the one path in Gate A where a wrong answer is dangerous rather than embarrassing. It therefore does **not** depend on model judgment.

### The rule
The allergen verdict is computed in deterministic Python inside your wrapper layer. The model receives the already-computed verdict and is only allowed to phrase it. The model never decides whether an allergen is present, and it can never downgrade a verdict.

`app/allergy_gate.py` is an **enforcement layer, not business logic** — it stays in place even after Person 2's Knowledge Base retrieval lands. Two independent checks on an allergen path is the intended design, not duplication.

### Verdict table (no other outcomes allowed)
| Condition | Forced status | Language |
|---|---|---|
| Allergen matches an identified food (direct or alias) | `conflict` | Name the allergen and the matched food |
| Any identified food is below the confidence floor, or `is_approximate` is true, or a composite dish is unresolved | `caution` | "cannot confirm this is free of `<allergen>`" |
| Profile is missing, empty, or failed to load | `caution` | "no profile available, allergens not checked" |
| `check_safety` failed or the KB returned nothing | `caution` | "allergen check unavailable" — never `ok` |
| Profile has allergies, all foods confidently identified, no match | `ok` | "no known match for `<allergens>` in the identified items" |
| Profile lists no allergies | `ok` | Say allergens were not part of this check |

Escalation is one-way: `ok → caution → conflict`. Any code path may raise the status. **No path may lower it.** Implement this as a `max()` over an ordered enum so a downgrade is structurally impossible.

### Matching rules
1. Normalise both sides: lowercase, trim, collapse whitespace, drop punctuation, naive singularisation.
2. Match on whole tokens as well as substrings of the food `label`, and on the alias table below.
3. Confidence floor: `0.60`. Below it, no `ok` verdict is possible regardless of match result. (Chosen default — tune once with the demo photo, then freeze.)
4. Ambiguity resolves toward caution. Always.

Minimum alias table (extend, never shrink):

```text
milk / dairy   -> cheese, butter, yogurt, cream, ghee, paneer, whey, custard, ice cream
egg            -> mayonnaise, mayo, albumen, meringue, omelette, frittata
peanut         -> groundnut, peanut butter, satay
tree nut       -> almond, cashew, walnut, pecan, pistachio, hazelnut, macadamia, praline
wheat / gluten -> bread, pasta, noodles, flour, couscous, semolina, breadcrumb, batter, roti, tortilla
soy            -> soya, tofu, edamame, miso, tempeh, soy sauce
fish           -> salmon, tuna, cod, anchovy, sardine, fish sauce
shellfish      -> shrimp, prawn, crab, lobster, crayfish, scallop, mussel, clam, oyster
sesame         -> tahini, hummus, halva, za'atar
mustard        -> dijon, mustard seed
sulphite       -> wine vinegar, dried fruit
```

Composite or sauced dishes are inherently unverifiable from a photo: a matched composite (curry, stew, casserole, dressing, marinade, "mixed") sets `match_type = "unverifiable"` and forces `caution` at minimum, even with no direct token match.

### Language rules
- Never output the word "safe", "safe to eat", or "allergen-free". Only "no known match found in the identified items".
- Never state severity, reaction likelihood, or anything about anaphylaxis, antihistamines, epinephrine, or dosing. That is diagnosis and treatment — it is blocked by P1-05 and must never be generated in the first place.
- Always name the specific allergen and the specific matched food. A vague warning is a failed warning.
- Always carry the non-diagnostic disclaimer and a "confirm with your clinician or the ingredient label" line.
- The conflict must appear in the tool output itself, not only in the model's prose, so the UI can render it independently of the model.

### Interaction with the rest of your slice
- **P1-02 wrappers:** `check_safety` returns only after `allergy_gate` has run over the result. The gate is the last thing the wrapper does before returning.
- **P1-05 guardrail:** verify the guardrail redirect does not swallow or blank a legitimate allergen conflict. A guardrail that silences the warning is worse than no guardrail. Test both together.
- **P1-04 memory:** allergies may be cached for conversational context, but the profile is the only source of truth. Re-read the profile every request; never let a remembered allergen list substitute for a fresh `get_profile` call, and never persist allergy data as a medical record.
- **Stubs:** `app/stubs.py` must ship one profile carrying a real allergy (the demo persona) so the conflict path is exercised from minute one, not discovered at integration.

### Required tests (add to `tests/test_safety_allergy.py`)
1. Direct match → `conflict`, allergen and food both named.
2. Alias match (profile says `milk`, photo has `cheese`) → `conflict`.
3. Low-confidence food, no match → `caution`, never `ok`.
4. Composite dish, no direct match → `caution` with `match_type = "unverifiable"`.
5. Missing/empty profile → `caution`, no claim made.
6. `check_safety` raises or returns empty → `caution`, never `ok`.
7. Clean meal, confident identification → `ok`, and the output contains no form of the word "safe".
8. Downgrade attempt: feed a `conflict` through the gate again with clean inputs → still `conflict`.
9. Output of every case contains the disclaimer and no diagnosis or treatment language.

### Evidence to capture
One `agentcore dev` transcript showing the demo persona's allergen conflict, with the allergen and matched food named in the structured output, plus the test summary line for the nine cases above. This is also the strongest safety moment in the demo — hand it to Person 3.

---

## 4. Task Pathway

Work top to bottom. Each task ends with evidence or a logged fallback.

### P1-01 — Strands agent baseline
- **Timebox:** 20 min (start 0:15, hard stop 0:35)
- **Depends on:** Preflight
- **MCP first:** `bedrock-agentcore` → CLI project creation, entrypoint contract. `strands-agents` → `Agent`, `BedrockModel`, system prompt.
- **Do:**
  1. From repo root: `agentcore create --name nutriguard --framework Strands --model-provider Bedrock --memory shortTerm --build CodeZip`
  2. `cd nutriguard` and list the generated tree; record the real entrypoint path.
  3. Write the NutriGuard system prompt into the entrypoint: identifies food from a photo, estimates portions, retrieves grounded USDA macros, checks the meal against the user profile, logs it, updates the dashboard. It states uncertainty out loud, says `unknown` when data is missing, and gives no diagnosis or treatment instruction — it defers to a clinician.
  4. Keep the model on Claude Sonnet in `us-west-2`. Type-hint every function.
  5. Add `tests/test_agent_baseline.py`: assert the agent builds, the system prompt contains the non-diagnosis clause, and the tool registry is non-empty. **Watch it fail first**, then make it pass.
- **Verify:**
  ```cmd
  agentcore dev --logs
  agentcore dev "Log a plate of grilled chicken and rice for user demo-1"
  ```
  Windows port conflict: `netstat -ano | findstr :8080` then `taskkill /PID <pid> /F`, or `agentcore dev -p 3000`.
- **Done when:** local invoke returns a coherent response and the baseline test passes.
- **Fallback:** if the CLI scaffold fails, hand-write a minimal `BedrockAgentCoreApp` entrypoint with `@app.entrypoint` and proceed; note it.

### P1-02 — Typed `@tool` wrappers
- **Timebox:** 30 min (hard stop 1:05)
- **Depends on:** P1-01, §3 contract. Person 2's real modules are *optional* here.
- **MCP first:** `strands-agents` → `@tool` decorator, tool specs, docstring/type-hint requirements, error handling.
- **Do:**
  1. `app/stubs.py`: deterministic fixture returns for all six required tools, matching §3 exactly. Mark each with `SOURCE = "stub"`.
  2. `app/agent_tools.py`: one `@tool` per contract entry. Each wrapper is *thin* — validate input, call business logic, normalise the result, return structured output. No business logic in the wrapper.
  3. Resolve implementations dynamically: try `src.nutriguard.*`, fall back to `app.stubs`, and set a `source` field so a stub is always visible in the response. Never silently fake real data.
  4. Explicit failure behaviour per tool: bad image path → structured error, not an exception; unknown food → `"unknown"` macros; missing profile → `caution` safety result with no claim.
  5. Register all wrappers on the agent. `suggest_recipe` stays commented out until §6 is fully green.
  6. `tests/test_tool_contracts.py`: for each tool, assert required keys, types, the `unknown` path, and the malformed-input path. Include `allergen_conflicts` in the required keys for `check_safety`.
- **Verify:** run the contract test suite; then `agentcore dev "What's in this photo: tests/fixtures/demo_meal.jpg"` and confirm the tool chain fires in the dev logs.
- **Done when:** contract tests pass and the agent selects tools in the intended order.
- **Fallback:** if a tool's shape is contested, keep the stub, log the mismatch, post §10-B. Do not change the contract unilaterally.

### P1-02A — Allergen gate (required, never cut)
- **Timebox:** 15 min (hard stop 1:20)
- **Depends on:** P1-02
- **MCP first:** none needed — this is pure local logic. Skip the doc step and spend the time on the tests.
- **Do:**
  1. `app/allergy_gate.py`: ordered status enum with one-way escalation via `max()`, the normaliser, the alias table, and the `0.60` confidence floor from §3A. Type-hint everything.
  2. Call the gate as the final step inside the `check_safety` wrapper, so it runs whether the underlying implementation is Person 2's KB path or your stub.
  3. Put the demo persona's real allergy into `app/stubs.py` so the conflict path runs from the start.
  4. `tests/test_safety_allergy.py`: all nine cases from §3A. Watch the downgrade test and the "no `safe` wording" test fail first.
- **Verify:** the nine allergy tests pass, and `agentcore dev "<demo prompt for the persona with the allergy>"` names both the allergen and the matched food in the structured output.
- **Done when:** every §3A verdict-table row is covered by a passing test and no output path can produce `ok` from a failed or low-confidence check.
- **Fallback:** none. If you are out of time, cut Memory (P1-04) and any polish instead. Shipping the allergen path on model judgment alone is not an acceptable outcome.

### P1-03 — SSM configuration loader
- **Timebox:** 20 min (hard stop 1:40)
- **Depends on:** AWS access
- **MCP first:** `aws-documentation` → SSM Parameter Store `get_parameters` / `get_parameters_by_path`, IAM permissions for AgentCore execution roles.
- **Do:**
  1. Create parameters under a single prefix:
     ```cmd
     aws ssm put-parameter --name /nutriguard/gate-a/table_name --value <table> --type String --overwrite --region us-west-2 --no-cli-pager
     aws ssm put-parameter --name /nutriguard/gate-a/bucket_name --value <bucket> --type String --overwrite --region us-west-2 --no-cli-pager
     aws ssm put-parameter --name /nutriguard/gate-a/kb_id --value <kb-id> --type String --overwrite --region us-west-2 --no-cli-pager
     aws ssm put-parameter --name /nutriguard/gate-a/guardrail_id --value <id> --type String --overwrite --region us-west-2 --no-cli-pager
     aws ssm put-parameter --name /nutriguard/gate-a/guardrail_version --value <version> --type String --overwrite --region us-west-2 --no-cli-pager
     ```
  2. `app/config.py`: typed, cached loader by path prefix. Missing parameter → clear startup error naming the parameter, never a silent default. Region fixed to `us-west-2`.
  3. `tests/test_config_ssm.py`: mock the SSM client — success, missing parameter, and cache-hit cases.
  4. Grep the whole project for hardcoded identifiers and remove any you find in your files.
- **Verify:** `aws ssm get-parameters-by-path --path /nutriguard/gate-a --region us-west-2 --no-cli-pager` plus the mocked tests passing.
- **Done when:** no resource identifier appears anywhere in your files and the loader test suite passes.
- **Fallback:** if IAM blocks SSM writes, read from `agentcore/.env.local` behind the *same* `config.py` interface, log the deviation, and keep `.env.local` gitignored.

### P1-05 — Guardrails (do this before P1-04; safety outranks Memory)
- **Timebox:** 15 min (hard stop 1:55)
- **Depends on:** P1-01, P1-02A, P1-03
- **MCP first:** `aws-documentation` → Bedrock Guardrails create/version, denied topics. `strands-agents` → `BedrockModel` guardrail parameters (`guardrail_id`, `guardrail_version`, `guardrail_trace`).
- **Do:**
  1. Create a guardrail whose denied topics cover medical diagnosis, treatment plans, and dosage advice — including allergy-reaction treatment (antihistamines, epinephrine, dosing) — with a redirect message pointing to a clinician. Publish a version.
  2. Wire `guardrail_id` / `guardrail_version` into `BedrockModel` from `config.py`.
  3. `tests/test_safety_guardrail.py`: a diagnostic prompt ("do I have diabetes, what should I take") must be redirected, and normal nutrition questions must still work (no false positive).
  4. **Allergen interaction test:** run the persona's allergen-conflict meal through the guarded agent and assert the conflict still surfaces with the allergen and food named. A guardrail that blanks a real warning is a failure, not a safety win.
- **Verify:** `agentcore dev "Based on this meal do I have diabetes and what medication should I take?"` → redirect, no diagnosis, no treatment. Then the allergen-conflict prompt → warning intact.
- **Done when:** redirect confirmed, the benign prompt still answers, and the allergen conflict survives the guardrail.
- **Fallback:** enforce refusal in the system prompt plus a wrapper-level check, label it as prompt-level only in the demo, and log that the managed guardrail is pending.

### P1-04 — Minimal Memory integration
- **Timebox:** 15 min (hard stop 2:05) — **first thing cut if behind**
- **Depends on:** P1-01
- **MCP first:** `bedrock-agentcore` → `agentcore add memory`, Strands memory integration, session/actor identifiers.
- **Do:**
  1. `agentcore add memory --name NutriGuardMemory --strategies SEMANTIC`
  2. Attach memory so profile context (allergy, sugar limit) survives a second request in the same session. Store no medical documents, no images.
  3. Keep the §3A rule intact: the allergen gate always re-reads the profile. Memory adds conversational continuity, never the authoritative allergy list.
  4. One test or a recorded two-turn dev invoke as evidence.
- **Verify:** two sequential `agentcore dev` calls where the second reflects context from the first.
- **Done when:** context carries across turns, or the task is explicitly cut and logged.
- **Fallback:** cut it. Demo the profile via `get_profile` instead and say so plainly.

### P1-06 — Runtime deployment (required)
- **Timebox:** 15 min (hard stop 2:40)
- **Depends on:** P1-02, P1-03, integration §5 complete
- **MCP first:** `bedrock-agentcore` → deploy, execution role permissions, troubleshooting.
- **Do:**
  1. `agentcore validate`
  2. `agentcore deploy --dry-run` then `agentcore deploy -v`
  3. Confirm the execution role can read your SSM prefix, the KB, the table, the bucket, and the guardrail. Add missing permissions — this is the most common failure.
  4. `agentcore status`
  5. `agentcore invoke "<the exact demo prompt>"`
- **Verify:** one real deployed request returns a valid structured response.
- **Done when:** deployed invoke succeeds, or the 10-minute rule fires.
- **Fallback:** after 10 minutes of failures, stop. Keep the verified local demo, capture the error text and the failing resource, and prepare an honest one-line explanation.

### P1-07 — CloudWatch / trace evidence
- **Timebox:** 10 min (hard stop 2:50)
- **Depends on:** P1-06
- **MCP first:** `aws-documentation` → AgentCore observability, CloudWatch Transaction Search enablement.
- **Do:**
  1. Enable Transaction Search if not already on.
  2. `agentcore logs` and `agentcore traces list`
  3. Capture one screenshot showing the multi-tool chain. Redact account IDs, ARNs, and user data.
- **Done when:** the tool sequence is visible in logs or traces with nothing sensitive on screen.
- **Fallback:** show the dev-server log of the local tool chain plus the architecture diagram.

---

## 5. Integration — T+1:35 → 2:05 (you lead)

Merge in dependency order. After **each** merge, run the affected tests before the next merge.

```cmd
git checkout main && git pull
git merge feature/vision-data        && python -m pytest -q
git merge feature/agentcore-platform && python -m pytest -q
git merge feature/product-ui         && python -m pytest -q
```

1. **Swap stubs for real code.** Once `src/nutriguard/*` exists, the dynamic resolver in `agent_tools.py` picks it up. Confirm each tool reports `source != "stub"`, or explicitly list which stubs remain.
2. **Contract mismatches** are fixed in the contract and by the owning person — you adapt only your wrapper's normalisation layer. Do not rewrite Person 2's modules.
3. **Any surviving stub** that affects a demo claim must be either replaced before P1-06 or removed from the demo narrative.
4. Walk the full journey locally and confirm each hop:
   ```text
   upload -> identify -> confirm/edit -> portion -> macros -> safety -> log -> dashboard
   ```
5. Commit small. Do not squash unrelated work. Do not bypass hooks. Do not force-push shared branches.

---

## 6. Pre-Demo Verification Gate (all must be green)

- [ ] Unit + contract tests pass — paste the summary line
- [ ] Type check passes on `nutriguard/app/**`
- [ ] Lint passes on `nutriguard/app/**`
- [ ] Local end-to-end photo→dashboard works
- [ ] Diagnostic prompt is redirected (P1-05 evidence)
- [ ] All nine §3A allergy tests pass
- [ ] Allergen conflict names both the allergen and the matched food in the structured output, not only in prose
- [ ] No output path can return `ok` from a failed, missing-profile, or low-confidence allergen check
- [ ] Grep confirms no meal output uses "safe", "safe to eat", or "allergen-free"
- [ ] Allergen conflict survives the guardrail (P1-05 step 4)
- [ ] Malformed image, missing profile, unknown food, failed lookup all degrade gracefully
- [ ] `git ls-files` shows no credentials, tokens, medical data, or photos
- [ ] Zero hardcoded ARNs / IDs / buckets / tables in your files
- [ ] Every AWS CLI command used `--no-cli-pager` and `--region us-west-2`
- [ ] Deployed invoke succeeded **or** local fallback is documented with the real error
- [ ] Remaining stubs are listed and none of them backs a demo claim

Only after all boxes are green may you consider `suggest_recipe`. Gate B stays untouched regardless.

---

## 7. Anti-Drift Self-Check (run before every file write)

1. Is this file inside my "You own" list? If no → stop, post a handoff message.
2. Is this task the current one in §4? If no → stop.
3. Did I query the MCP docs for this task? If no → do that first.
4. Is it in Gate A scope, or did I drift into Gate B? Drift → delete it.
5. Am I within the timebox? Over → take the fallback and log it.
6. Do I have evidence for the previous task? If no → get evidence before writing more code.
7. Does this add a resource identifier, credential, or nutrition value from nowhere? → stop.
8. Does this touch an allergen path? Then: is the verdict still deterministic, still one-way escalating, and still tested? Any "no" → stop and fix before continuing.

---

## 8. Cut Order When Behind

Cut in this order, log each cut, never negotiate:

1. `suggest_recipe` (P1-07 optional path)
2. AgentCore Memory (P1-04)
3. Managed Guardrails → prompt-level refusal only (P1-05 fallback)
4. Live deployment → verified local demo (P1-06 fallback)
5. CloudWatch screenshot → dev-server log (P1-07 fallback)

Extending the alias table beyond the §3A minimum is polish and may be cut. The gate itself, its one-way escalation, and its nine tests may not.

Never cut: P1-01, P1-02, P1-03, the local end-to-end journey, or the non-diagnosis safety behaviour.

---

## 9. Evidence Log — create `EVIDENCE_P1.md` and append per task

```markdown
## <TASK ID> — <name>
Docs consulted: <MCP server> → <doc titles>
Command: <exact command>
Result: <output summary / test line>
Status: pass | fallback taken
Notes: <stubs remaining, deviations, cuts>
Real generated paths: <entrypoint path, config paths>
```

---

## 10. Handoff Messages (copy-paste, don't paraphrase)

**§10-A — after publishing the contract (by 0:20):**
> Contract frozen at `docs/contracts/gate_a_tools.md`. Person 2: implement against these exact field names in `nutriguard/src/nutriguard/`. Person 3: build against this shape. Missing values are the string `unknown`, never a guess. Every `SafetyResult` carries a non-diagnostic disclaimer and an `allergen_conflicts` list — empty list is a valid answer, a missing key is a bug. Renaming a field needs all three of us to agree.

**§10-D — allergen rules, send with §10-A:**
> Allergen verdicts are computed deterministically in `app/allergy_gate.py`, not by the model, and the gate runs on the result of `check_safety` regardless of who implemented it. Person 2: return whatever the KB gives you, including empty — the gate handles escalation, so don't try to decide the verdict yourself, and never return `ok` on a failed lookup. Person 3: render `allergen_conflicts` from the structured output directly, name the allergen and the matched food, and never display "safe" or "allergen-free" anywhere in the UI. Allowed phrasing is in §3A of `PERSON1_GATE_A_PLAN.md`.

**§10-B — contract mismatch found during integration:**
> Mismatch in `<tool>`: contract expects `<field/type>`, implementation returns `<actual>`. I'm keeping my stub for this tool until it's fixed by the owner. Not editing your module.

**§10-C — blocked on a dependency:**
> `<task>` is blocked on `<dependency>`. Continuing behind a labelled stub. The demo will not claim this path works until the real implementation lands.

---

## 11. Timeline at a Glance

| Time | Task | Hard stop |
|---|---|---|
| 0:00–0:15 | Preflight §1 | 0:15 |
| 0:15–0:35 | P1-01 agent baseline | 0:35 |
| 0:20 | Publish contract §3 + msg §10-A | 0:25 |
| 0:35–1:05 | P1-02 `@tool` wrappers | 1:05 |
| 1:05–1:20 | P1-02A allergen gate (never cut) | 1:20 |
| 1:20–1:40 | P1-03 SSM loader | 1:40 |
| 1:40–1:55 | P1-05 Guardrails + allergen interaction | 1:55 |
| 1:55–2:05 | P1-04 Memory (cuttable, cut this first) | 2:05 |
| 1:35–2:05 | §5 integration (you lead, overlaps) | 2:05 |
| 2:05–2:25 | §6 verification gate | 2:25 |
| 2:25–2:40 | P1-06 deploy | 2:40 |
| 2:40–2:50 | P1-07 observability evidence | 2:50 |
| 2:50–3:00 | Hand to Person 3 for demo, freeze code | 3:00 |

---

## Sources

- [Get started with the AgentCore CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html)
- [Get started with AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-get-started.html)
- [Strands Agents — Bedrock model provider API](https://strandsagents.com/docs/api/python/strands.models.bedrock/)
- [Strands Agents — deploy to AgentCore Runtime (Python)](https://strandsagents.com/docs/user-guide/deploy/deploy_to_bedrock_agentcore/python/)

Content informed by these sources was rephrased for compliance with licensing restrictions.
