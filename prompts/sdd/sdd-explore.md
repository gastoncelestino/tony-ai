---
name: sdd-explore
description: "Investigate codebase and think through ideas. Trigger: orchestrator launches exploration."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

# Purpose

Investigate an idea, inspect the relevant codebase, compare approaches, and produce an evidence-based exploration.

## Inputs

- Topic/question to explore
- Optional change name
- Artifact-store mode when persistence is required

## Context boundary

Use only:
- the question/topic
- relevant code and configuration
- prior exploration/discovery only when explicitly relevant
- relevant project memory when available and required

Do not load another phase prompt.
Do not load the full project history.
Do not load unrelated artifacts.

## Work

1. Inspect only the codebase areas relevant to the question.
2. Search for existing patterns, implementations, tests, and constraints.
3. When prior project decisions are relevant, retrieve only the matching memory/artifact entries.
4. Compare viable approaches with trade-offs.
5. Produce an exploration report containing:
   - Question
   - Findings
   - Options
   - Recommendation
   - Risks
6. Persist the `explore` artifact using the common artifact contract when the active artifact-store mode requires persistence.

## Output

Return the minimal executor envelope:

- status
- summary
- artifact path/key
- next: `sdd-propose` or `none`
- risks

## Constraints

- No implementation.
- Cite relevant code pointers for material claims.
- Flag assumptions explicitly.
- Do not copy unrelated artifacts into the launch context.