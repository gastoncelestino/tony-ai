---
name: sdd-spec
description: "Write a testable technical specification from a proposal."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

# Purpose
Translate approved business requirements into a testable technical specification.

## Inputs
- Change name
- Proposal artifact `sdd/{change-name}/proposal`
- Structured artifact paths/status only when needed for persistence

## Work
1. Read the proposal; do not retrieve exploration unless a proposal gap explicitly requires it.
2. Define functional and non-functional requirements.
3. Map every requirement to testable Given/When/Then scenarios.
4. Define only interfaces, data model, error handling, security, observability, deployment, and testing details required by the change.
5. Flag proposal gaps instead of inventing requirements.
6. Persist `sdd/{change-name}/spec` using the common artifact contract.

## Constraints
- Specification is technical and testable; implementation design belongs to `sdd-design`.
- Do not load another phase prompt.
- Do not copy proposal/history beyond what is needed to produce the spec.

## Output
Minimal executor envelope; next phase `sdd-design` or `sdd-tasks` when design is unnecessary.
