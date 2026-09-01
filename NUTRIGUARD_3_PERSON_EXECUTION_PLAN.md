# NutriGuard AI — 3-Person, 3-Hour Execution Plan

## 1. Delivery Strategy

Use two delivery gates:

- **Gate A — 3-hour hackathon:** Ship a deployed, judge-ready MVP with a polished photo-to-dashboard journey and visible AgentCore orchestration.
- **Gate B — Post-hackathon/multi-day:** Add the complete local vision pipeline, broader evaluation, performance work, and advanced product features.

Gate A must work independently. Do not start Gate B work until the Gate A demo has passed end-to-end.

## 2. Product Goal

**NutriGuard AI — “See it, log it, stay safe.”**

A user uploads a meal photo. NutriGuard identifies likely foods, estimates portions, retrieves grounded nutrition values, checks the meal against a user profile, logs it, and updates a daily dashboard. It provides cautious nutrition guidance—not medical diagnosis or treatment advice.

### Gate A scope

Build only:

- Structured user profile; no medical-document parsing.
- Photo upload; no live camera or voice.
- Reliable managed/lightweight food identification path.
- Approximate portion estimate with an explicit uncertainty label.
- USDA-backed calories, protein, carbohydrates, fat, and sugar.
- Knowledge Base safety check against allergies and profile notes.
- Meal log and daily dashboard with sugar highlighted.
- One recipe-suggestion path if the core journey finishes early.
- AgentCore Runtime/Gateway, Guardrails, Memory, and CloudWatch evidence where practical.

Cut from Gate A:

- SAM 2 segmentation.
- Full Grounding DINO/SigLIP/Depth Anything pipeline.
- Trained portion model.
- OCR, barcode scanning, PDF ingestion, voice, weekly reports, and trend charts.

## 3. Three-Person Team Division

| Person | Role | Branch | Primary ownership |
|---|---|---|---|
| Person 1 | AgentCore and Integration Lead | `feature/agentcore-platform` | Strands agent, tool registration, SSM configuration, AgentCore deployment, Guardrails, Memory, CloudWatch, final integration |
| Person 2 | Vision, Nutrition, and Data Lead | `feature/vision-data` | Food identification adapter, portion heuristic, USDA lookup, Knowledge Base safety retrieval, DynamoDB/S3 adapters |
| Person 3 | Product UI, Test, and Demo Lead | `feature/product-ui` | Upload UI, result panel, dashboard, API client, browser smoke test, accessibility, demo and judge narrative |

Each person owns implementation, tests, and documentation for their slice. Person 1 integrates but does not silently rewrite another person's subsystem.

## 4. Compressed Seven-Phase Workflow

Use the discipline of `obra/superpowers` for lifecycle control and `addyosmani/agent-skills` for verification gates:

1. **Brainstorm (5 minutes):** confirm persona, demo moment, constraints, and cuts.
2. **Spec (5 minutes):** agree on tool contracts, data shapes, safety boundary, and acceptance criteria.
3. **Plan (5 minutes):** assign the task ledger and dependency order.
4. **TDD (throughout):** add focused tests before behavior where practical.
5. **Subagent development (parallel build):** each person works only on their owned slice.
6. **Review (20 minutes):** merge in dependency order and verify behavior, security, and interfaces.
7. **Finalize (25 minutes):** deploy, smoke-test, rehearse, and freeze.

No task is complete because it “looks right.” Completion requires command output, a passing test, a successful build, or a real smoke-test result.

## 5. Skill Setup

Before coding, each teammate checks whether these skills are already workspace-scoped. Import missing skills through Kiro's **Agent Steering & Skills** panel from their official GitHub skill subfolders, then commit the workspace skill files so everyone shares the same behavior.

### Shared lifecycle skills from `obra/superpowers`

- Brainstorming
- Writing plans
- Subagent-driven development
- Systematic debugging
- Requesting code review
- Finishing a development branch

### Shared quality skills from `addyosmani/agent-skills`

- `test-driven-development`
- `code-review-and-quality`
- `debugging-and-error-recovery`
- `security-and-hardening`

Do not activate two competing TDD skills at once. Use Addy Osmani's TDD skill as the test authority and Superpowers for the wider lifecycle.

### Role-specific emphasis

- **Person 1:** API/interface design, observability, deployment, and review.
- **Person 2:** TDD, source-driven development, debugging, and performance.
- **Person 3:** frontend UI engineering, browser testing, accessibility, and demo preparation.

### Skill acceptance criteria

- [ ] Every teammate can see the shared skills in Kiro.
- [ ] Only one TDD workflow is active.
- [ ] Review and debugging skills can be invoked.
- [ ] `.kiro/` and project skill directories are not ignored by Git.

## 6. Shared Project Rules

- Consult current AWS, AgentCore, and Strands documentation through MCP before integration work.
- Use Python type hints and short explanatory comments.
- Use the Strands `@tool` decorator for agent-facing tools.
- Keep `@tool` wrappers separate from business logic.
- Target AWS `us-west-2`.
- Include `--no-cli-pager` in AWS CLI commands.
- Load resource identifiers from SSM parameters; never hardcode ARNs, IDs, buckets, or table names.
- Never commit AWS credentials, temporary tokens, medical data, or uploaded photos.
- Never invent nutrition values; return `unknown` when source data is missing.
- Never provide diagnosis or treatment instructions.
- Prefer a visible approximation/fallback over hidden uncertainty.
- Keep the MVP minimal and demo-focused.

## 7. Gate A Architecture

```text
Photo Upload UI
      |
      v
AgentCore Gateway / Runtime
      |
      v
Strands NutriGuard Agent
      |
      +-- identify_food
      +-- estimate_portion
      +-- get_macros
      +-- check_safety
      +-- log_meal
      +-- get_profile
      +-- suggest_recipe (only if time remains)
      |
      +-- Bedrock Knowledge Base
      +-- AgentCore Memory
      +-- Bedrock Guardrails
      +-- DynamoDB / S3
      +-- CloudWatch
```

### Tool contracts

```python
identify_food(image_path: str) -> list[FoodItem]
estimate_portion(image_path: str, foods: list[FoodItem]) -> list[FoodItem]
get_macros(foods: list[FoodItem]) -> MacroBreakdown
check_safety(meal: MacroBreakdown, profile: UserProfile) -> SafetyResult
log_meal(user_id: str, meal: MealRecord) -> None
get_profile(user_id: str) -> UserProfile
suggest_recipe(profile: UserProfile, remaining: MacroBreakdown) -> Recipe
```

Every tool requires type hints, a concise docstring, a structured result, and explicit failure behavior.

## 8. Three-Hour Timeline

| Time | Phase | Owners | Required output |
|---|---|---|---|
| 0:00–0:15 | Brainstorm, spec, plan, skills check | Everyone | Frozen MVP, contracts, branches, assigned task IDs |
| 0:15–1:35 | Parallel TDD build | All three | Three independently testable slices |
| 1:35–2:05 | Integrate Data → AgentCore → UI | Person 1 leads | Complete local photo-to-dashboard flow |
| 2:05–2:25 | Review and harden | Everyone | Tests/build pass; secrets and safety checked |
| 2:25–2:40 | Deploy and production smoke test | Persons 1 and 2 | Deployed endpoint and one successful request |
| 2:40–3:00 | Demo rehearsal and submission | Person 3 leads | Rehearsed demo, evidence, fallback screenshots |

### 0:00–0:15 — Setup and freeze

Everyone:

- Verify Git branches, AWS access, SSM parameters, Knowledge Base status, model access, and MCP connections.
- Confirm no credentials are tracked by Git.
- Confirm skills are available.
- Agree on JSON/tool contracts.
- Select one representative meal photo and one user profile.
- Freeze the Gate A cuts; no new feature may enter without removing another.

### 0:15–1:35 — Parallel build

#### Person 1

- Scaffold the Strands agent and system prompt.
- Add typed tool wrappers using agreed contracts.
- Load configuration from SSM.
- Add the minimum AgentCore Runtime/Gateway configuration.
- Apply Guardrails and basic CloudWatch instrumentation.
- Prepare deployment while local integration continues.

#### Person 2

- Define shared domain models and sample responses first.
- Implement a reliable food-identification adapter.
- Implement an approximate portion heuristic.
- Implement USDA-backed macro lookup.
- Implement Knowledge Base safety retrieval.
- Implement minimal meal/profile persistence.
- Provide fixtures to Persons 1 and 3 immediately.

#### Person 3

- Build the UI against mocked fixture responses.
- Add photo upload and detected-food confirmation/editing.
- Add macros and safety-result panels.
- Add the daily dashboard and sugar warning.
- Add loading, empty, retry, and error states.
- Prepare the demo script and one browser smoke test.

### 1:35–2:05 — Integration

Merge order:

1. `feature/vision-data`
2. `feature/agentcore-platform`
3. `feature/product-ui`

After each merge, run targeted tests and fix contract mismatches immediately. Stub non-critical AWS behavior rather than blocking the whole flow, but clearly label the stub and replace it before the production smoke test if it affects the demo claim.

Required integrated journey:

```text
Upload photo
-> identify food
-> confirm/edit foods
-> estimate portion
-> retrieve grounded macros
-> check profile safety
-> log meal
-> update dashboard
```

### 2:05–2:25 — Review and hardening

- Run code review and security skills.
- Run unit, tool-contract, and browser smoke tests.
- Run type checks, lint, and build.
- Search tracked files for credentials or hardcoded resource identifiers.
- Test malformed image, missing profile, unknown food, and failed lookup behavior.
- Confirm safety output avoids diagnosis and treatment claims.

### 2:25–2:40 — Deploy

- Deploy with AgentCore.
- Run one real deployed request.
- Confirm CloudWatch shows the agent/tool flow.
- Record only non-sensitive evidence.
- If deployment fails after 10 minutes, preserve the verified local demo and capture the deployment error for honest explanation.

### 2:40–3:00 — Finalize

- Rehearse the demo twice.
- Take fallback screenshots.
- Freeze the code after a successful rehearsal.
- Write the short Kiro/skills/process explanation.
- Prepare the judge evidence checklist.

## 9. Gate A Task Ledger

| ID | Owner | Task | Depends on | Acceptance criterion |
|---|---|---|---|---|
| P1-01 | Person 1 | Strands agent baseline | Shared setup | Agent responds locally and targeted test passes |
| P1-02 | Person 1 | Typed `@tool` wrappers | P2-01 | Agent validates arguments and selects tools |
| P1-03 | Person 1 | SSM configuration loader | AWS access | No resource identifier is hardcoded |
| P1-04 | Person 1 | Minimal Memory integration | P1-01 | Relevant profile context survives another request |
| P1-05 | Person 1 | Guardrails | P1-01 | Diagnostic request is safely redirected |
| P1-06 | Person 1 | Runtime/Gateway deployment | P1-02, P1-03 | Deployed endpoint returns a valid response |
| P1-07 | Person 1 | CloudWatch evidence | P1-06 | Tool execution is visible without exposing secrets |
| P2-01 | Person 2 | Shared domain models and fixtures | None | Valid and invalid fixtures are tested |
| P2-02 | Person 2 | Food-identification adapter | P2-01 | Demo image returns labels and confidence |
| P2-03 | Person 2 | Portion heuristic | P2-02 | Returns grams plus approximation/confidence flag |
| P2-04 | Person 2 | USDA lookup | P2-01 | Known food returns sourced macros; missing data is unknown |
| P2-05 | Person 2 | RAG safety checker | P2-04 | Conflict response includes evidence and no diagnosis |
| P2-06 | Person 2 | Minimal persistence | P1-03 | Meal write/read test passes |
| P3-01 | Person 3 | UI shell and mocked client | P2-01 fixtures | Responsive UI renders against fixtures |
| P3-02 | Person 3 | Upload and confirmation | P3-01 | User can upload and edit detected foods |
| P3-03 | Person 3 | Results and safety panel | P2 contracts | Macros, uncertainty, and warnings are clear |
| P3-04 | Person 3 | Dashboard | P2-06 | Logged meal updates totals and sugar state |
| P3-05 | Person 3 | Browser smoke and error states | P3-02 | Core journey and one failure path pass |
| P3-06 | Person 3 | Demo and judge narrative | Integrated build | Demo fits 4–5 minutes and has fallback evidence |

### Priority rule

Tasks P1-01/02/03/06, P2-01/02/03/04/05, and P3-01/02/03/04 are required. Memory, advanced persistence, recipe suggestions, and extra polish are cut first if the schedule slips.

## 10. Testing and Verification Requirements

No task is complete without evidence.

### Minimum 3-hour test set

- Unit tests for domain models, macro transformation, and portion flags.
- Contract tests for each implemented `@tool`.
- Mocked AWS tests for SSM and the Knowledge Base adapter.
- One agent orchestration test covering the core tool sequence.
- One browser smoke test for upload-to-dashboard.
- One safety test for a diagnosis/treatment request.
- One deployed smoke test if deployment succeeds.

### Verification gates

For each task:

1. Observe a focused failure before implementing behavior where practical.
2. Make the targeted test pass.
3. Run affected tests.
4. Run type checking and linting for affected code.
5. Record the command and result in the task or pull request.

Before demo freeze:

- [ ] Unit and contract tests pass.
- [ ] Type check passes.
- [ ] Lint passes.
- [ ] Production build passes.
- [ ] Local end-to-end smoke test passes.
- [ ] Deployed smoke test passes or the local fallback is documented.
- [ ] No credentials or medical data are tracked by Git.

## 11. Judge-Aligned Scorecard

| Criterion | Evidence to present |
|---|---|
| Agentic depth | Visible multi-tool chain, structured tools, Memory/Guardrails/Gateway where completed, and failure recovery |
| Technical execution | Deployed or locally verified AgentCore runtime, typed contracts, SSM configuration, tests, and build output |
| Innovation | Portion-aware nutrition analysis instead of food-name-only classification |
| AWS integration | Bedrock, AgentCore, Knowledge Base, DynamoDB/S3, Guardrails, and CloudWatch |
| User impact | Faster meal logging and profile-aware nutrition safety guidance |
| Safety | Grounded nutrition data, source-aware warnings, visible uncertainty, and no diagnosis claims |
| UX and polish | Fast upload flow, editable detections, understandable dashboard, accessible states |
| Kiro usage | Committed spec, steering, skills, hooks, task ledger, and review evidence |
| Demo quality | Reliable story, clear transformation, visible agent flow, fallback screenshots |
| Feasibility | Working 3-hour MVP plus a credible measured Gate B roadmap |

## 12. Demo Script

1. Introduce a user monitoring sugar and one allergy.
2. Upload the prepared meal photo.
3. Show detected foods and correct one item if useful.
4. Run the analysis.
5. Show approximate portions, confidence, and grounded macros.
6. Show the profile-aware safety explanation.
7. Log the meal.
8. Show the dashboard and sugar state update.
9. Show CloudWatch or the architecture to prove the multi-tool AgentCore flow.
10. Close with Gate B: advanced segmentation, depth-based portions, and measured accuracy.

Target demo length: **4–5 minutes**.

## 13. Gate B — Multi-Day Advanced Track

Only begin after Gate A is stable.

### Advanced vision

```text
Grounding DINO
-> SAM 2
-> SigLIP 2 or DINOv2
-> Qwen-VL or Bedrock low-confidence fallback
-> Depth Anything V2
-> food-density/volume-to-grams model
-> USDA lookup
```

Acceptance evidence:

- Labeled evaluation image set.
- Food detection/classification accuracy.
- Portion mean absolute error.
- Latency per stage.
- Fallback rate and fallback accuracy.
- Comparison against the Gate A adapter.

### Broader reliability

- Full mocked AWS client tests.
- Deployed integration suite.
- Prompt-injection and unsafe-health-advice evaluation.
- Browser end-to-end suite.
- Load, latency, and cost measurements.
- Partial-failure and retry tests.
- Barcode and nutrition-label OCR if time remains.

### Product extensions

- Medical document ingestion with explicit consent.
- Weekly reports and trends.
- Voice input/output.
- Human correction feedback.
- Trained portion model.

## 14. Merge and Review Rules

- Pull `main` before each major task.
- Commit small, reviewable changes every 15–25 minutes.
- Do not combine unrelated changes.
- Require one teammate review per pull request.
- Do not merge failing tests.
- Do not bypass hooks.
- Do not force-push shared branches.
- Do not commit credentials, model weights, user data, or temporary photos.
- Resolve interface disagreements in the shared contract rather than changing both sides independently.

## 15. Risks and Fast Fallbacks

| Risk | Time-box | Fallback |
|---|---|---|
| Vision integration is slow | 15 minutes | Use managed/lightweight Gate A adapter |
| Portion estimate is unreliable | Immediate | Label approximate and allow user correction |
| USDA match is ambiguous | Immediate | Ask user to select from top candidates |
| Knowledge Base retrieval fails | 10 minutes | Return cautious no-evidence result; make no safety claim |
| Backend blocks UI | Immediate | Continue with shared fixtures and mocked client |
| Deployment fails | 10 minutes in deploy phase | Use verified local demo plus honest deployment evidence |
| Teammate blocked | 15 minutes | Stub dependency and request focused review |
| Credentials expire | Immediate | Refresh outside Git and rerun identity verification |

## 16. Definition of Done

- [ ] All three people have assigned roles, branches, and task IDs.
- [ ] The compressed seven-phase workflow is followed.
- [ ] AWS, AgentCore, and Strands MCP servers connect.
- [ ] Required lifecycle and quality skills are available to all teammates.
- [ ] Only one TDD authority is active.
- [ ] Specs, steering, skills, and hooks are committed.
- [ ] AWS operations target `us-west-2`.
- [ ] AWS CLI commands use `--no-cli-pager`.
- [ ] Resource identifiers come from SSM.
- [ ] No credentials, tokens, medical data, or hardcoded AWS resources are tracked.
- [ ] The selected Bedrock model invocation succeeds.
- [ ] Photo-to-dashboard works locally end-to-end.
- [ ] Nutrition values come from a trusted source.
- [ ] Unknown values and uncertainty are explicit.
- [ ] Safety output avoids diagnosis and treatment claims.
- [ ] Required unit, contract, orchestration, browser, and safety tests pass.
- [ ] Type check, lint, and production build pass.
- [ ] Deployment and smoke test succeed, or the verified local fallback is ready.
- [ ] Kiro workflow evidence is preserved in the repository.
- [ ] Demo is rehearsed twice and fallback screenshots are ready.
- [ ] Gate A remains stable regardless of Gate B progress.

## 17. Start Now

### Person 1

- Create `feature/agentcore-platform`.
- Start P1-01 with a focused failing test.
- Publish the typed tool interface to the team.

### Person 2

- Create `feature/vision-data`.
- Start P2-01 and publish fixtures within 15 minutes.
- Then implement P2-02 and P2-04 before optional persistence work.

### Person 3

- Create `feature/product-ui`.
- Start P3-01 using Person 2's fixture contract.
- Prepare the demo persona and image while the UI builds.

## Sources

- [obra/superpowers](https://github.com/obra/superpowers)
- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)

Content informed by these sources was rephrased for compliance with licensing restrictions.
