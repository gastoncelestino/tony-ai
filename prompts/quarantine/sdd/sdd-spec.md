---
name: sdd-spec
description: "Translate approved requirements into a testable technical specification."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "4.0"
  delegate_only: true
---

# SDD Spec

## Objective
Translate approved business requirements into a testable technical specification.

## Inputs
- Change name
- Proposal artifact

## Output
Define:
- Functional and non-functional requirements
- Given/When/Then scenarios covering each requirement
- Interfaces and data model required by the change
- Error handling and security requirements
- Observability, deployment, and testing requirements where applicable
- Explicit gaps, assumptions, and unresolved requirements

## Boundary
The specification defines testable technical requirements. Detailed implementation design belongs to the Design phase.

The Tony Kernel owns phase selection, execution permissions, scope, transitions, and artifact lifecycle. This contract defines the meaning and expected output of the Spec phase; it does not define runtime tool policy.
