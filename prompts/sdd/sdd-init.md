---
name: sdd-init
description: "Bootstrap SDD project context and testing capabilities."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "4.0"
  delegate_only: true
---

# SDD Init

## Objective
Bootstrap the project context required by the SDD workflow.

## Inputs
- Active project workspace
- Optional user preferences

## Output
Produce the project initialization artifact containing the detected stack, testing/build capabilities, artifact-store mode, and preflight defaults required by later phases.

## Work
- Detect the project languages and frameworks.
- Detect the test runner and test command.
- Detect the build/type-check command and coverage command when available.
- Record the `strict_tdd` capability when it can be established from project configuration.
- Record the configured artifact-store mode and preflight defaults.

## Boundary
Inspect only the project configuration needed to establish SDD project context. Do not implement a requested change or perform phase work belonging to Explore or later phases.

The Tony Kernel owns phase selection, execution permissions, scope, transitions, and artifact lifecycle. This contract defines the meaning and expected output of the Init phase; it does not define runtime tool policy.
