---
name: sdd-tasks
description: "Break down the specification and design into implementation tasks."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "4.0"
  delegate_only: true
---

# SDD Tasks

## Objective
Break the approved specification and design into granular, implementable, verifiable tasks.

## Inputs
- Change name
- Specification artifact
- Design artifact

## Task contract
Each task must include:

| Field | Requirement |
|---|---|
| ID | Hierarchical (`1.1`, `1.2`, `2.1`, ...) |
| Title | One-line implementation objective |
| Description | Scope and testable acceptance criteria |
| Phase | Logical delivery grouping |
| Dependencies | Task IDs that must complete first |
| Files | Expected new or modified files |
| Tests | Required test scenarios |

Each task is one logical, verifiable objective suitable for one focused execution. Independent objectives must be separate tasks. Dependencies form a DAG. Missing specification/design information is a risk, not an invitation to invent requirements.

## Workload forecast
Forecast total changed lines and implementation risk. Flag a chaining or delivery decision when the forecast exceeds the project's defined budget or risk threshold.

## Output
Produce the complete task set and workload forecast, with dependencies and acceptance criteria sufficient for the Apply phase.

The Tony Kernel owns phase selection, execution permissions, scope, transitions, blocking conditions, and artifact lifecycle. This contract defines the meaning and expected output of the Tasks phase; it does not define runtime tool policy.
