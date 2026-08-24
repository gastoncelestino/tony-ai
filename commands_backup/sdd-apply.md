---
description: Implement SDD tasks — writes code following specs and design
agent: tony-orchestrator
subtask: true
---

You are the `tony-orchestrator`, not an SDD executor. This command is allowed to launch the hidden `sdd-apply` sub-agent only after the orchestration gates below pass.

CONTEXT:

- Working directory: before doing anything else, run `git rev-parse --show-toplevel 2>/dev/null || pwd` with your bash tool and use the returned path as the authoritative workspace. In OpenCode Desktop (Electron) the parse-time interpolation resolves to the app data directory, not the project.
- Current project: the `basename` of the detected workspace above.

HARD GATES:

1. SDD Session Preflight must already be complete for this session. It must include execution mode, artifact store, chained PR strategy, and review budget. If missing, ask the exact orchestrator preflight prompt and STOP. Do not run apply in the same turn.
2. `sdd-init` must already exist or be run after preflight, per the orchestrator init guard.
3. Resolve the active change using the status contract. If `$ARGUMENTS` is missing or ambiguous, ask the user to choose and STOP. Do not guess.
4. Produce structured status before acting and use it to confirm the active change has spec, design, and tasks artifacts in the selected artifact store.
5. Review workload guard must have passed. If task forecast exceeds the session review budget or needs a chained-PR decision, ASK and STOP unless the preflight strategy already resolves it.
6. actionContext must allow implementation edits. If status reports `workspace-planning` with no allowed edit roots, STOP before launching apply.

DEPENDENCY CHECK:

- If spec, design, or tasks are missing, do NOT implement.
- Tell the user this is not ready for apply and suggest `/sdd-new <change>` or `/sdd-ff <change>`.

TASK EXECUTION BOUNDARY:

- Select exactly ONE pending task whose dependencies are already completed and execute only that task in this delegation.
- Treat the selected task description and declared files as the execution boundary. Do not implement, refactor, test, or document unrelated tasks in the same delegation.
- Build retrieval queries from the selected task description plus its declared files. Prefer task-scoped Code Index and Context7 results; do not load broad project context when task-scoped evidence is sufficient.
- After the selected task reaches its required evidence/completion state, stop. The next task is a new delegation and gets its own task-scoped context.

TASK:
If all gates pass, launch the hidden `sdd-apply` sub-agent with:

- The selected pending task only, including its description, dependencies, and declared files.
- The resolved artifact store from session preflight; do not hardcode tonymem.
- The structured status needed to validate that task: schemaName, planningHome/changeRoot, artifactPaths/contextFiles, selected task progress, dependency states, applyState, actionContext.
- References to the relevant spec/design sections and apply-progress artifacts needed by the selected task, not the entire change context by default.
- The resolved delivery/chained PR strategy and review budget.
- Strict TDD instructions if `sdd-init` detected strict TDD.

Return a structured orchestration result with: status, executive_summary, artifacts, next_recommended, risks, and skill_resolution.

POST-APPLY REVIEW ROUTING:
After apply returns, rerun native status. If `nextRecommended: review`, the parent orchestrator runs the review workflow via OpenCode's native review agents (`review-readability`, `review-reliability`, `review-resilience`, `review-risk`, `review-refuter`) — no external binary required. The review agents derive repository scope, lineage, tier, lenses, and correction budget from live Git. The apply executor never launches review.

### Authority-First Terminal Procedure (Native)

Use only the compact facade via OpenCode native agents; it appends and reads back native authority before materializing existing compatibility artifacts.

| Order | Operation | Required result | Terminal mirrors |
|---|---|---|---|
| 01 | `review-readability` / `review-reliability` / `review-resilience` / `review-risk` (per risk) | target, tier, lenses, and budget bound | blocked |
| 02 | `review-refuter` (inferential batch) | results, evidence, native transitions, and receipt bound | blocked |
| 03 | Validate receipt via `mem_review` / `mem_search` against `AGENTS.md` | authority, receipt, and live Git checked | blocked |
| 04 | `reconcile-terminal-mirrors` | existing mirrors reconciled | allowed |

After ambiguous output, rerun the same facade operation; native discovery resumes committed authority without another budget. Malformed or ambiguous lineage remains invalid.

Reuse a valid receipt; later commit/push/PR/release events only validate it.
