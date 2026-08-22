---
name: sdd-archive
description: "Close a verified SDD change and produce the final archive report."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "4.0"
  delegate_only: true
---

# SDD Archive

## Objective
Close the change after verification and produce the final archive report.

## Inputs
- Change name
- Completed task/apply state
- Verification report
- Available proposal, specification, design, and task artifact references

## Work
Reconcile the final state and report:
- change summary
- delivered behavior
- verification evidence
- deviations
- lessons learned
- follow-ups

Archive only when the approved work is complete and verification permits closure.

The Tony Kernel owns phase selection, execution permissions, scope, transitions, blocking conditions, and completion validation. This contract defines the meaning and expected output of the Archive phase; it does not define runtime tool policy.
