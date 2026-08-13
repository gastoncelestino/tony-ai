---
name: sdd-onboard
description: "Guide a user through SDD onboarding and establish the minimum project/change context."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

# Purpose
Guide onboarding for a project or change and establish only the context required for the next SDD action.

## Inputs
- User onboarding request
- Repository/project location
- Existing SDD state when available
- Artifact-store mode
- Structured status when supplied

## Context boundary
Inspect only what is required to understand the project's current SDD state.

Prefer:
- README/project documentation relevant to development
- existing SDD configuration
- active change metadata
- existing artifact references
- targeted repository structure

Do not load:
- every project file
- all SDD artifacts
- all phase prompts
- generated prompt bundles
- `phase-manifest.json`
- unrelated skills
- implementation source unless needed to answer the onboarding question

## Work
1. Determine whether the project already has SDD state.
2. Identify the active artifact-store mode and relevant project configuration.
3. Identify active changes and their current state when applicable.
4. Explain the minimum information needed for the next action.
5. If onboarding requires creating or updating project/change state, persist only that state using the active artifact-store contract.
6. Recommend the next appropriate action without executing another SDD phase.

## Output
Return:
- status
- current project/change state
- relevant artifact paths/keys
- onboarding findings
- missing information, if any
- next recommended action

## Constraints
- Do not execute another SDD phase.
- Do not load all phase prompts to explain the workflow.
- Do not reconstruct generated prompts or manifests.
- Do not copy unrelated project content into onboarding state.
- Prefer references and summaries over copied artifact contents.