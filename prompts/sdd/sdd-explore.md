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
- Read relevant codebase areas
- Search for similar patterns (`code_search`, `mem_search`)
- Compare approaches (trade-offs, pros/cons)
- Check prior decisions in tonymem (`mem_search`)

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