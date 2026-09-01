# NutriGuard AI — Merged Kiro + AgentCore Build Plan

## 0. What's being merged, and why it fits together

Four sources feed this plan:

1. **The 3-hour team playbook** — how 5 people share one repo, one steering file, and parallel Kiro sessions.
2. **The NutriGuard AI PRD** — the product (photo → safety-checked meal → dashboard, plus recipe suggestions), and its AWS Bedrock AgentCore architecture.
3. **The free vision stack** — Grounding DINO → SAM 2 → SigLIP 2/DINOv2 → Qwen-VL → Depth Anything V2 → your own portion model. This becomes the actual code inside the PRD's `identify_food` and `get_macros` tools, instead of a single paid multimodal call for every frame.
4. **The AgentCore workshop pages** — the real CLI + Kiro workflow (`agentcore dev`, `agentcore deploy`, the `@tool` decorator pattern, the pyproject-sync hook) that every role will actually type.

The synthesis: **AgentCore stays the orchestration backbone** (Strands agent, Gateway, Memory, Guardrails, CloudWatch — this is what the "Agentic Depth" judging criterion rewards), but the **vision/macro reasoning is self-hosted and free**, which is both cheaper per-call and the genuine technical differentiator ("photo → volume → grams → accurate macros," per the stack doc). Bedrock's hosted vision models (visible in your model catalog — Claude Sonnet/Opus/Haiku, Nova Pro, **Qwen3 VL 235B**, Pixtral Large, Kimi K2.5, Gemma 3, Nemotron Nano, Palmyra Vision) become the **fallback for mixed/complex dishes** if the local pipeline is too slow or unsure — this is literally the same role Qwen-VL plays in the free stack, just callable as a managed model when you're short on time. Titan Text V2 / Cohere Embed v4 from the catalog's Embeddings row are the natural embedding model for the RAG safety-check against the user's medical profile.

## 1. Time Budget

The playbook targets **3:00 total**; the PRD's own MVP section assumes **~5 hours**. Since the playbook is the concrete team-process document, this plan defaults to **3 hours** and trims the PRD's MVP further (see §9). If your actual event is longer, scale each phase proportionally — the phase *order* doesn't change.

| Time | Phase | Who |
|---|---|---|
| 0:00–0:15 | Confirm scope (§9), assign roles | Everyone |
| 0:15–0:30 | Kiro + AgentCore setup, scaffold baseline agent, commit `.kiro/` | Workflow Lead + everyone reviewing |
| 0:30–2:10 | Parallel build, own branch, own Kiro session | All 5 |
| 2:10–2:35 | Merge in dependency order, hook runs tests | Workflow Lead |
| 2:35–3:00 | Deploy, smoke test, demo run-through, submission notes | Deploy & Demo Lead |

## 2. Roles, Mapped to Real Tools

| # | Role | Owns (concrete) | Branch |
|---|---|---|---|
| 1 | **Frontend/UI** | Camera capture + upload UI, chat panel, dashboard with sugar highlighted, voice STT/TTS if time allows | `feature/frontend` |
| 2 | **Backend/API** | `main.py` agent definition: system prompt, tool registration, AgentCore Gateway exposure for `identify_food`, `get_macros`, `check_safety`, `log_meal`, `get_profile`, `get_remaining_macros`, `suggest_recipe`, `get_report` | `feature/backend` |
| 3 | **Data & AWS Services** | The vision/macro pipeline itself (Grounding DINO → SAM 2 → SigLIP2/DINOv2 → Qwen-VL fallback → Depth Anything V2 → portion heuristic → USDA lookup), DynamoDB schema, S3 storage, Bedrock Knowledge Base ingestion for RAG | `feature/data` |
| 4 | **Kiro Workflow Lead** | Spec (`requirements.md`/`design.md`/`tasks.md`), steering, skills, hooks, merge order, integration pass | `main` |
| 5 | **Deploy & Demo Lead** | `agentcore deploy`, Cognito wiring, Guardrails, final smoke test, demo script, "how we used Kiro" write-up | `feature/deploy` |

## 3. Architecture (merged)

| Layer | Component | Implementation |
|---|---|---|
| Dev workflow | Spec-driven build | **Kiro** |
| Agent runtime | Orchestration | **Bedrock AgentCore Runtime** running a **Strands Agents SDK** agent |
| Vision — detection | Find food items in frame | **Grounding DINO** (open-vocab, Apache 2.0) |
| Vision — segmentation | Separate items on the plate | **SAM 2** *(cut for MVP if time-boxed — see §9)* |
| Vision — recognition | Classify each item | **SigLIP 2 / DINOv2** |
| Vision — complex dishes | Mixed plates (kabsa, biryani, koshari, etc.) | **Qwen-VL** locally, or **Bedrock Qwen3 VL 235B / Claude vision** as a managed fallback |
| Portion estimation | Grams from pixels | **Depth Anything V2 (Small)** + a simple volume→grams heuristic for MVP; a trained portion model is the stretch differentiator |
| Packaged food | Barcode / label shortcut | **ZXing** barcode scan + **PaddleOCR** for nutrition-label text, bypassing vision entirely when available |
| Nutrition data | Macro lookup | **USDA FoodData Central** — never let the model invent numbers |
| Grounding / RAG | Meal vs. medical profile | **Bedrock Knowledge Base on S3 Vectors**, embeddings via **Titan Text V2** or **Cohere Embed v4** |
| Memory | Cross-session recall | **AgentCore Memory** |
| Tool exposure | Function-calling surface | **AgentCore Gateway** |
| Storage | Profiles, logs, reports | **DynamoDB** |
| Object storage | Photos, medical PDFs | **S3** |
| Auth | Sign-up/in | **Cognito** |
| Safety | Scope + block diagnosis claims | **Bedrock Guardrails** |
| Observability | Trace each tool call | **CloudWatch** |
| Runtime for local models | Run vision stack fast | **ONNX Runtime** (CPU-friendly for the 3-hour build; skip GPU provisioning unless someone already has a template) |

## 4. Final Agent Tool Surface

```python
identify_food(image_path: str) -> list[FoodItem]
# Grounding DINO detect -> (SAM2 segment, if time) -> SigLIP2/DINOv2 classify
# -> Qwen-VL / Bedrock vision fallback if confidence is low or dish is mixed

estimate_portion(image_path: str, food_items: list[FoodItem]) -> list[FoodItem]
# Depth Anything V2 Small -> volume estimate -> grams heuristic

get_macros(food_items: list[FoodItem]) -> MacroBreakdown
# USDA FoodData Central lookup; sugar always returned as its own field

check_safety(meal_data: MacroBreakdown, user_profile: dict) -> SafetyResult
# Bedrock Knowledge Base RAG against allergies/doctor notes/goals

log_meal(user_id: str, meal_data: dict) -> None        # DynamoDB write
get_profile(user_id: str) -> dict
get_remaining_macros(user_id: str) -> dict
suggest_recipe(profile: dict, remaining_macros: dict) -> Recipe
get_report(user_id: str, period: str) -> Report
```

## 5. Kiro + AgentCore Setup (0:00–0:30, Workflow Lead drives)

### 5a. Scaffold a working baseline first
Don't start from a blank repo — get one deployed agent with one tool in minutes, then reshape it:

```bash
curl 'https://static.us-east-1.prod.workshops.aws/.../setup.sh' --output setup.sh
bash setup.sh
agentcore invoke --prompt "What time is it, and how many words are in this sentence?"
```

If that baseline works, `app/AssistantAgent/main.py` is your starting file for §6's Backend prompts below.

### 5b. Steering file — `.kiro/steering/conventions.md`
```
Stack: Python, Strands Agents SDK, AWS Bedrock AgentCore Runtime.
Vision pipeline lives in tools/vision/ (detection, segmentation, classification, portion).
Nutrition/agent tools live in tools/nutrition/ and are registered in app/AssistantAgent/main.py.
Never invent nutrition numbers — always call the USDA lookup tool.
Every tool needs a docstring and type hints (the agent relies on both to call it correctly).
Keep tool functions small; business logic separate from Strands @tool wrappers.
```

### 5c. Skills to install into `.kiro/skills/`
| Skill | Source | Give to |
|---|---|---|
| `test-driven-development` | `github.com/addyosmani/agent-skills/tree/main/skills/test-driven-development` | Everyone |
| `code-review-and-quality` | `github.com/addyosmani/agent-skills/tree/main/skills/code-review-and-quality` | Workflow Lead |
| `frontend-design` | `github.com/anthropics/skills/tree/main/skills/frontend-design` | Frontend |

### 5d. Test hook + dependency-sync hook
In Kiro's Hooks panel, describe both in plain language:
> "After a task from the spec is implemented, run the test suite automatically. If tests fail, don't mark the task complete — report what failed."

> "Watch pyproject.toml and run `uv sync` whenever it changes. Run it once now to sync."

The second one matters more here than in the generic workshop example, because the Data role will be adding `torch`, `transformers`, `segment-anything`, etc. mid-build.

### 5e. Light spec
Write `requirements.md`/`design.md` in plain language from PRD §5 and §11 (trimmed per §9 below), let Kiro generate `tasks.md`, and copy each person's tasks into the role table in §2.

## 6. Parallel Build (0:30–2:10) — concrete Kiro prompts per role

### Backend — system prompt + tool registration
```text
Update app/AssistantAgent/main.py to add a system prompt: the agent is
NutriGuard, a nutrition safety co-pilot. It identifies food from photos,
computes macros, checks meals against the user's medical profile, and
never gives medical diagnoses — only "confirm with your doctor" notes.
Register the tools: identify_food, estimate_portion, get_macros,
check_safety, log_meal, get_profile, get_remaining_macros, suggest_recipe,
get_report. Import them from tools/vision and tools/nutrition.
Update pyproject.toml dependencies.
```

### Data & AWS — vision pipeline
```text
In tools/vision/identify.py, add a @tool function
identify_food(image_path: str) -> list[dict] that:
1. Runs Grounding DINO to detect food regions in the image.
2. Classifies each region with SigLIP 2 (or DINOv2), returning label + confidence.
3. If confidence is low or more than 3 items overlap heavily, fall back to
   Qwen-VL for whole-dish understanding.
Return a list of {label, confidence, bbox}. Include docstring and type hints.
```
```text
In tools/vision/portion.py, add estimate_portion(image_path, food_items) that
runs Depth Anything V2 Small to get a depth map, then applies a simple
volume-to-grams heuristic per food label. Flag the estimate as approximate
in the return value.
```
```text
In tools/nutrition/macros.py, add get_macros(food_items) that looks up each
item against a local USDA FoodData Central export and returns calories,
protein, carbs, fat, sugar, and key vitamins. Never estimate values the
lookup doesn't have — return "unknown" instead.
```
**Time-box call:** SAM 2's exact per-item segmentation and a fully trained portion model are the parts most likely to blow the 3-hour budget. Ship the detection→classification→depth-heuristic path first; add SAM 2 masking only if the merge (§7) lands early.

### Frontend
```text
Build the Agent page: photo upload/live camera, chat panel wired to the
agent's Gateway endpoint, and a dashboard showing today's calories,
protein, carbs, fat, vitamins vs. target, with sugar intake highlighted
in a warning color once near/over the threshold.
```

### Deploy & Demo Lead (working ahead in parallel)
- Wire Cognito sign-up/sign-in.
- Draft the Bedrock Guardrails policy: block diagnostic claims, keep the agent scoped to nutrition coaching.
- Prepare the demo script and one realistic test meal photo per team member's feature.

### Workflow Lead
- Floats across branches, unblocks people, keeps `tasks.md` current, prepares the merge order for §7.

## 7. Integration (2:10–2:35)

Merge order: **Data → Backend → Frontend → Deploy** (lowest-dependency first). The test hook fires on each merge — fix failures before moving to the next. Run the `code-review-and-quality` skill for a fast pass once everything is on `main`.

```bash
agentcore dev      # local smoke test after merge
agentcore deploy   # redeploy to AgentCore Runtime
```

## 8. Deploy, Demo & Submission (2:35–3:00)

- Final `agentcore deploy` + smoke test of the full loop: photo → identify → portion → macros → safety check → log → dashboard.
- Run the recipe-suggestion path once too (Feature 2).
- Do **not** gitignore `.kiro/` — it's your proof of how Kiro was used.
- Write 3–4 sentences: what the spec looked like, which skills you used and why, what the test hook caught.
- Run the demo once, live, before presenting.

## 9. MVP Cut for 3 Hours

Build first:
- Structured onboarding form (skip PDF parsing).
- Photo upload (not live video) + text chat.
- Detection → classification → depth-heuristic portion → USDA macros → RAG safety check → log → dashboard, sugar highlighted.
- One on-demand recipe suggestion call.

Cut unless time remains:
- SAM 2 exact segmentation.
- A trained (vs. heuristic) portion model — call this out explicitly in the pitch as "what's next," since it's your named competitive advantage even if the MVP uses the simpler heuristic.
- Live camera feed, full TTS/STT loop, real PDF ingestion, automated weekly reports, multi-day trend charts.

## 10. Pitch Outline (merged)
1. Title & tagline — "See it, log it, stay safe."
2. The problem — one named persona, one moment of friction.
3. The moment of impact — photo in, safety-checked meal out (live demo).
4. Architecture — the table in §3, emphasizing AgentCore orchestration + self-hosted vision.
5. Feature 1 walkthrough — capture & safety check.
6. Feature 2 walkthrough — recipe suggestions.
7. **Agentic depth + the differentiator** — the multi-tool chain (detection → classification → portion → macros → RAG), and why grams-not-just-labels is the hard, valuable problem.
8. Impact & metrics (PRD §12).
9. What's next — trained portion model, SAM 2, live video, voice.
10. Thank you / Q&A.

## 11. Command + Prompt Cheat Sheet
```bash
bash setup.sh && agentcore invoke --prompt "..."   # baseline scaffold
agentcore dev                                       # local test loop
agentcore deploy                                    # deploy to AgentCore
```
Kiro hook prompts (reuse verbatim, they're phase-agnostic):
- "After a task from the spec is implemented, run the test suite automatically. If tests fail, don't mark the task complete — report what failed."
- "Watch pyproject.toml and run `uv sync` whenever it changes."

## 12. Master Checklist
- [ ] Scope trimmed to §9's MVP
- [ ] Roles assigned per §2
- [ ] Baseline agent scaffolded and verified
- [ ] Steering file, skills, both hooks committed
- [ ] Light spec → tasks.md generated, copied into role table
- [ ] Branches created, everyone pulled setup
- [ ] Vision pipeline: detection + classification + depth-heuristic portion working end-to-end on one test photo
- [ ] RAG safety check returns OK/conflict with source reference
- [ ] Merge order agreed (Data → Backend → Frontend → Deploy)
- [ ] `.kiro/` NOT gitignored
- [ ] Demo rehearsed live once
