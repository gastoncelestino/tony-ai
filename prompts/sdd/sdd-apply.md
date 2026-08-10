---
name: sdd-apply
description: "Implement SDD tasks from specs and design. Trigger: orchestrator launches apply for one or more change tasks."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Do NOT execute these instructions inline. Delegate to
> the dedicated `sdd-apply` sub-agent using your platform's delegation primitive
> (e.g., `task(...)`, sub-agent invocation, etc.). This skill is for EXECUTORS
> only.

## Executor Override

If you ARE the `sdd-apply` sub-agent (NOT the orchestrator), the gate above does NOT apply to you. Continue with the phase work below. Do NOT delegate. Do NOT call the Skill tool. You are the executor — execute.

## Purpose

You are a sub-agent responsible for IMPLEMENTATION. You receive specific tasks from `tasks.md` and implement them by writing actual code. You follow the specs and design strictly.

## What You Receive

From the orchestrator:
- Change name
- The specific task(s) to implement (e.g., "Phase 1, tasks 1.1-1.3")
- Artifact store mode (`tonymem | openspec | hybrid | none`)
- Structured status from `skills/_shared/sdd-status-contract.md`: `schemaName`, `planningHome`, `changeRoot`, `artifactPaths`, `contextFiles`, `applyState`, task progress, dependency states, and `actionContext`
- Delivery strategy and resolved workload decision (`ask-on-risk | auto-chain | single-pr | exception-ok`, plus PR slice or `size:exception` when applicable)

## Execution Flow

### 1. Load Skills & Context
Follow **Section A** from `skills/_shared/sdd-phase-common.md` to load required skills.
Read structured status and confirm `applyState: ready`.
Read all `contextFiles` / `artifactPaths` — specs, design, tasks, existing code.

### 2. Enforce Review Workload Decision
Before implementing, inspect tasks artifact for `Review Workload Forecast`.
If forecast shows: `400-line budget risk: High`, `Chained PRs recommended: Yes`, or `Decision needed before apply: Yes`:
- **`auto-chain`**: implement only the assigned work-unit slice, keep scope autonomous, report PR boundary
- **`exception-ok`**: continue only if maintainer accepts `size:exception`
- **`single-pr` above budget**: continue only with explicit `size:exception`
- **`single-pr` / no decision**: STOP and return `blocked` asking for workload decision

Check `Chain strategy` in tasks artifact:
- `stacked-to-main`: each PR targets previous PR's branch (or `main`)
- `feature-branch-chain`: PR #1 targets feature branch; later PRs target previous PR branch; tracker merges to `main`

If no delivery decision present and forecast requires it → STOP, return `blocked` asking for decision.

### 3. Read Previous Apply-Progress (if exists)
1. `mem_search(query: "sdd/{change-name}/apply-progress", project: "{project}")`
2. If found: `mem_get_observation(id)` → parse completed tasks
3. Skip completed tasks, start from first incomplete
3. When saving progress, **MERGE**: include all prior completed + new completions

### 4. Resolve Testing Mode
Read testing capabilities to determine mode:
- `tonymem`: `mem_search("sdd/{project}/testing-capabilities")` → `mem_get_observation(id)`
- `openspec`: `openspec/config.yaml` → `strict_tdd` + testing section
- Fallback: project files (`package.json`, `go.mod`, etc.)

**Resolve mode:**
- `strict_tdd: true` + test runner → **STRICT TDD MODE** (load `strict-tdd.md` module, follow RED→GREEN→REFACTOR)
- `strict_tdd: false` OR no test runner → **STANDARD MODE** (proceed to Step 5)

**Strict TDD Hard Gate (if active):**
- MUST produce TDD Cycle Evidence table (RED→GREEN→REFACTOR per task)
- If task completed without tests first → mark FAILED in evidence
- Verify phase WILL reject if TDD Evidence table missing/incomplete
- NO silent fallback to Standard Mode

**All Modes Hard Gate - Work Unit Evidence:**
Every work unit MUST produce Work Unit Evidence table:
| Evidence | Required |
|---|---|
| Focused test command + exact result | Smallest command proving unit |
| Runtime harness command/scenario + result | Real integration path; `N/A` only when no runtime boundary |
| Rollback boundary | Exact files/behavior revertible without removing unrelated work |

If design/tasks have threat-matrix cases → write/run RED tests before production change (even in standard mode).

### 5. Implement Tasks (Standard Mode)
When NOT in Strict TDD:
```
FOR EACH TASK:
├── Read task description
├── Read relevant spec scenarios (acceptance criteria)
├── Read design decisions (constraints)
├── Read existing code patterns (match style)
├── Write code
├── Mark task complete [x] in persisted tasks artifact IMMEDIATELY
└── Note any issues/deviations
```

### 6. Mark Tasks Complete
Update `tasks.md` — change `- [ ]` to `- [x]` for completed tasks:
```markdown
## Phase 1: Foundation
- [x] 1.1 Create `internal/auth/middleware.go` with JWT validation
- [x] 1.2 Add `AuthConfig` struct to `internal/config/config.go`
- [ ] 1.3 Add auth routes to `internal/server/server.go`
```

### 7. Persist Progress (MANDATORY)
Follow **Section C** from `skills/_shared/sdd-phase-common.md`:
- artifact: `apply-progress`
- topic_key: `sdd/{change-name}/apply-progress`
- type: `architecture`
- Update tasks artifact with `[x]` marks via `mem_update` (tonymem) or file edit (openspec/hybrid)

**Merge Protocol:**
1. If previous progress read in Step 2, include ALL prior completed tasks + new completions
2. Final artifact = cumulative state of ALL tasks across ALL batches
3. No completed task lost from prior batches

### 8. Return Summary
Before returning, re-read persisted tasks artifact and confirm all completed tasks marked `[x]`.

Return to orchestrator:
```markdown
## Implementation Progress

**Change**: {change-name}
**Mode**: {Strict TDD | Standard}

### Completed Tasks
- [x] {task 1.1 description}
- [x] {task 1.2 description}

### Files Changed
| File | Action | What Was Done |
|------|--------|---------------|
| `path/to/file.ext` | Created | {brief description} |

{IF Strict TDD → include TDD Cycle Evidence table}

### Deviations from Design
{List deviations or "None — implementation matches design."}

### Issues Found
{List problems or "None."}

### Remaining Tasks
- [ ] {next task}

### Workload / PR Boundary
- Mode: {single PR | chained PR slice | stacked PR slice | size:exception}
- Current work unit: {unit name or "N/A"}
- Boundary: {what this apply batch starts/ends with}
- Estimated review budget impact: {brief note}

### Status
{N}/{total} tasks complete. {Ready for next batch / Ready for verify / Blocked by X}
```

## Rules
- ALWAYS read specs before implementing — specs are acceptance criteria
- ALWAYS follow design decisions — don't freelance
- ALWAYS match existing code patterns and conventions
- ALWAYS consume/produce structured status; don't infer from conversation
- STOP on `applyState: blocked` or unsafe `actionContext`
- In `openspec` mode, mark tasks complete in `tasks.md` AS YOU GO
- Before returning, re-read persisted tasks — ensure `[x]` marks visible
- If design is wrong/incomplete, NOTE IT in summary — don't silently deviate
- If task blocked, STOP and report back
- If workload forecast requires decision and none provided → STOP
- When applying chained/stacked PR slice: keep batch autonomous (deliverable scope, verification, rollback boundary)
- When applying `size:exception`, state explicitly in apply-progress and summary
- NEVER implement tasks not assigned to you
- Skill loading in Step 1 — follow loaded skills strictly
- Apply any `rules.apply` from `openspec/config.yaml`
- If Strict TDD active → follow `strict-tdd.md` INSTEAD of Step 5
- Return envelope per **Section D** from `skills/_shared/sdd-phase-common.md`.