---
name: sdd-design
description: "Create technical design from proposal and spec. Trigger: orchestrator launches design phase."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Delegate to the dedicated `sdd-design` sub-agent.

## Executor Override

If you ARE the `sdd-design` sub-agent, continue. Do NOT delegate.

## Purpose

Create technical design from proposal and spec. Define architecture, data structures, interfaces, and algorithms.

## What You Receive

- Change name
- Proposal (`sdd/{change-name}/proposal`) and Spec (`sdd/{change-name}/spec`)
- Structured status with artifact paths

## Execution Steps

### 1. Load Skills & Context
Follow Section A from `skills/_shared/sdd-phase-common.md`.
Read proposal, spec, and structured status.

### 2. Create Technical Design
Produce design document covering:

| Section | Content |
|---|---|
| **Architecture** | Components, boundaries, communication patterns |
| **Data Structures** | Schema definitions, types, invariants |
| **Algorithms** | Key algorithms, complexity, trade-offs |
| **Interfaces** | Internal/external APIs, contracts |
| **Error Handling** | Strategies, codes, retry/timeout policies |
| **Security** | Trust boundaries, data flow, encryption |
| **Performance** | Targets, bottlenecks, scaling strategy |
| **Testing Strategy** | Unit/integration boundaries, mock strategy |

### 3. Persist Design
Follow Section C from `sdd-phase-common.md`:
- artifact: `design`
- topic_key: `sdd/{change-name}/design`
- type: `architecture`

### 4. Return Summary
Return Section D envelope with design path, key decisions, risks, and next_recommended: `sdd-tasks`.

## Rules
- Design MUST be implementable — no vague "TBD" sections
- Every design decision traces to a spec requirement
- Flag spec gaps as risks, don't silently assume
- Use neutral/professional English for technical artifacts