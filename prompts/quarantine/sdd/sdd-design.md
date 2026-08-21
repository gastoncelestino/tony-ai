---
name: sdd-design
description: "Turn the specification into an implementable technical design."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "4.0"
  delegate_only: true
---

# SDD Design

## Objective
Turn the approved specification into an implementable technical design.

## Inputs
- Change name
- Specification artifact
- Proposal context only when needed for scope traceability

## Output
Define the implementation approach, including as applicable:
- Architecture and boundaries
- Data structures and algorithms
- Interfaces
- Error handling and security
- Performance considerations
- Testing boundaries
- Traceability from major decisions to specification requirements
- Unresolved specification gaps and assumptions

## Boundary
The design must be implementable and consistent with the specification. It does not create implementation tasks or modify the project.

The Tony Kernel owns phase selection, execution permissions, scope, transitions, and artifact lifecycle. This contract defines the meaning and expected output of the Design phase; it does not define runtime tool policy.
