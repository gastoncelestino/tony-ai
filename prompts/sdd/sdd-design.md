---
name: sdd-design
description: "Create an implementable technical design from proposal and spec."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

# Purpose
Turn the approved specification into an implementable technical design.

## Inputs
- Change name
- Proposal `sdd/{change-name}/proposal` only for scope traceability
- Specification `sdd/{change-name}/spec`

## Work
1. Read spec and proposal only as needed to resolve scope.
2. Define architecture, boundaries, data structures, algorithms, interfaces, error handling, security, performance, and testing boundaries required by the spec.
3. Trace each major decision to a specification requirement.
4. Flag unresolved spec gaps rather than silently assuming.
5. Persist `sdd/{change-name}/design` using the common artifact contract.

## Constraints
- Design must be implementable; avoid vague TBDs.
- Do not retrieve tasks, apply-progress, verify-report, or archive artifacts.
- Do not load another phase prompt.

## Output
Minimal executor envelope; next phase `sdd-tasks`.
