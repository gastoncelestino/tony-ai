---
name: sdd-tasks
description: "Break down specs and design into implementation tasks. Trigger: orchestrator launches task planning."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Delegate to the dedicated `sdd-tasks` sub-agent.

## Executor Override

If you ARE the `sdd-tasks` sub-agent, continue. Do NOT delegate.

## Purpose

Break down specs and design into granular, implementable tasks with clear acceptance criteria.

## What You Receive

- Change name
- Spec (`sdd/{change-name}/spec`) and Design (`sdd/{change-name}/design`)
- Structured status with artifact paths

## Execution Steps

### 1. Load Skills & Context
Follow Section A from `skills/_shared/sdd-phase-common.md`.
Read spec, design, and structured status.

### 2. Generate Tasks
Break down into granular tasks with:

| Field | Description |
|---|---|
| **ID** | Hierarchical (1.1, 1.2, 2.1...) |
| **Title** | One-line description |
| **Description** | What to implement, acceptance criteria |
| **Phase** | Logical grouping (Foundation, Core, Integration, Polish) |
| **Dependencies** | Task IDs that must complete first |
| **Files** | Expected new/modified files |
| **Tests** | Required test scenarios |

**Task Granularity Rule**: Each task = 1 logical commit. If a task needs >2 files or >200 lines, split it.

### 3. Review Workload Guard
Forecast total changed lines and risk:
- If >400 lines OR high risk → forecast `Chained PRs recommended: Yes`
- Include `400-line budget risk: High/Medium/Low`
- Set `Decision needed before apply: Yes` if forecast exceeds budget

### 4. Delivery Strategy Forecast
If workload exceeds budget, forecast:
- `auto-chain` / `ask-on-risk` / `single-pr` / `exception-ok`
- Suggest `Chain strategy`: `stacked-to-main` or `feature-branch-chain`

### 5. Persist Tasks
Follow Section C from `sdd-phase-common.md`:
- artifact: `tasks`
- topic_key: `sdd/{change-name}/tasks`
- type: `architecture`

### 6. Return Summary
Return Section D envelope with tasks path, task count, workload forecast, and next_recommended: `sdd-apply`.

## Rules
- Each task = 1 logical commit / PR
- Tasks MUST have testable acceptance criteria
- Dependencies MUST form a DAG (no cycles)
- Flag spec/design gaps as task-level risks