---
name: sdd-init
description: "Bootstrap SDD project context and testing capabilities."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

# Purpose
Initialize SDD state once per project.

## Inputs
- Project root
- Optional user preferences

## Work
1. If `sdd-init/{project}` already exists, return the cached configuration.
2. Inspect only project configuration needed to identify:
   - languages/frameworks
   - test runner and test command
   - build/type-check command
   - coverage command when available
   - `strict_tdd` capability
3. Select artifact store: `tonymem` (default), `openspec`, `hybrid`, or `none`.
4. Set preflight defaults: execution mode, delivery strategy, and review budget (400 lines default).
5. Persist the resulting project context as `sdd-init/{project}` using the common artifact contract.

## Output
Return the minimal executor envelope with detected stack/capabilities and next phase: `sdd-onboard` or `sdd-explore`.

## Constraints
- Run only once per project unless no cached state exists.
- Do not inspect unrelated source code.
- Do not load another phase prompt.
