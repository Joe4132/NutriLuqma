# 3-Hour AWS Kiro Hackathon Playbook — 5-Person Team

## 0. The idea in one line
Kiro works best when the whole team shares the **same repo, the same steering file, and the same skills** — because everyone runs their own Kiro session on their own branch, but Kiro reads `.kiro/steering/`, `.kiro/skills/`, and `.kiro/hooks/` straight from the repo. Set those up once, commit them, and all 5 Kiro sessions behave the same way from that point on.

---

## 1. Time Budget (3:00 total)

| Time | Phase | Who |
|---|---|---|
| 0:00–0:15 | Pick ONE small, scoped idea. Assign roles. | Everyone |
| 0:15–0:30 | **Kiro Setup** — write the lightweight spec, add steering, install skills, add the test hook. Commit `.kiro/` to the repo. | Kiro Workflow Lead + everyone reviewing |
| 0:30–2:10 | Parallel build. Each person on their own branch, own Kiro session. | All 5, in parallel |
| 2:10–2:35 | Integration — merge branches, run tests via the hook, resolve conflicts. | Kiro Workflow Lead |
| 2:35–3:00 | Deploy, demo run-through, write the "how we used Kiro" submission notes. | Deploy & Demo Lead |

---

## 2. The 5 Roles

| # | Role | Owns | Branch |
|---|---|---|---|
| 1 | **Frontend/UI** | UI screens, styling, client-side logic | `feature/frontend` |
| 2 | **Backend/API** | Endpoints, business logic, request handling | `feature/backend` |
| 3 | **Data & AWS Services** | DB schema, storage, any AWS integration (Lambda/DynamoDB/S3/etc.) | `feature/data` |
| 4 | **Kiro Workflow Lead** | Spec (`requirements.md`/`design.md`/`tasks.md`), steering, skills, hooks, and final merge/integration | `main` (integrates into this) |
| 5 | **Deploy & Demo Lead** | AWS deployment, final test pass, demo script, hackathon write-up | `feature/deploy` |

If your idea splits into 5 clearly independent features instead of layers (e.g. 5 separate tools/pages), swap to one-person-per-feature instead — same setup below still applies, you'd just each own a vertical slice.

---

## 3. Kiro Setup (do this once, ~15 min, Workflow Lead drives)

### 3a. Steering file — `.kiro/steering/conventions.md`
Keep it short. This is what keeps 5 parallel Kiro sessions from generating incompatible code:
- Stack/language choices (framework, styling approach, AWS services in use)
- Folder structure everyone should follow
- Naming conventions
- "Keep functions small, business logic separate from handlers" — whatever your team's actual rule is

### 3b. Skills — install into `.kiro/skills/` (workspace-scoped, commit to repo so everyone gets them on pull)
In Kiro's **Agent Steering & Skills** panel → **+** → **Import a skill** → paste a GitHub URL pointing to the skill's *subfolder* (not the repo root):

| Skill | Source | Why |
|---|---|---|
| `test-driven-development` | `github.com/addyosmani/agent-skills/tree/main/skills/test-driven-development` | Enforces writing/running tests as part of each task — this is your "Kiro testing" setup |
| `code-review-and-quality` | `github.com/addyosmani/agent-skills/tree/main/skills/code-review-and-quality` | Give this to the Workflow Lead for the integration pass |
| `frontend-design` | `github.com/anthropics/skills/tree/main/skills/frontend-design` | Give this to the Frontend person for UI polish |

(These are all public, MIT-style community skills — same `SKILL.md` format works across Claude Code, Cursor, and Kiro.)

### 3c. Test hook — `.kiro/hooks/`
Instead of hand-writing hook config, open Kiro's **Hooks** panel and describe it in plain language, e.g.:
> "After a task from the spec is implemented, run the test suite automatically. If tests fail, don't mark the task complete — report what failed."

Kiro will configure the hook for you. This is what makes testing *automatic* instead of something people remember to do manually at 2:50.

### 3d. Spec — keep it light
Write `requirements.md` and `design.md` together as a team in plain language (skip full formal EARS notation — it's built for correctness-critical projects, not a 3-hour sprint). Let Kiro generate `tasks.md` from that — this **is** your task list. Copy each person's tasks from it into their role above so nothing gets duplicated or missed.

---

## 4. During the Build (0:30–2:10)
- Everyone pulls `main` after setup (steering + skills + hook come along automatically).
- Work on your own branch. Commit small, commit often — every 15–20 min, not just at the end.
- Because the `test-driven-development` skill is active, Kiro will nudge tests alongside implementation on its own — you don't need to ask for them separately.
- If you're blocked on someone else's piece, stub it and keep moving — don't wait.

## 5. Integration (2:10–2:35)
- Workflow Lead merges branches into `main` in this order: Data → Backend → Frontend → Deploy (lowest-dependency first).
- The test hook fires on merge/task completion — fix failures before moving to the next merge.
- Use the `code-review-and-quality` skill for a fast pass on the merged result.

## 6. Deploy, Demo & Submission (2:35–3:00)
- Deploy & Demo Lead handles AWS deployment and a final smoke test.
- **Do not** add `.kiro/` to `.gitignore` — most Kiro hackathons require the specs/steering/skills/hooks in the repo as proof of how Kiro was used.
- Write 3–4 sentences: what the spec looked like, which skills you used and why, what the test hook caught.
- Run the demo once, live, before presenting.

---

## Quick checklist
- [ ] Idea scoped small
- [ ] Roles assigned
- [ ] Steering file committed
- [ ] Skills imported and committed
- [ ] Test hook configured
- [ ] Lightweight spec + tasks.md generated
- [ ] Branches created, everyone pulled setup
- [ ] Merge order agreed
- [ ] `.kiro/` folder NOT gitignored
- [ ] Demo rehearsed
