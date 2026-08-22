---
name: sdd-propose
description: "Turn exploration into a scoped business proposal."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "4.0"
  delegate_only: true
---

# SDD Propose

## Objective
Turn the approved exploration findings into a business-facing proposal with explicit scope.

## Inputs
- Change name
- Exploration artifact, when available
- User/topic context when supplied

## Output
Produce:
- Business problem and target users
- Current-state gap
- Proposed solution
- Functional and non-functional requirements
- In-scope and out-of-scope behavior
- Non-goals
- Assumptions and risks
- Smallest valuable first slice

## Boundary
The proposal defines business scope and intended behavior. It is not a technical specification or implementation design.

The Tony Kernel owns phase selection, execution permissions, scope, transitions, and artifact lifecycle. This contract defines the meaning and expected output of the Propose phase; it does not define runtime tool policy.
