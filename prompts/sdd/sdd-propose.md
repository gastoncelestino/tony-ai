---
name: sdd-propose
description: "Create a scoped change proposal from exploration."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

# Purpose
Turn exploration into a business-facing proposal with explicit scope.

## Inputs
- Change name
- Exploration artifact `sdd/{change-name}/explore`, when available
- Optional raw topic/user input
- Interactive mode, when enabled

## Work
1. Read only the exploration artifact needed for this proposal.
2. In interactive mode ask only the clarifying questions needed to resolve business rules, constraints, edge cases, or trade-offs.
3. Produce:
   - Business problem and target users
   - Current-state gap
   - Proposed solution
   - Functional/non-functional requirements
   - In/out scope and non-goals
   - Assumptions and risks
   - Smallest valuable first slice
4. Persist `sdd/{change-name}/proposal` using the common artifact contract.

## Constraints
- Proposal is not technical design.
- Do not load spec, design, tasks, apply, verify, or archive prompts.
- Do not copy unrelated artifacts into context.

## Output
Minimal executor envelope; next phase `sdd-spec`.
