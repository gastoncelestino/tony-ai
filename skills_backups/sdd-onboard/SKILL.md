---
name: sdd-onboard
description: "Guide a user through SDD onboarding using the real project and minimum required context."
disable-model-invocation: true
user-invocable: true
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  interactive: true
---

# Purpose

Guide the user through SDD onboarding using the real project. This is an interactive teaching workflow, not a delegated implementation phase.

## Context boundary

Load only the minimum context required to understand:

- project structure
- SDD configuration
- active changes
- current artifact-store mode
- the user's onboarding question

Do not load:

- every project file
- all SDD artifacts
- all phase prompts
- generated prompt bundles
- phase manifests
- unrelated skills
- implementation source unless needed for the onboarding question

Prefer references, summaries, and targeted inspection over copied content.

## Flow

### 1. Understand the project

Inspect only the relevant project documentation and SDD configuration.

Determine:

- whether SDD is already initialized
- active artifact-store mode
- active changes
- current SDD state

### 2. Explain SDD

Explain briefly:

- what SDD is
- what each phase does
- how artifacts move between phases
- how persistence works
- why each phase receives limited context

Do not load the implementation prompts of every phase just to explain the workflow.

### 3. Identify the first useful action

Based on the project state and user's goal, recommend the smallest appropriate next action.

Examples:

- initialize project → `sdd-init`
- understand a problem → `sdd-explore`
- turn exploration into proposal → `sdd-propose`
- continue an existing change → `sdd-continue`

Do not execute another SDD phase automatically.

### 4. Interactive guidance

Ask focused questions only when required.

When showing an artifact or state, prefer:

- artifact reference
- topic key
- path
- concise summary

Do not copy unrelated artifact contents into the conversation.

## Persistence

If onboarding itself must persist project/change state, use the active artifact-store mode and write only the state required for onboarding.

Do not create OpenSpec artifacts unless the active mode is `openspec` or `hybrid`.

## Output

Return:

status: success | partial | blocked
project-state: current relevant state
artifact-store: active mode
findings: concise onboarding findings
missing: missing information, if any
next: recommended SDD action

## Rules

- Remain interactive.
- Do not delegate onboarding to another phase.
- Do not execute another SDD phase automatically.
- Do not load all phase prompts.
- Do not reconstruct generated prompts or manifests.
- Keep context minimal.
- Use the real project rather than toy examples.