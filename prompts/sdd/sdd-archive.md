---
name: sdd-archive
description: "Close change and persist final state. Trigger: orchestrator launches archive after verify passes."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Delegate to the dedicated `sdd-archive` sub-agent.

## Executor Override

If you ARE the `sdd-archive` sub-agent, continue. Do NOT delegate.

## Purpose

Close the change and persist final state. Reconcile artifacts, produce final report.

## What You Receive

- Change name
- All artifacts (proposal, spec, design, tasks, apply-progress, verify-report)
- Structured status with artifact paths

## Execution Steps

### 1. Load Skills & Context
Follow Section A from `skills/_shared/sdd-phase-common.md`.
Read all artifacts and structured status.

### 2. Verify Archive Readiness
- `applyState: all_done` (all tasks complete)
- `verify-report` verdict: `PASS` or `PASS WITH WARNINGS`
- All tasks marked `[x]` in tasks artifact
- No `blockedReasons` in status

If any check fails → return `blocked` with missing items.

### 3. Reconcile Artifacts
- Ensure tasks artifact shows all tasks `[x]`
- Ensure `apply-progress` reflects all completed tasks
- Ensure `verify-report` verdict matches task completion

### 4. Produce Archive Report
Create `archive-report` with:

| Section | Content |
|---|---|
| **Change Summary** | Name, mode, dates, duration |
| **Deliverables** | Files changed, artifacts produced |
| **Verification** | Verdict, test summary, coverage |
| **Deviations** | Design/spec deviations with rationale |
| **Lessons** | What worked, what didn't, reusable patterns |
| **Follow-ups** | Known issues, tech debt, future work |

### 5. Persist Archive
Follow Section C from `sdd-phase-common.md`:
- artifact: `archive-report`
- topic_key: `sdd/{change-name}/archive-report`
- type: `architecture`

### 6. Return Summary
Return Section D envelope with archive path, final verdict, and next_recommended: `none` (change complete).

## Strict-vs-OpenSpec Archive Policy

OpenSpec permits archiving with incomplete artifacts after user confirmation. This project is stricter by default:

- Incomplete implementation tasks block archive unless proven complete
- CRITICAL issues in `verify-report` always block archive
- Missing proposal/spec/design reported; archive continues only with explicit user choice
- Archive records what was missing

## Rules
- Do NOT archive with CRITICAL verify issues
- Do NOT archive with unchecked tasks (unless exceptional reconciliation with proof)
- Archive report is the final source of truth for the change