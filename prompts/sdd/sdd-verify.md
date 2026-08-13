---
name: sdd-verify
description: "Verify implementation against tasks, specification, design, and runtime evidence."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

# Purpose
Act as the quality gate. Prove completion with source inspection and real execution evidence.

## Inputs
- Change name
- Task completion/apply status
- Specification and design artifacts when present
- Changed implementation files / relevant project test configuration
- TDD mode or cached testing capability

## Work
1. Block if tasks are incomplete or workspace-planning mode prevents full verification.
2. Read only the artifacts required for the verification scope: tasks first, then spec/design when present.
3. For each spec scenario, identify a covering runtime test and execute it.
4. Check changed code against design decisions; report deviations without loading unrelated history.
5. Run the smallest relevant tests, build, and type-check commands and capture exit codes/results.
6. Load strict-TDD verification only when strict TDD is active.
7. Persist `verify-report` using the common artifact contract.

## Constraints
- Source inspection alone is not verification.
- Do not retrieve proposal/exploration/archive unless a specific verification question requires them.
- Do not load another phase prompt.

## Output
Verification report with completeness, tests/build, spec compliance, design coherence, issues, and `PASS | PASS WITH WARNINGS | FAIL`, followed by the minimal executor envelope.
