# Phase Launcher — Phase Routing

This skill is used by the orchestrator to route work to the appropriate sub-agent without constructing phase prompts.

## Purpose

The launcher owns routing and delegation only.

It does not own phase implementation rules, artifact schemas, persistence protocols, review procedures, or prompt composition.

## Usage

When the orchestrator needs to launch phase `X`:

1. Resolve `X` through the phase capabilities/routing map.
2. Select the corresponding dedicated agent.
3. Pass only the inputs required by that phase.
4. Launch the agent using its configured source prompt.
5. Return the phase result to the orchestrator.

## SDD Phase Routing

| Phase | Agent | Capability |
|-------|-------|------------|
| sdd-init | sdd-init | Initialize SDD state and project capabilities |
| sdd-onboard | sdd-onboard | Guide the user through an SDD walkthrough |
| sdd-explore | sdd-explore | Investigate questions, code, constraints, and approaches |
| sdd-propose | sdd-propose | Turn exploration into a scoped proposal |
| sdd-spec | sdd-spec | Turn proposal into an acceptance-oriented technical specification |
| sdd-design | sdd-design | Turn specification into an implementation design |
| sdd-tasks | sdd-tasks | Turn specification/design into ordered implementation tasks |
| sdd-apply | sdd-apply | Implement an assigned task slice |
| sdd-verify | sdd-verify | Validate implementation against specification and tests |
| sdd-archive | sdd-archive | Close the change and persist final state |

## Launch Contract

For every SDD phase:

- The phase agent owns its implementation instructions.
- The orchestrator owns routing and delegation only.
- The phase prompt is loaded directly from the configured agent definition.
- Pass references and identifiers instead of copying full artifacts whenever possible.
- Retrieve upstream artifacts only when the target phase requires them.
- Pass only the status fields required by the target phase.
- Never load all phase prompts or all phase artifacts into the launch context.

## Review Phases

| Phase | Agent |
|-------|-------|
| review-readability | review-readability |
| review-reliability | review-reliability |
| review-resilience | review-resilience |
| review-risk | review-risk |
| review-refuter | review-refuter |

Review agents own their review-specific instructions and receive only the review context required by the selected lens.

## Judgment Day Phases

| Phase | Agent |
|-------|-------|
| jd-fix-agent | jd-fix-agent |
| jd-judge-a | jd-judge-a |
| jd-judge-b | jd-judge-b |

Judgment Day agents own their phase-specific instructions and receive only the context required by the selected operation.

## Context Boundary

The launcher must not become a second orchestrator or a prompt compiler.

It must not:

- construct or modify phase prompts
- resolve dynamic includes
- load phase-specific implementation instructions
- load every phase's protocol or skill
- copy unrelated artifacts into a phase launch
- implement phase-specific workflow logic
- retrieve artifacts on behalf of the target phase unless explicitly required by the launch contract

The dedicated phase agent is responsible for its own phase instructions and for retrieving the minimum additional context required to complete its work.