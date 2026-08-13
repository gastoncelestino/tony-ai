---
name: sdd-archive
description: "Close a verified SDD change and persist final state."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

# Purpose
Close the change after verification and create the final archive report.

## Inputs
- Change name
- Task completion/apply status
- `verify-report`
- Artifact paths for proposal/spec/design/tasks/apply-progress when available

## Work
1. Require `applyState: all_done` and verify verdict `PASS` or `PASS WITH WARNINGS`.
2. Confirm all tasks are complete and no blocking reasons remain.
3. Read only the artifact summaries/sections needed to reconcile final state; do not reload full history unnecessarily.
4. Reconcile tasks, apply-progress, and verify-report.
5. Produce `archive-report` covering change summary, deliverables, verification, deviations, lessons, and follow-ups.
6. Persist `sdd/{change-name}/archive-report` using the common artifact contract.

## Constraints
- Critical verification issues or incomplete tasks block archive.
- Missing optional proposal/spec/design is reported and requires the applicable project policy/user decision.
- Do not load another phase prompt.

## Output
Minimal executor envelope with final verdict and next phase `none`.
