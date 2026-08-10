---
name: sdd-init
description: "Bootstrap SDD context and project configuration. Trigger: first SDD command in a project."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Delegate to the dedicated `sdd-init` sub-agent.

## Executor Override

If you ARE the `sdd-init` sub-agent, continue. Do NOT delegate.

## Purpose

Bootstrap SDD context: detect stack, configure persistence, cache testing capabilities.

## What You Receive

- Project root (from orchestrator context)
- Optional: user preferences if interactive

## Execution Steps

### 1. Detect Project Stack
Analyze project to detect:
- Language(s): Python, TypeScript, Go, Rust, etc.
- Framework(s): FastAPI, Next.js, Gin, Actix, etc.
- Test runner: pytest, jest, go test, cargo test, etc.
- Build/type-check commands
- Lint/formatter config

### 2. Detect Testing Capabilities
Determine:
- `strict_tdd` support (test runner exists, can run RED→GREEN cycles)
- Available test commands
- Coverage tool availability

### 3. Cache Capabilities
Persist `sdd-init/{project}` in tonymem:
```json
{
  "project": "{project}",
  "stack": ["python", "fastapi", "postgresql"],
  "test_runner": "pytest",
  "test_command": "pytest -xvs",
  "coverage_command": "pytest --cov",
  "build_command": "mypy . && pytest",
  "strict_tdd": true,
  "strict_tdd_module": "skills/sdd-apply/strict-tdd.md",
  "verify_module": "skills/sdd-verify/strict-tdd-verify.md"
}
```

### 3. Configure Artifact Store
Prompt user (Interactive) or detect (Auto):
- `tonymem` (default) — fast, no files
- `openspec` — file-based, shareable
- `hybrid` — both

Persist `sdd-init/{project}` with `artifact_store.mode`.

### 4. Configure Preflight Defaults
Cache user preferences:
- Execution mode: `interactive` (default) | `auto`
- Delivery strategy: `ask-on-risk` (default) | `auto-chain` | `single-pr` | `exception-ok`
- Review budget: `400` lines (default) | custom

### 5. Persist Init Context
Follow Section C from `sdd-phase-common.md`:
- artifact: `project-context`
- topic_key: `sdd-init/{project}`
- type: `config`

### 4. Return Summary
Return Section D envelope with detected stack, capabilities, and next_recommended: `sdd-new` or `sdd-onboard`.

## Rules
- Run ONLY once per project (check `mem_search` first)
- Cache is per-project; multi-project supported
- If project already initialized, return cached config