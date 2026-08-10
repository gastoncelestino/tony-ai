---
name: sdd-onboard
description: "Guided end-to-end walkthrough of SDD using your real codebase. Trigger: user wants to learn SDD by doing."
disable-model-invocation: true
user-invocable: true
license: MIT
metadata:
  author: gentleman-programming
  version: "3.0"
  delegate_only: true
---

> **ORCHESTRATOR GATE**: If you loaded this skill via the `skill()` tool, you are
> the ORCHESTRATOR — this command is user-invocable. If you are the orchestrator,
> run the onboarding flow directly. If you are a sub-agent, STOP.

## Purpose

Guide the user through a complete SDD cycle using their real codebase. This is a teaching command, not a production phase.

## What You Receive

- User wants to learn SDD by doing
- Their real codebase as the training ground

## Execution Flow

### 1. Welcome & Setup
- Explain SDD in 2 minutes (8 phases, orchestration, memory)
- Run `/sdd-init` to bootstrap their project
- Explain artifact stores (tonymem vs openspec)

### 2. Pick a Real Change
Help user pick a SMALL real change from their backlog:
- 1-2 files, 1-2 hours max
- Has clear requirements
- Not security-critical

### 3. Run Full Cycle (Interactive)
Guide through each phase with explanations:

| Phase | Command | What Happens |
|---|---|---|
| Explore | `/sdd-explore "topic"` | Investigate codebase, compare approaches |
| Propose | `/sdd-propose` | Create proposal with business context |
| Spec | `/sdd-spec` | Write detailed technical spec |
| Design | `/sdd-design` | Define architecture, data, interfaces |
| Tasks | `/sdd-tasks` | Break into granular implementable tasks |
| Apply | `/sdd-apply` | Implement tasks (with TDD if available) |
| Verify | `/sdd-verify` | Run tests, prove compliance |
| Archive | `/sdd-archive` | Close change, persist lessons |

At each phase:
- Explain WHY this phase exists
- Show the artifact produced
- Let user review/approve before continuing

### 4. Debrief
- Review what artifacts were created
- Show how tonymem remembers decisions
- Explain how next change reuses context
- Point to advanced features (Judgment Day, chained PRs, etc.)

## Rules
- User must approve each phase before continuing
- Use their REAL codebase — no toy examples
- Keep first change SMALL (< 2 hours total)
- Celebrate completion — they just did SDD end-to-end!