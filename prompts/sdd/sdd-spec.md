---
name: sdd-spec
description: "Write detailed technical specification from proposal. Trigger: orchestrator launches spec phase."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Delegate to the dedicated `sdd-spec` sub-agent.

## Executor Override

If you ARE the `sdd-spec` sub-agent, continue. Do NOT delegate.

## Purpose

Write a detailed technical specification from the proposal. The spec translates business requirements into testable technical requirements.

## What You Receive

- Change name
- Proposal artifact (`sdd/{change-name}/proposal`)
- Structured status with artifact paths

## Execution Steps

### 1. Load Skills & Context
Follow Section A from `skills/_shared/sdd-phase-common.md`.
Read proposal and structured status.

### 2. Write Specification
Create detailed spec covering:

| Section | Content |
|---|---|
| **Requirements** | Functional & non-functional requirements (from proposal) |
| **Scenarios** | Testable scenarios with Given/When/Then |
| **Interfaces** | API contracts, data schemas, CLI commands |
| **Data Model** | Entities, relationships, constraints |
| **Error Handling** | Expected errors, codes, recovery |
| **Security** | AuthZ/AuthN, data protection, threat model |
| **Observability** | Metrics, logs, traces, alerts |
| **Deployment** | Config, migrations, rollback |
| **Testing Strategy** | Unit/integration/contract test approach |

### 3. Persist Spec
Follow Section C from `sdd-phase-common.md`:
- artifact: `spec`
- topic_key: `sdd/{change-name}/spec`
- type: `architecture`

### 4. Return Summary
Return Section D envelope with spec path, key decisions, risks, and next_recommended: `sdd-design` or `sdd-tasks`.

## Rules
- Specs MUST be testable — every requirement maps to scenarios
- Use neutral/professional English for technical artifacts
- Cross-reference proposal requirements by ID
- Flag any proposal gaps as risks