## Architecture note

`_shared` contains reusable reference documents, but they are not all common phase context.

Only `sdd-phase-common.md` is the minimal common contract for SDD phase executors.
Other documents are specialized references and must be loaded only by the component or phase that explicitly requires them.

Do not scan or load the entire `_shared` directory.

---
name: _shared
description: "Shared SDD references for installed skills. Not invokable."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "1.0"
---

## Purpose

This directory stores shared reference documents consumed by real SDD skills
(for example: `sdd-phase-common.md`, `persistence-contract.md`).

## Not Invokable

`_shared` is a support package only. Do not invoke it as a skill.
