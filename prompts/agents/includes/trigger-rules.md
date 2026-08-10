### Sub-Agent Context Protocol

Sub-agents get a fresh context with NO memory. The orchestrator controls context access.

#### Non-SDD Tasks (general delegation)

- Read context: orchestrator searches tonymem (`mem_search`) for relevant prior context and passes it in the sub-agent prompt. Sub-agent does NOT search tonymem itself.
- Write context: sub-agent MUST save significant discoveries, decisions, or bug fixes to tonymem via `mem_save` before returning.
- Always add to the sub-agent prompt: "If you make important discoveries, decisions, or fix bugs, save them to tonymem via mem_save with project: '{project}'."

#### SDD Phases

Each phase has explicit read/write rules:

| Phase         | Reads                                                   | Writes           |
| ------------- | ------------------------------------------------------- | ---------------- |
| `sdd-explore` | nothing                                                 | `explore`        |
| `sdd-propose` | exploration (optional)                                  | `proposal`       |
| `sdd-spec`    | proposal (required)                                     | `spec`           |
| `sdd-design`  | proposal (required)                                     | `design`         |
| `sdd-tasks`   | spec + design (required)                                | `tasks`          |
| `sdd-apply`   | tasks + spec + design + `apply-progress` (if it exists) | `apply-progress` |
| `sdd-verify`  | spec + tasks + `apply-progress`                         | `verify-report`  |
| `sdd-archive` | all artifacts                                           | `archive-report` |

For phases with required dependencies, sub-agents read directly from the backend - orchestrator passes artifact references (topic keys or file paths), NOT the content itself.

#### Strict TDD Forwarding (MANDATORY)

When launching `sdd-apply` or `sdd-verify`, the orchestrator MUST:

1. Search for testing capabilities: `mem_search(query: "sdd-init/{project}", project: "{project}")`
2. If the result contains `strict_tdd: true`, add: "STRICT TDD MODE IS ACTIVE. Test runner: {test_command}. You MUST follow strict-tdd.md. Do NOT fall back to Standard Mode."
3. If the search fails or `strict_tdd` is not found, do NOT add the TDD instruction

#### Apply-Progress Continuity (MANDATORY)

When launching `sdd-apply` for a continuation batch:

1. Search for existing apply-progress: `mem_search(query: "sdd/{change-name}/apply-progress", project: "{project}")`
2. If found, add: "PREVIOUS APPLY-PROGRESS EXISTS at topic_key 'sdd/{change-name}/apply-progress'. You MUST read it first via mem_search + mem_get_observation, merge your new progress with the existing progress, and save the combined result. Do NOT overwrite - MERGE."
3. If not found, no extra instruction is needed

#### tonymem Topic Key Format

| Artifact        | Topic Key                          |
| --------------- | ---------------------------------- |
| Project context | `sdd-init/{project}`               |
| Exploration     | `sdd/{change-name}/explore`        |
| Proposal        | `sdd/{change-name}/proposal`       |
| Spec            | `sdd/{change-name}/spec`           |
| Design          | `sdd/{change-name}/design`         |
| Tasks           | `sdd/{change-name}/tasks`          |
| Apply progress  | `sdd/{change-name}/apply-progress` |
| Verify report   | `sdd/{change-name}/verify-report`  |
| Archive report  | `sdd/{change-name}/archive-report` |

<!-- tony-ai:trigger-rules -->
## Agent Trigger Rules

Deterministic bounded-review lifecycle router; apply it as a decision procedure, not advice. Post-apply starts `review/start(target)` only when no valid receipt exists. Pre-commit, pre-push, and pre-PR validate the same content-bound receipt and never create a new review budget or silently start Judgment Day. Release from protected `main` may bypass receipt validation only when the tag targets the current immutable `origin/main` SHA, required CI for that exact SHA is successful, the remote head is rechecked before tag push, and no fresh risk evidence exists; otherwise fail closed through native receipt validation. Major and post-incident releases require explicit extraordinary review.

Receipt action table: missing → start explicitly after implementation/post-apply; scope-changed → create a new lineage; invalidated → require explicit maintainer action; escalated → stop. New CI, vulnerability, base, policy, provenance, or release evidence may invalidate/escalate without reopening unchanged code review.

Inside explicit `review/start(target)` only, select initial lenses by deterministic risk: **Low** (only documentation, comments, formatting, or typo-only string edits; zero executable-code and configuration changes) → no lens; **Medium** (every remaining change) → exactly ONE dominant-risk lens; **High** (security/auth/update/payments, data loss or exposure, permission changes, shell/process integration, or more than 400 authored changed lines) → four initial 4R lens sweeps. Generated goldens are excluded from the authored threshold but remain in snapshot identity. Model, provider, profile, and reasoning effort are never classifier inputs.

Risk table: Clear naming, structure, maintainability, or small refactors → `review-readability`; Behavior, state, tests, determinism, or regressions → `review-reliability`; Shell/process integration, partial failures, recovery, or degraded dependencies → `review-resilience`; Security, permissions, data exposure/loss, architecture, or dependencies → `review-risk`.

- At **pre-commit**, always: validate the existing content-bound receipt with native `validate review receipt via mem_review/mem_search against AGENTS.md <gate> --cwd <repo>`; never start a reviewer or reset its budget. (validate the staged/intended content against the existing receipt; never create a review budget)
- At **pre-push**, always: validate the existing content-bound receipt with native `validate review receipt via mem_review/mem_search against AGENTS.md <gate> --cwd <repo>`; never start a reviewer or reset its budget. (validate pushed commits against the same content-bound receipt)
- At **pre-pr**, always: validate the existing content-bound receipt with native `validate review receipt via mem_review/mem_search against AGENTS.md <gate> --cwd <repo>`; never start a reviewer or reset its budget. (validate candidate tree, paths, policy, evidence, base relationship, and receipt without reopening review)
- At **release**, always: validate the existing content-bound receipt with native `validate review receipt via mem_review/mem_search against AGENTS.md <gate> --cwd <repo>`; never start a reviewer or reset its budget. (validate immutable release tree, provenance, evidence, and publication boundary)
- At **post-sdd-phase**, after the apply phase completes: if no valid receipt exists, explicitly run `review/start(target)`; otherwise reuse the receipt. (explicitly start ordinary bounded implementation review after apply only when no valid receipt exists)
<!-- /tony-ai:trigger-rules -->