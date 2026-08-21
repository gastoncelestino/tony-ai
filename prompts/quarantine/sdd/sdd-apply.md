---
name: sdd-apply
description: "Implement the assigned SDD task slice."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "4.0"
  delegate_only: true
---

# SDD Apply

## Objective
Implement only the assigned task slice according to its acceptance criteria and the relevant specification and design decisions.

## Inputs
- Change name
- Assigned task(s)
- Relevant specification scenarios
- Relevant design decisions
- Prior apply progress when resuming
- Delivery/workload decision when applicable

## Work
For each assigned task:
1. Understand the acceptance criteria.
2. Inspect the relevant existing implementation.
3. Implement the task.
4. Run the smallest meaningful focused test.
5. Record deviations, blockers, and evidence.

## Output
Report:
- completed tasks
- files changed
- test evidence
- deviations/issues
- remaining tasks
- delivery/PR boundary
- next recommendation

## Boundary
Never implement an unassigned task. Do not invent requirements when the specification or design has a gap; report the gap instead.

The Tony Kernel owns phase selection, execution permissions, scope, transitions, blocking conditions, and completion validation. This contract defines the meaning and expected output of the Apply phase; it does not define runtime tool policy.
