---
name: sdd-apply
description: "Implement assigned SDD tasks. Trigger: orchestrator launches apply for one or more task slices."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

# Purpose
Implement only the assigned task slice, following its acceptance criteria, relevant specification, and design constraints.

## Inputs
- Change name
- Assigned task(s) from `tasks`
- Artifact-store mode
- `applyState`, dependency state, and `actionContext`
- Delivery/workload decision when the task forecast requires one
- Only the artifact references and code paths relevant to the assigned tasks

## Context boundary
Do not load all `contextFiles` or all phase artifacts. Retrieve only:
- the assigned task(s)
- the relevant spec scenarios
- the relevant design decisions
- required existing source files
- prior `apply-progress` for this change when resuming
- testing capability/configuration when needed

Do not load proposal, exploration, verify, archive, or unrelated tasks unless the assigned task explicitly depends on them.

## Execution
1. Confirm `applyState: ready` and that assigned task dependencies are satisfied. Stop as `blocked` otherwise.
2. Check the task workload decision. If the forecast requires a decision and none is present, stop as `blocked`.
3. Retrieve prior `apply-progress` only when resuming; merge new completions with the cumulative state.
4. Resolve testing mode from the project's cached testing capability or project configuration.
5. If strict TDD is active, load `strict-tdd.md` and use RED → GREEN → REFACTOR. Otherwise use the standard flow.
6. For each assigned task:
   - read the task acceptance criteria
   - read only relevant spec/design sections
   - inspect relevant existing code
   - implement the task
   - run the smallest meaningful focused test
   - record deviations or blockers
7. Mark completed tasks in the persisted tasks artifact when the active store supports it.
8. Persist cumulative `apply-progress` using the common artifact contract.
9. Re-read the persisted task state before returning.

## Evidence
For every work unit record:
- focused test command and result
- runtime harness/scenario and result, or `N/A` when no runtime boundary exists
- rollback boundary

## Output
Return:
- status
- change/mode
- completed tasks
- files changed
- test evidence
- deviations/issues
- remaining tasks
- workload/PR boundary
- next recommendation (`sdd-apply` for remaining tasks, otherwise `sdd-verify`)

## Constraints
- Never implement unassigned tasks.
- Follow spec acceptance criteria and design decisions; report gaps instead of freelancing.
- Stop on blocked/unsafe action context.
- In chained work, keep the assigned slice autonomous and reviewable.
- Do not copy unrelated artifacts into the launch context or persisted progress.
