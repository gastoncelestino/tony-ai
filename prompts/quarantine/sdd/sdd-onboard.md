---
name: sdd-onboard
description: "Guided end-to-end walkthrough of SDD using the real codebase. Trigger: user wants to learn SDD by doing."
disable-model-invocation: true
user-invocable: true
license: MIT
metadata:
  author: gentleman-programming
  version: "4.0"
  delegate_only: true
---

# SDD Onboard

## Objective
Guide the user through a complete SDD cycle using the real codebase as a teaching exercise.

This is a teaching workflow, not an additional production phase. The Tony Kernel remains authoritative for phase selection, execution permissions, scope, transitions, blocking conditions, and artifact lifecycle.

## What the user receives
- A short explanation of SDD and its phase model.
- A small real change selected from the project's backlog or current needs.
- An explanation of each phase and the artifact it produces.
- An opportunity to review and approve each phase before continuing.
- A final review of the artifacts, decisions, and lessons from the cycle.

## Phase walkthrough
Use the active SDD workflow and its phase contracts:

| Phase | Purpose |
|---|---|
| Init | Establish project context and testing capabilities |
| Explore | Investigate the codebase and relevant implementation options |
| Propose | Define the business scope and intended behavior |
| Spec | Define testable technical requirements |
| Design | Define the implementation architecture and interfaces |
| Tasks | Break the approved design into implementable tasks |
| Apply | Implement the approved tasks |
| Verify | Validate the implementation and gather evidence |
| Archive | Close the change and preserve relevant lessons |

At each phase, explain why it exists, show the resulting artifact, and let the user review or approve before continuing when the workflow requires approval.

## Teaching constraints
- Use the real project as the training ground.
- Prefer a small, well-bounded first change.
- Explain decisions without performing unrelated work.
- Do not treat this teaching contract as a substitute for Kernel enforcement or phase execution policy.

## Boundary
Do not invent a parallel phase state machine. Do not load or execute phase contracts outside the phase currently authorized by Tony Kernel.
