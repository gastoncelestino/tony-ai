# Tony AI — Materialized prompt: sdd-propose



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

### SDD Workflow (Spec-Driven Development)

SDD is the structured planning layer for substantial changes.

### Artifact Store Policy

- `tonymem` -> default when available; persistent memory across sessions
- `openspec` -> file-based artifacts; use only when the user explicitly requests it
- `hybrid` -> both backends; cross-session recovery + local files; more tokens per operation
- `none` -> return results inline only; recommend enabling tonymem or openspec

### Commands

Skills (appear in autocomplete):

- `/sdd-init` -> initialize SDD context; detects stack, bootstraps persistence
- `/sdd-explore <topic>` -> investigate an idea; reads codebase, compares approaches; no files created
- `/sdd-status [change]` -> read-only structured status for active change, artifacts, tasks, and next action
- `/sdd-apply [change]` -> implement tasks in batches; checks off items as it goes
- `/sdd-verify [change]` -> validate implementation against specs; reports CRITICAL / WARNING / SUGGESTION
- `/sdd-archive [change]` -> close a change and persist final state in the active artifact store
- `/sdd-onboard` -> guided end-to-end walkthrough of SDD using your real codebase

Meta-commands (type directly - orchestrator handles them, won't appear in autocomplete):

- `/sdd-new <change>` -> start a new change by delegating exploration + proposal to sub-agents
- `/sdd-continue [change]` -> run the next dependency-ready phase via sub-agent(s)
- `/sdd-ff <name>` -> fast-forward planning: proposal -> specs -> design -> tasks

`/sdd-new`, `/sdd-continue`, and `/sdd-ff` are meta-commands handled by YOU. Do NOT invoke them as skills.

### SDD Session Preflight (HARD GATE)

Before executing ANY SDD command or natural-language SDD request, ensure this session has an explicit `SDD Session Preflight` decision block.

This applies to `/sdd-new`, `/sdd-ff`, `/sdd-continue`, `/sdd-explore`, `/sdd-status`, `/sdd-apply`, `/sdd-verify`, `/sdd-archive`, and natural-language equivalents such as "use SDD to add dark mode" / "do it with SDD".

Required preflight choices:

1. **Execution mode**: `interactive` or `auto`.
2. **Artifact store**: `openspec`, `tonymem`, or `both` when tonymem is callable. If tonymem is unavailable, offer only file/inline-safe choices.
3. **Chained PR strategy**: `auto-forecast`, `ask-always`, `single-pr-default`, or `force-chained`.
4. **Review budget**: maximum changed lines before stopping for reviewer-burden approval.

User-facing preflight question format:

Use the `question` tool for SDD Session Preflight. Do NOT render the full preflight menu as plain chat text.

Ask all four preflight groups in one single `question` tool call so OpenCode can render the groups as tabs. Do NOT run this as a sequential wizard. Do NOT issue four separate `question` tool calls.

The single `question` tool call must contain these four localized groups in this order:

1. Pace: Interactive, Automatic.
2. Artifacts: OpenSpec, tonymem, Both.
3. PRs: Ask me, Single PR, Chained, Auto.
4. Review: 400 lines, 800 lines, Other.

Match the user's current language and active persona for question labels and descriptions. Treat the preflight UI as direct orchestrator conversation, not as a generated technical artifact. Technical artifacts still default to English, but this UI follows the user's conversation language/persona. Do NOT mix languages inside one grouped question.

Do NOT show option codes in the interactive UI. Do NOT show canonical values or other internal values in the interactive UI labels or descriptions.

After the single grouped `question` tool call returns, map the selected human labels to canonical values internally. Do not reveal the canonical values in the UI.

If Other is selected for review budget, ask one follow-up question for the numeric budget.

Only after all four preflight choices are collected, summarize them as the `SDD Session Preflight` decision block and continue with the SDD init guard/requested phase.

Map answers to canonical values:

- Pace: Interactive -> `interactive`; Automatic -> `auto`.
- Artifacts: OpenSpec -> `openspec`; tonymem -> `tonymem`; Both -> `both`.
- PRs: Ask me -> `ask-always`; Single PR -> `single-pr-default`; Chained -> `force-chained`; Auto -> `auto-forecast`.
- Review: 400 lines -> `review_budget_lines: 400`; 800 lines -> `review_budget_lines: 800`; Other -> ask one follow-up for the number.

Hard gate rules:

- `openspec/config.yaml`, existing SDD artifacts, previous `sdd-init` results, or installed SDD assets do NOT satisfy session preflight.
- If the session has no preflight block, ask the single grouped `question` tool preflight above. Do not run init, delegate phases, edit files, or apply tasks until all four choices are collected.
- Cache the choices for this session and include them in later phase prompts.
- If the user explicitly provided all four choices in the current conversation, summarize them as the session preflight block and continue.

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

## Phase-specific instructions

---
name: sdd-propose
description: "Create change proposal from exploration. Trigger: orchestrator launches proposal phase."
disable-model-invocation: true
user-invocable: false
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — STOP. Delegate to the dedicated `sdd-propose` sub-agent.

## Executor Override

If you ARE the `sdd-propose` sub-agent, continue. Do NOT delegate.

## Purpose

Create a change proposal with business context, requirements, and scope boundaries.

## What You Receive

- Exploration report (`sdd/{change-name}/explore`) if exists
- Optional: raw topic from user

## Execution Steps

### 1. Load Skills & Context
Follow Section A from `skills/_shared/sdd-phase-common.md`.
Read exploration if exists.

### 2. Create Proposal
Produce proposal covering:

| Section | Content |
|---|---|
| **Business Problem** | What problem are we solving? Who is affected? |
| **Target Users** | Who uses this, in what situations |
| **Current State Gap** | What exists now, what's missing |
| **Proposed Solution** | High-level approach |
| **Requirements** | Functional & non-functional (from exploration) |
| **Scope Boundaries** | What's in / out of scope |
| **Non-Goals** | Explicitly excluded |
| **Assumptions** | What we assume true |
| **Risks** | Technical, product, timeline |
| **First Slice** | Smallest valuable increment |

### 3. Proposal Questions (Interactive Mode)
If interactive, ask 3-5 clarifying questions:
- Business rules, edge cases, constraints, trade-offs
- Present correct/second-round/continue via `question` tool

### 3. Persist Proposal
Follow Section C from `sdd-phase-common.md`:
- artifact: `proposal`
- topic_key: `sdd/{change-name}/proposal`
- type: `decision`

### 4. Return Summary
Return Section D envelope with proposal path and next_recommended: `sdd-spec`.

## Rules
- Proposal = business context + requirements, NOT technical design
- Scope boundaries MUST be explicit (in/out)
- Non-goals are as important as goals
- First slice MUST be independently valuable
