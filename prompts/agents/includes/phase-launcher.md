# Phase Launcher — Dynamic Include Resolver

This skill is used by the orchestrator to build sub-agent prompts dynamically by resolving includes from the phase manifest.

## Usage

When the orchestrator needs to launch a sub-agent for phase `X`:

1. Read `prompts/agents/includes/phase-manifest.json`
2. Look up `phases["X"]` (or `review_phases["X"]` for review agents)
3. Build the prompt by concatenating:
   - Base includes (always included)
   - Phase-specific includes
   - Skills (referenced as skill files to load)
4. Inject into the sub-agent prompt template

## Prompt Template

```
{file:./includes/sub-agent-context-protocol.md}

{file:./includes/{include_1}.md}
{file:./includes/{include_2}.md}
...

## Skills to load before work
{file:./../_shared/sdd-phase-common.md}
{file:./../_shared/{skill_1}.md}
...

## Phase-Specific Instructions
{file:./prompts/sdd/{phase_name}.md}
```

## Phase Mappings

| Phase | Base Includes | Extra Includes | Skills |
|-------|---------------|----------------|--------|
| sdd-apply | sub-agent-context-protocol | tonymem-topic-key-format, trigger-rules, strict-tdd-forwarding, apply-progress-continuity | sdd-phase-common, openspec-convention, tonymem-convention, skill-resolver |
| sdd-verify | sub-agent-context-protocol | trigger-rules, review-lens-selection, review-execution-contract, authority-first-terminal-procedure | sdd-phase-common, review-ledger-contract |
| sdd-spec | sub-agent-context-protocol | sdd-workflow, sdd-session-preflight, sdd-entry-routing, sdd-init-guard | sdd-phase-common, openspec-convention |
| sdd-design | sub-agent-context-protocol | sdd-workflow, sdd-session-preflight | sdd-phase-common, openspec-convention |
| sdd-tasks | sub-agent-context-protocol | sdd-workflow, review-workload-guard, delivery-strategy, chain-strategy | sdd-phase-common, openspec-convention, tonymem-convention, skill-resolver |
| sdd-archive | sub-agent-context-protocol | trigger-rules, sdd-workflow | sdd-phase-common, openspec-convention, tonymem-convention |
| sdd-explore | sub-agent-context-protocol | delegation-rules, mandatory-delegation-triggers | - |
| sdd-propose | sub-agent-context-protocol | sdd-workflow, sdd-session-preflight | sdd-phase-common |
| sdd-init | sub-agent-context-protocol | sdd-session-preflight, artifact-store-mode | sdd-phase-common, tonymem-convention |
| sdd-onboard | sub-agent-context-protocol | sdd-workflow, execution-mode, artifact-store-mode, delivery-strategy | sdd-phase-common |

## Review Phases

| Phase | Includes | Skills |
|-------|----------|--------|
| review-readability | review-lens-selection, review-execution-contract, authority-first-terminal-procedure | sdd-phase-common, review-ledger-contract |
| review-reliability | review-lens-selection, review-execution-contract, authority-first-terminal-procedure | sdd-phase-common, review-ledger-contract |
| review-resilience | review-lens-selection, review-execution-contract, authority-first-terminal-procedure | sdd-phase-common, review-ledger-contract |
| review-risk | review-lens-selection, review-execution-contract, authority-first-terminal-procedure | sdd-phase-common, review-ledger-contract |
| review-refuter | review-execution-contract, authority-first-terminal-procedure | sdd-phase-common, review-ledger-contract |

## Judgment Day Phases

| Phase | Includes | Skills |
|-------|----------|--------|
| jd-fix-agent | trigger-rules, strict-tdd-forwarding | sdd-phase-common |
| jd-judge-a | review-lens-selection, review-execution-contract, authority-first-terminal-procedure | sdd-phase-common, review-ledger-contract |
| jd-judge-b | review-lens-selection, review-execution-contract, authority-first-terminal-procedure | sdd-phase-common, review-ledger-contract |

## Usage in Orchestrator

When the orchestrator decides to launch a sub-agent for phase `X`:

1. Read `prompts/agents/includes/phase-manifest.json`
2. Resolve includes for phase `X`
3. Build prompt by concatenating `{file:./includes/{include}.md}` for each include
4. Append skills as `## Skills to load before work` + `{file:./../_shared/{skill}.md}`
4. Append phase-specific instructions from `prompts/sdd/{phase}.md` (which now only contains phase-specific logic, not common includes)
5. Launch sub-agent with constructed prompt

This ensures each sub-agent loads ONLY the includes it needs, reducing token overhead by ~70-80%.