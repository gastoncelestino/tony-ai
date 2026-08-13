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

# Purpose

Break the specification and design into small, implementable task slices.

## Inputs

- Change name
- `sdd/{change-name}/spec`
- `sdd/{change-name}/design`
- Artifact-store mode
- Minimal structured status needed for workload and delivery decisions

## Context boundary

Read only the specification, design, and status required to plan the tasks.

Do not load:
- proposal
- exploration
- implementation files
- verify reports
- archive data
- unrelated phase prompts
- complete runtime status contracts

## Work

1. Read the specification and design.
2. Create tasks with:
   - ID
   - title
   - implementation description
   - testable acceptance criteria
   - logical phase
   - dependencies
   - expected files
   - required tests
3. Keep each task to one logical commit.
4. Split a task expected to touch more than 2 files or 200 lines.
5. Forecast changed lines and implementation risk.
6. If the forecast exceeds 400 lines or presents high risk, mark the workload as requiring a delivery decision.
7. When a delivery decision is required, forecast:
   - `auto-chain`
   - `ask-on-risk`
   - `single-pr`
   - `exception-ok`
8. Suggest a chain strategy when chaining is required.
9. Persist the `tasks` artifact using the common artifact contract.

## Output

Return the minimal executor envelope with:

- task count
- workload forecast
- delivery recommendation
- artifact path/key
- risks
- next: `sdd-apply`

## Constraints

- Acceptance criteria must be testable.
- Dependencies must form a DAG.
- Flag specification/design gaps instead of inventing requirements.
- Never include unrelated phase instructions or artifacts in the task artifact.