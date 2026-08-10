---
name: sdd-propose
description: "Create change proposal from exploration. Trigger: orchestrator launches proposal phase."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Delegate to the dedicated `sdd-propose` sub-agent.

## Executor Override

If you ARE the `sdd-propose` sub-agent, continue. Do NOT delegate.

## Purpose

Create a change proposal with business context, requirements, and scope boundaries.

## What You Receive

- Exploration report (`sdd/{change-name}/explore`) if exists
- Optional: raw topic from user

## Execution Steps

### 1. Load Skills & Context
Follow Section A from `skills/_shared/sdd-phase-common.md`.
Read exploration if exists.

### 2. Create Proposal
Produce proposal covering:

| Section | Content |
|---|---|
| **Business Problem** | What problem are we solving? Who is affected? |
| **Target Users** | Who uses this, in what situations |
| **Current State Gap** | What exists now, what's missing |
| **Proposed Solution** | High-level approach |
| **Requirements** | Functional & non-functional (from exploration) |
| **Scope Boundaries** | What's in / out of scope |
| **Non-Goals** | Explicitly excluded |
| **Assumptions** | What we assume true |
| **Risks** | Technical, product, timeline |
| **First Slice** | Smallest valuable increment |

### 3. Proposal Questions (Interactive Mode)
If interactive, ask 3-5 clarifying questions:
- Business rules, edge cases, constraints, trade-offs
- Present correct/second-round/continue via `question` tool

### 3. Persist Proposal
Follow Section C from `sdd-phase-common.md`:
- artifact: `proposal`
- topic_key: `sdd/{change-name}/proposal`
- type: `decision`

### 4. Return Summary
Return Section D envelope with proposal path and next_recommended: `sdd-spec`.

## Rules
- Proposal = business context + requirements, NOT technical design
- Scope boundaries MUST be explicit (in/out)
- Non-goals are as important as goals
- First slice MUST be independently valuable