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

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Delegate to the dedicated `sdd-explore` sub-agent.

## Executor Override

If you ARE the `sdd-explore` sub-agent, continue. Do NOT delegate.

## Purpose

Investigate an idea, read codebase, compare approaches. No files created — pure investigation.

## What You Receive

- Topic/question to explore
- Optional: change name if part of existing SDD change

## Execution Steps

### 1. Load Skills & Context
Follow Section A from `skills/_shared/sdd-phase-common.md` (minimal — no phase skills needed).

### 2. Investigate
- **Treat the repository codebase as the primary source of truth for exploration.** Start by locating the relevant implementation, configuration, tests, and documentation in the active workspace.
- Use the available codebase search/read tools (`code_search`, direct file reads, or equivalent repository inspection) to identify concrete code paths and cite `file:line` references.
- Use `mem_search` only as a complementary source for prior decisions, historical context, or similar patterns already recorded in TonyMem.
- **Never stop exploration because `mem_search` returns no results.** If memory has no matching observations, continue with codebase search and direct file inspection.
- Do not treat an empty memory result as evidence that the requested system or concept does not exist.
- Compare approaches (trade-offs, pros/cons) only after the relevant codebase path has been established.

### 3. Synthesize Findings
Produce exploration report with:

| Section | Content |
|---|---|
| **Question** | What was investigated |
| **Findings** | Key discoveries, code pointers |
| **Options** | Approaches compared with trade-offs |
| **Recommendation** | Suggested approach with rationale |
| **Risks** | Known unknowns, technical debt |

### 4. Persist Exploration
Follow Section C from `sdd-phase-common.md`:
- artifact: `explore`
- topic_key: `sdd/{change-name}/explore` (or standalone if no change)
- type: `discovery`

### 5. Return Summary
Return Section D envelope with exploration path, key findings, and next_recommended: `sdd-propose` or `none`.

## Rules
- No implementation — pure investigation
- Cite code pointers (file:line) for all claims
- Flag assumptions explicitly
- No files created in repo (only tonymem artifacts)
