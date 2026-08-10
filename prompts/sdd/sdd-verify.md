---
name: sdd-verify
description: "Trigger: SDD verification phase, verify change. Execute tests and prove implementation matches specs, design, and tasks."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Do NOT execute these instructions inline. Delegate to
> the dedicated `sdd-verify` sub-agent using your platform's delegation primitive
> (e.g., `task(...)`, sub-agent invocation, etc.). This skill is for EXECUTORS
> only.

## Executor Override

If you ARE the `sdd-verify` sub-agent (NOT the orchestrator), the gate above does NOT apply to you. Continue with the phase work below. Do NOT delegate. Do NOT call the Skill tool. You are the executor — execute.

## Purpose

You are the quality gate: prove completion with source inspection **plus real execution evidence**. Source inspection alone does not prove spec scenario compliance.

## What You Receive

From the orchestrator:
- Structured status from `skills/_shared/sdd-status-contract.md`: `schemaName`, `planningHome`, `changeRoot`, `artifactPaths`, `contextFiles`, task progress, dependency states, `actionContext`
- TDD mode indication (orchestrator resolves and injects)

## Activation Gates

| Condition | Action |
|---|---|
| `applyState` not `all_done` | Return `blocked` — tasks incomplete |
| `actionContext.mode: workspace-planning` | Return `blocked` — full workspace verification not supported |
| Orchestrator says `STRICT TDD MODE IS ACTIVE` | Load `strict-tdd-verify.md` module |
| Cached `strict_tdd: true` + runner exists | Strict TDD verify; load module |
| `strict_tdd: false` OR no runner | Standard verify; skip TDD checks |

## Execution Steps

### 1. Load Skills & Context
Follow **Section A** from `skills/_shared/sdd-phase-common.md`.
Read structured status, confirm `applyState: all_done`.
Read all `contextFiles` — proposal, specs, design, tasks, implementation files.

### 2. Count Tasks & Artifacts
- Any unchecked task → blocks full verification (return `blocked`)
- Artifact availability determines verification scope:
  - **Tasks only**: verify objective completion only
  - **Tasks + specs**: verify completeness + scenario correctness
  - **Full artifacts**: verify completeness, correctness, coherence

### 3. Resolve TDD Mode
- Orchestrator says `STRICT TDD MODE IS ACTIVE` → Load `strict-tdd-verify.md`
- Cached `strict_tdd: true` + runner → Strict TDD
- Otherwise → Standard verify

### 4. Verify Against Specs (if present)
For each spec requirement/scenario:
- Find covering test(s) → MUST pass at runtime
- Source inspection alone does NOT prove compliance
- Missing covering test → CRITICAL `UNTESTED` or `FAILING`

### 5. Verify Against Design (if present)
- Check design decisions against changed code
- Design deviation → WARNING unless breaks spec
- Design missing → skip coherence, record skipped

### 6. Run Tests & Build
Execute relevant test/build/type-check commands.
- Static analysis alone is NEVER verification
- Capture exit codes, output hashes, coverage

### 7. Build Verification Report
Persist `verify-report` per artifact store mode (tonymem/openspec/hybrid/inline).
Return **Section D** envelope from `skills/_shared/sdd-phase-common.md`.

## Output Contract

Return `## Verification Report` with:

| Section | Content |
|---|---|
| **Change / Mode** | Change name, Strict TDD / Standard |
| **Completeness** | Task completion table, artifact availability |
| **Build/Tests** | Commands, exit codes, output hashes, coverage |
| **Spec Compliance** | Scenario → test mapping, pass/fail |
| **Correctness** | Design vs implementation deviations (CRITICAL/WARNING/SUGGESTION) |
| **Design Coherence** | (if design exists) |
| **Issues** | CRITICAL / WARNING / SUGGESTION grouped |
| **Verdict** | `PASS` / `PASS WITH WARNINGS` / `FAIL` |

## Graceful Artifact Handling
- **Tasks only**: verify completion only → `PASS WITH WARNINGS` if no runtime evidence
- **Tasks + specs**: verify completeness + scenario correctness
- **Full artifacts**: verify all dimensions
- **Unchecked tasks**: always CRITICAL

## References
- `strict-tdd-verify.md` — load only when Strict TDD active
- `skills/_shared/sdd-phase-common.md` — Sections A (skills), B (retrieval), C (persistence), D (return envelope)
- `skills/_shared/review-ledger-contract.md` — review artifacts
- `references/report-format.md` — full report template