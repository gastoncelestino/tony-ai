# Tony AI — Materialized prompt: sdd-tasks



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

### Review Workload Guard (MANDATORY)

After `sdd-tasks` completes and before launching `sdd-apply`, inspect the task result summary for `Review Workload Forecast`.

If it says `Chained PRs recommended: Yes`, `400-line budget risk: High`, estimated changed lines exceed 400, or `Decision needed before apply: Yes`, apply the cached `delivery_strategy`. Whenever a directive below tells the orchestrator to ask the user a decision (split vs. exception, or which chain strategy), present that decision via the `question` tool: each is its own single `question` tool call with its options; do NOT render the options as a plain markdown bullet list or plain chat text.

- **`ask-on-risk`**: STOP and ask, via the `question` tool, whether to split into chained/stacked PRs or proceed with `size:exception`. If the user chooses chained PRs and `chain_strategy` is not yet cached, also ask which chain strategy to use (stacked-to-main or feature-branch-chain) via the `question` tool.
- **`auto-chain`**: Do not ask about splitting. If `chain_strategy` is not yet cached, ask which chain strategy to use (stacked-to-main or feature-branch-chain) via the `question` tool. Then pass to `sdd-apply`: implement only the next autonomous slice using work-unit commits, with clear start, finish, verification, and rollback boundary.
- **`single-pr`**: STOP and require/record maintainer-approved `size:exception` before `sdd-apply`.
- **`exception-ok`**: Continue, but pass to `sdd-apply` that this run uses maintainer-approved `size:exception`.

Do this even in Automatic mode. Automatic mode does not override reviewer burnout protection.

When launching `sdd-apply`, always include the resolved `delivery_strategy`, `chain_strategy`, and any chosen PR boundary/exception in the prompt.

### Delivery Strategy

This is collected by `SDD Session Preflight` as the chained PR strategy. If missing, enforce the hard gate before any phase work. Ask which delivery/review strategy they want:

- **`ask-on-risk`** (default): Ask later if `sdd-tasks` forecasts high risk or >400 changed lines.
- **`auto-chain`**: If forecast is high, continue with chained/stacked PR slices without asking again.
- **`single-pr`**: Prefer one PR; if forecast exceeds 400 lines, require `size:exception` before apply.
- **`exception-ok`**: Allow a large PR because the maintainer explicitly accepts `size:exception`.

Cache the delivery strategy for the session. Pass it as `delivery_strategy` to `sdd-tasks` and `sdd-apply` prompts.

### Chain Strategy

When `delivery_strategy` results in chained PRs (either by user choice via `ask-on-risk` or automatically via `auto-chain`), ask the user which chain strategy to use. Use the `question` tool for this choice: present the two strategy options through a single `question` tool call; do NOT render the options as a plain markdown bullet list or plain chat text.

- **`stacked-to-main`**: Each PR merges to main in order. Fast iteration, fix on the go. Best for speed-first teams and independent slices.
- **`feature-branch-chain`**: The feature/tracker branch accumulates final integration; PR #1 targets the tracker branch, later child PRs target the immediate previous PR branch so review diffs stay focused. Only the tracker merges to main. Best for rollback control and coordinated releases.

Cache the chain strategy for the session. Pass it as `chain_strategy` to `sdd-tasks` and `sdd-apply` prompts alongside `delivery_strategy`. Do not ask again unless the user changes scope.

When delivery planning yields chained PRs, treat `chained-pr` (registry skill `tony-ai-chained-pr`) as a required skill match: resolve it by registry name through this template's existing skill-resolution mechanism (the same one it already uses to pass skills to phases) and ensure the `sdd-tasks` and `sdd-apply` phases load and follow it BEFORE planning or creating any PR. Do not hardcode the skill path; defer resolution to that mechanism.

## Skills to load before work



# SDD Phase — Common Protocol

Boilerplate identical across all SDD phase skills. Sub-agents MUST load this alongside their phase-specific SKILL.md.

Executor boundary: every SDD phase agent is an EXECUTOR, not an orchestrator. Do the phase work yourself. Do NOT launch sub-agents, do NOT call `delegate`/`task`, and do NOT bounce work back unless the phase skill explicitly says to stop and report a blocker.

## A. Skill Loading

1. Check if the orchestrator injected a `## Skills to load before work` block in your launch prompt. If yes, read those exact `SKILL.md` files before task-specific work.
2. If no skills block was provided, check for `SKILL: Load` instructions. If present, load those exact skill files.
3. If neither was provided, search for the skill registry as a fallback:
   a. `mem_search(query: "skill-registry", project: "{project}")` — if found, `mem_get_observation(id)` for full content
   b. Fallback: read `.atl/skill-registry.md` from the project root if it exists
   c. From the registry's skills index, match triggers to your task and read the exact listed `SKILL.md` paths.
4. If no registry exists, proceed with your phase skill only.

NOTE: the preferred path is (1) — exact skill paths selected by the orchestrator. Paths (2) and (3) are fallbacks. Searching the registry is SKILL LOADING, not delegation. If `## Skills to load before work` is present, IGNORE redundant `SKILL: Load` instructions.

## B. Artifact Retrieval (tonymem Mode)

**CRITICAL**: `mem_search` returns 300-char PREVIEWS, not full content. You MUST call `mem_get_observation(id)` for EVERY artifact. **Skipping this produces wrong output.**

**Run all searches in parallel** — do NOT search sequentially.

```
mem_search(query: "sdd/{change-name}/{artifact-type}", project: "{project}") → save ID
```

Then **run all retrievals in parallel**:

```
mem_get_observation(id: {saved_id}) → full content (REQUIRED)
```

Do NOT use search previews as source material.

## C. Artifact Persistence

Every phase that produces an artifact MUST persist it. Skipping this BREAKS the pipeline — downstream phases will not find your output.

### tonymem mode

```
mem_save(
  title: "sdd/{change-name}/{artifact-type}",
  topic_key: "sdd/{change-name}/{artifact-type}",
  type: "architecture",
  project: "{project}",
  capture_prompt: false,
  content: "{your full artifact markdown}"
)
```

`topic_key` enables upserts — saving again updates, not duplicates.
`capture_prompt: false` is mandatory for SDD artifacts because they are automated pipeline outputs, not human/proactive memory saves. Set it when the tonymem tool schema supports it; if an older schema rejects or does not expose the field, omit it rather than failing.

### OpenSpec mode

File was already written during the phase's main step. No additional action needed.

### Hybrid mode

Do BOTH: write the file to the filesystem AND call `mem_save` as above.

### None mode

Return result inline only. Do not write any files or call `mem_save`.

## D. Return Envelope

> **CRITICAL — Response ordering**: Your FINAL output MUST be text (the return envelope), NOT a tool call. If you need to save to tonymem (`mem_save`), do it BEFORE your final text response. Do NOT call `mem_session_summary` — that's for top-level agents only. **Why**: When a sub-agent's last action is a tool call, the parent agent receives only the tool result — your text response (the actual analysis) is lost.

Every phase MUST return a structured envelope to the orchestrator:

- `status`: `success`, `partial`, or `blocked`
- `executive_summary`: 1-3 sentence summary of what was done
- `detailed_report`: (optional) full phase output, or omit if already inline
- `artifacts`: list of artifact keys/paths written
- `next_recommended`: the next SDD phase to run, or "none"
- `risks`: risks discovered, or "None"
- `skill_resolution`: how skills were loaded — `paths-injected` (received exact skill paths from orchestrator), `fallback-registry` (self-loaded paths from registry), `fallback-path` (loaded via SKILL: Load path), or `none` (no skills loaded)

Example:

```markdown
**Status**: success
**Summary**: Proposal created for `{change-name}`. Defined scope, approach, and rollback plan.
**Artifacts**: tonymem `sdd/{change-name}/proposal` | `openspec/changes/{change-name}/proposal.md`
**Next**: sdd-spec or sdd-design
**Risks**: None
**Skill Resolution**: paths-injected — 3 skills (react-19, typescript, tailwind-4)
(other values: `fallback-registry`, `fallback-path`, or `none — no registry found`)
```

## E. Review Workload Guard

SDD must protect reviewer cognitive load, not only generate tasks.

- The default PR review budget is **400 changed lines** (`additions + deletions`).
- Count authored text additions plus deletions only for this threshold. Generated goldens are excluded from authored risk count but remain included in complete snapshot identity and receipt validation.
- The orchestrator MUST cache a delivery strategy at session start: `ask-on-risk` (default), `auto-chain`, `single-pr`, or `exception-ok`.
- The orchestrator MUST pass `delivery_strategy` to `sdd-tasks` and the resolved decision to `sdd-apply`.
- `sdd-tasks` MUST forecast whether the planned work may exceed that budget.
- The forecast MUST include exact plain-text guard lines: `Decision needed before apply: Yes|No`, `Chained PRs recommended: Yes|No`, and `400-line budget risk: Low|Medium|High`.
- If the forecast is high, `sdd-tasks` MUST recommend chained or stacked PRs using deliverable work units.
- `sdd-apply` MUST NOT start oversized work unless the delivery strategy resolves to chained/stacked PR slices or explicitly accepted `size:exception`.
- Each chained PR slice must have a clear start, clear finish, autonomous scope, verification, and reasonable rollback.
- In a Feature Branch Chain, PR #1 targets the feature/tracker branch and later child PRs target the immediate previous PR branch; if GitHub shows previous slices in a child diff, retarget/rebase until the diff is clean.

This guard exists to reduce reviewer burnout and keep implementation delivery safe. Do not treat it as optional process noise.

# OpenSpec File Convention (shared across all SDD skills)

## Directory Structure

```
openspec/
├── config.yaml              <- Project-specific SDD config
├── specs/                   <- Source of truth (main specs)
│   └── {domain}/
│       └── spec.md
└── changes/                 <- Active changes
    ├── archive/             <- Completed changes (YYYY-MM-DD-{change-name}/)
    └── {change-name}/       <- Active change folder
        ├── state.yaml       <- DAG state (survives compaction)
        ├── exploration.md   <- (optional) from sdd-explore
        ├── proposal.md      <- from sdd-propose
        ├── specs/           <- from sdd-spec
        │   └── {domain}/
        │       └── spec.md  <- Delta spec
        ├── design.md        <- from sdd-design
        ├── tasks.md         <- from sdd-tasks (updated by sdd-apply)
        └── verify-report.md <- from sdd-verify
```

## Artifact File Paths

| Skill | Creates / Reads | Path |
|-------|----------------|------|
| orchestrator | Creates/Updates | `openspec/changes/{change-name}/state.yaml` |
| sdd-init | Creates | `openspec/config.yaml`, `openspec/specs/`, `openspec/changes/`, `openspec/changes/archive/` |
| sdd-explore | Creates (optional) | `openspec/changes/{change-name}/exploration.md` |
| sdd-propose | Creates | `openspec/changes/{change-name}/proposal.md` |
| sdd-spec | Creates | `openspec/changes/{change-name}/specs/{domain}/spec.md` |
| sdd-design | Creates | `openspec/changes/{change-name}/design.md` |
| sdd-tasks | Creates | `openspec/changes/{change-name}/tasks.md` |
| sdd-apply | Updates | `openspec/changes/{change-name}/tasks.md` (marks `[x]`) |
| sdd-verify | Creates | `openspec/changes/{change-name}/verify-report.md` |
| sdd-archive | Moves | `openspec/changes/{change-name}/` → `openspec/changes/archive/YYYY-MM-DD-{change-name}/` |
| sdd-archive | Updates | `openspec/specs/{domain}/spec.md` (merges deltas into main specs) |

## Reading Artifacts

```
Proposal:   openspec/changes/{change-name}/proposal.md
Specs:      openspec/changes/{change-name}/specs/  (all domain subdirectories)
Design:     openspec/changes/{change-name}/design.md
Tasks:      openspec/changes/{change-name}/tasks.md
Verify:     openspec/changes/{change-name}/verify-report.md
Config:     openspec/config.yaml
Main specs: openspec/specs/{domain}/spec.md
```

## Writing Rules

- Always create the change directory before writing artifacts
- If a file already exists, READ it first and UPDATE it (don't overwrite blindly)
- If the change directory already exists with artifacts, the change is being CONTINUED
- Use `openspec/config.yaml` `rules` section for project-specific constraints per phase

## Delta Spec Sections

Delta specs MAY include these sections:

```markdown
## ADDED Requirements
## MODIFIED Requirements
## REMOVED Requirements
## RENAMED Requirements
```

- `ADDED` appends new requirements to the main spec.
- `MODIFIED` replaces the full matching requirement block in the main spec. The delta MUST contain the entire updated requirement, including unchanged scenarios that must be preserved.
- `REMOVED` deletes the matching requirement from the main spec. Each removed requirement MUST include `(Reason: ...)` and SHOULD include `(Migration: ...)` when consumers or persisted behavior are affected.
- `RENAMED` changes a requirement heading/name without changing behavior unless the delta also includes a `MODIFIED` block for the new requirement. Each rename MUST state old and new names explicitly.

## Config File Reference

```yaml
# openspec/config.yaml
schema: spec-driven

context: |
  Tech stack: {detected}
  Architecture: {detected}
  Testing: {detected}
  Style: {detected}

rules:
  proposal:
    - Include rollback plan for risky changes
  specs:
    - Use Given/When/Then for scenarios
    - Use RFC 2119 keywords (MUST, SHALL, SHOULD, MAY)
  design:
    - Include sequence diagrams for complex flows
    - Document architecture decisions with rationale
  tasks:
    - Group by phase, use hierarchical numbering
    - Keep tasks completable in one session
  apply:
    guidelines:
      - Follow existing code patterns
    tdd: false           # Set to true to enable RED-GREEN-REFACTOR
    test_command: ""
  verify:
    test_command: ""
    build_command: ""
    coverage_threshold: 0
  archive:
    - Warn before merging destructive deltas
```

## Archive Structure

When archiving, the change folder moves to:
```
openspec/changes/archive/YYYY-MM-DD-{change-name}/
```

Use today's date in ISO format. The archive is an AUDIT TRAIL — never delete or modify archived changes.

# TonyMem Artifact Convention (shared across all SDD skills)

## Storage Model

TonyMem persists SDD artifacts as observations in a shared SQLite database
(`memory.db`). Each artifact is one row in the `observations` table, keyed by
`(project, topic_key)` with upsert semantics: saving the same `topic_key` again
updates the existing row instead of creating a duplicate.

## Topic Key Format

Every SDD artifact uses a deterministic topic key so phases can find each
other's output without guessing:

```
sdd/{change-name}/{artifact-type}
```

| Artifact | Topic Key |
|----------|-----------|
| Project context | `sdd-init/{project}` |
| Exploration | `sdd/{change-name}/explore` |
| Proposal | `sdd/{change-name}/proposal` |
| Spec | `sdd/{change-name}/spec` |
| Design | `sdd/{change-name}/design` |
| Tasks | `sdd/{change-name}/tasks` |
| Apply progress | `sdd/{change-name}/apply-progress` |
| Verify report | `sdd/{change-name}/verify-report` |
| Archive report | `sdd/{change-name}/archive-report` |

## mem_save Contract

When persisting an artifact to tonymem, use:

```
mem_save(
  title: "sdd/{change-name}/{artifact-type}",
  topic_key: "sdd/{change-name}/{artifact-type}",
  type: "architecture",
  project: "{project}",
  capture_prompt: false,
  content: "{full artifact markdown}"
)
```

Rules:
- `capture_prompt: false` is mandatory for automated SDD artifacts. They are
  pipeline outputs, not human/proactive memory saves.
- If the tool schema does not expose `capture_prompt`, omit it rather than
  failing the save.
- `type` is advisory metadata; use `architecture` for planning artifacts,
  `decision` for choices, `bugfix` for corrections, or match the artifact kind.

## mem_get_observation Contract

`mem_search` returns 300-character previews. For full artifact content, always
follow up with `mem_get_observation(id)`. Never treat a search preview as
source material.

## mem_search Queries

To find an existing artifact:

```
mem_search(query: "sdd/{change-name}/{artifact-type}", project: "{project}")
```

To list all artifacts for a change:

```
mem_search(query: "sdd/{change-name}/", project: "{project}")
```

## Project Isolation

Every `mem_save` and `mem_search` MUST include `project`. Observations are
scoped by project; omitting `project` breaks isolation and pollutes other
projects' recall.

## Concurrent Writes

Two concurrent saves of the same `(project, topic_key)` must not crash. The
upsert path handles this at the SQLite level (`ON CONFLICT DO UPDATE`). Do not
implement manual read-modify-write cycles; always use `mem_save` with the
topic_key above.

## Memory Lifecycle

Saved memories can become stale as the codebase evolves. TonyMem uses a
three-state lifecycle to prevent outdated memories from being trusted as
current facts:

| State | Meaning |
|-------|---------|
| `active` | Current, verified memory (default on save). |
| `proven` | Solution verified through repeated Q&A. Ranks first in `mem_search`. |
| `needs_review` | Stale memory that must be re-verified before use. |

### mem_review Contract

Lifecycle transitions are managed exclusively through `mem_review`:

```
mem_review(action: "mark_stale", ids: [...])       // → needs_review
mem_review(action: "mark_reviewed", ids: [...])    // → active
mem_review(action: "mark_proven", ids: [...])      // → proven
mem_review(action: "list", project: "{project}")   // list needs_review (default)
mem_review(action: "list", project: "{project}", status: "proven")  // list by status
```

Rules:
- All transitions accept any source state (no guard on the previous status).
- `mem_search` results include `lifecycle_status` in every row. When a result
  shows `needs_review`, do NOT treat it as a confirmed fact — verify it
  against the current codebase/state before acting on it.
- `proven` memories rank first in `mem_search` (before `active` and
  `needs_review`), so verified solutions surface first.
- When saving updated knowledge for an evolving topic, reuse the same
  `topic_key` to upsert in place, then `mark_reviewed` if the prior state was
  `needs_review`.

### SDD Artifact Lifecycle

SDD artifacts (`proposal`, `spec`, `design`, `tasks`, etc.) default to
`active`. Mark a design decision as `proven` only after it has been validated
through a completed `sdd-verify` phase or repeated Q&A. If the codebase
diverges from a stored artifact (e.g. the spec no longer matches
implementation), `mark_stale` it and re-verify before reusing it.

## Fallback When tonymem Is Unavailable

If `mem_save` or `mem_search` returns `available: false` or fails, degrade to
`none` mode for that operation: return the artifact inline in your response and
do not block the phase. Report the degraded path in the Section D return
envelope's `risks` field.

﻿# Skill Resolver — Universal Protocol

Any agent that **delegates work to sub-agents** MUST use this protocol to resolve relevant skills and pass them safely.

## Why This Exists

Sub-agents start with no project skill context. The registry gives delegators a cheap index of available skills without rewriting or summarizing those skills.

## When to Apply

Before every sub-agent launch that involves reading, writing, reviewing, testing, documenting, or creating project artifacts. Skip only for purely mechanical commands.

## The Protocol

### Step 1: Obtain the Skill Registry

The registry is an **index** of skill names, triggers, scopes, and exact `SKILL.md` paths. It is not a compact-rules bundle.

Resolution order:
1. Use the session cache if present.
2. `mem_search(query: "skill-registry", project: "{project}")` → `mem_get_observation(id)` for full content.
3. Fallback: read `.atl/skill-registry.md` from the project root.
4. No registry found → proceed without project skills and warn the user to run `/sdd-skill-registry refresh` (OpenCode slash command) or manually rebuild the registry.

### Step 2: Match Relevant Skills

Match on two dimensions:

| Context | Match against |
| --- | --- |
| Code/files | Registry trigger/description mentions the language, framework, tool, or path context |
| Task/action | Registry trigger/description mentions actions like PR, review, docs, tests, Jira, comments, release |

Prefer the smallest useful set. If more than five skills match, keep the five most relevant and prioritize code context over task context.

### Step 3: Pass Skill Paths

Inject paths, not summaries:

```markdown
## Skills to load before work

Read these exact files before reading, writing, reviewing, testing, or creating artifacts:

- /absolute/path/to/skills/go-testing/SKILL.md
- /absolute/path/to/skills/typescript/SKILL.md
```

The sub-agent MUST read those files before task-specific work. `SKILL.md` is the runtime contract and source of truth.

### Step 4: Report Resolution

Sub-agents MUST report `skill_resolution`:

- `paths-injected` — received exact skill paths from the delegator and loaded them.
- `fallback-registry` — no paths received, self-loaded paths from the registry.
- `fallback-path` — loaded an explicit fallback path outside the registry.
- `none` — no skills loaded.

If a sub-agent reports anything other than `paths-injected`, the orchestrator MUST re-read the registry before the next delegation.

## Compaction Safety

- The registry persists in tonymem and `.atl/skill-registry.md`.
- Delegators can recover selected paths after compaction by re-reading the registry.
- Sub-agents receive exact files to read, so skill meaning is not degraded by generated summaries.

## Integration Points

- **ATL Orchestrator**: resolves paths for all SDD and non-SDD delegations.
- **judgment-day**: resolves paths before Judge A, Judge B, and Fix Agent.
- **pr-review and future delegators**: use this protocol when launching sub-agents.

## Phase-specific instructions

---
name: sdd-tasks
description: "Break down specs and design into implementation tasks. Trigger: orchestrator launches task planning."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Delegate to the dedicated `sdd-tasks` sub-agent.

## Executor Override

If you ARE the `sdd-tasks` sub-agent, continue. Do NOT delegate.

## Purpose

Break down specs and design into granular, implementable tasks with clear acceptance criteria.

## What You Receive

- Change name
- Spec (`sdd/{change-name}/spec`) and Design (`sdd/{change-name}/design`)
- Structured status with artifact paths

## Execution Steps

### 1. Load Skills & Context
Follow Section A from `skills/_shared/sdd-phase-common.md`.
Read spec, design, and structured status.

### 2. Generate Tasks
Break down into granular tasks with:

| Field | Description |
|---|---|
| **ID** | Hierarchical (1.1, 1.2, 2.1...) |
| **Title** | One-line description |
| **Description** | What to implement, acceptance criteria |
| **Phase** | Logical grouping (Foundation, Core, Integration, Polish) |
| **Dependencies** | Task IDs that must complete first |
| **Files** | Expected new/modified files |
| **Tests** | Required test scenarios |

**Task Granularity Rule**: Each task = 1 logical commit. If a task needs >2 files or >200 lines, split it.

### 3. Review Workload Guard
Forecast total changed lines and risk:
- If >400 lines OR high risk → forecast `Chained PRs recommended: Yes`
- Include `400-line budget risk: High/Medium/Low`
- Set `Decision needed before apply: Yes` if forecast exceeds budget

### 4. Delivery Strategy Forecast
If workload exceeds budget, forecast:
- `auto-chain` / `ask-on-risk` / `single-pr` / `exception-ok`
- Suggest `Chain strategy`: `stacked-to-main` or `feature-branch-chain`

### 5. Persist Tasks
Follow Section C from `sdd-phase-common.md`:
- artifact: `tasks`
- topic_key: `sdd/{change-name}/tasks`
- type: `architecture`

### 6. Return Summary
Return Section D envelope with tasks path, task count, workload forecast, and next_recommended: `sdd-apply`.

## Rules
- Each task = 1 logical commit / PR
- Tasks MUST have testable acceptance criteria
- Dependencies MUST form a DAG (no cycles)
- Flag spec/design gaps as task-level risks
