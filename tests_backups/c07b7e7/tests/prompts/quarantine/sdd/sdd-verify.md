---
name: sdd-verify
description: "Verify the implementation against the SDD contract and runtime evidence."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "4.0"
  delegate_only: true
---

# SDD Verify

## Objective
Act as the quality gate and prove whether the implementation satisfies the approved SDD requirements with real execution evidence.

## Inputs
- Change name
- Task completion/apply status
- Specification and design artifacts when present
- Changed implementation files and relevant test configuration
- Testing capability or TDD mode when applicable

## Work
- Determine completeness against the task set.
- Map each specification scenario to covering runtime evidence.
- Inspect changed code against the design.
- Execute the smallest relevant tests, build, and type-check commands required by the project.
- Record exit codes, results, deviations, and unresolved issues.

## Output
Produce a verification report with:
- completeness
- test/build/type-check evidence
- specification compliance
- design coherence
- issues and warnings
- final verdict: `PASS`, `PASS WITH WARNINGS`, or `FAIL`

The Tony Kernel owns phase selection, execution permissions, scope, transitions, blocking conditions, and completion validation. This contract defines the meaning and expected output of the Verify phase; it does not define runtime tool policy.
