# Tony-AI

Tony-AI is an agent orchestration system for software development based on Spec-Driven Development (SDD). It combines specialized agents, local LLMs, persistent memory, semantic code search, and deterministic workflow enforcement.

## What is Tony-AI?

Tony-AI separates **orchestration** from **enforcement**:

- **Orchestration** decides what work should be done and which agent can perform it.
- **Enforcement** deterministically decides whether a workflow transition is allowed.

The system is designed to preserve, index, retrieve, and reuse operational knowledge. It is not a model-training system.

## Architecture at a glance

```text
                         OpenCode
                            │
                            ▼
                    Tony Orchestrator
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
      TonyMem          Code Index       Judgment Memory
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                            ▼
                       SDD Workflow
                            │
                            ▼
                       Tony Kernel
                            │
                            ▼
                       Phase / Agent
```

For the detailed component model, workflow contracts, persistence model, and enforcement rules, see [ARCHITECTURE.md](ARCHITECTURE.md).

## SDD workflow

The main FSM contains exactly eight phases:

```text
explore → propose → spec → design → tasks → apply → verify → archive
```

Review 4R and Judgment Day are **auxiliary workflows**, not additional FSM phases. They can participate between implementation and verification without changing the eight-phase state machine.

## Context and memory

Context services participate throughout the workflow:

- **TonyMem** — persistent decisions, discoveries, and shared context.
- **Code Index** — semantic search over the codebase.
- **Judgment Memory** — previous review judgments and lessons.
- **DCP** — dynamic context management.
- **Tony Kernel** — deterministic workflow enforcement.

The systems are complementary rather than sequential. An agent may consult the appropriate service whenever the current phase needs that information.

## Judgment Day

Judgment Day is an explicit review flow separate from Review 4R. It retrieves relevant previous judgments before evaluation and records terminal results for future recall.

```text
Implementation
      │
      ├──────────────► Review 4R
      │
      └──────────────► Judgment Day
                              │
                         jd_recall
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
               jd-judge-a          jd-judge-b
                    │                   │
                    └─────────┬─────────┘
                              ▼
                         jd_record
                              │
                              ▼
                       Judgment Memory
                              │
                              ▼
                            Verify
```

## Tony Kernel

Tony Kernel is the deterministic enforcement layer. It validates, among other things:

- valid phase transitions;
- required artifacts;
- artifact integrity and checksums;
- allowed scope;
- evidence;
- retry budget;
- phase completion state.

The Kernel is **fail-closed**: when a mandatory condition is missing, the transition is blocked rather than inferred from an agent response.

## Installation

For the complete installation procedure, see [INSTALL.md](INSTALL.md).

The recommended setup is:

```bash
git clone https://github.com/gastoncelestino/tony-ai.git
cd tony-ai
git checkout dev
./scripts/setup.sh
./scripts/health.sh
```

## Usage

Initialize a project:

```text
/sdd-init
```

Start a change:

```text
/sdd-new "add rate limiting to the login endpoint"
```

Run implementation and verification:

```text
/sdd-apply
/sdd-verify
/sdd-archive
```

Useful operational commands include:

```text
/memory-search "rate limiting"
/memory-stats
/judgment-history
/kernel-status
```

Judgment Day can be explicitly requested when an independent judgment is needed.

## Local models

The default local model configuration is defined by the repository configuration and installation scripts. Do not treat this README as the source of truth for model names; use the current `opencode.json` and setup configuration.

## Documentation map

| Document | Source of truth for |
|---|---|
| `README.md` | Project overview, quickstart, and user-facing concepts |
| `INSTALL.md` | Installation and environment configuration |
| `ARCHITECTURE.md` | Components, responsibilities, workflow, contracts, and persistence |
| `TESTING.md` | Test strategy, commands, coverage, CI, and troubleshooting |
| `AGENTS.md` | Agent/development operating rules |
| Component READMEs | Implementation details specific to each subsystem |
| Code + tests | Definitive implemented behavior |

When two documents disagree about implemented behavior, verify the code and tests first and update the documentation that is not authoritative for that subject.

## Project structure

```text
tony-ai/
├── README.md
├── ARCHITECTURE.md
├── TESTING.md
├── INSTALL.md
├── AGENTS.md
├── opencode.json
├── kernel/
├── local-memory/
├── code-index/
├── judgment-memory/
├── plugins/
├── prompts/
├── skills/
├── tests/
├── tools/
└── docker/
```

## Documentation validation

The repository should eventually validate documentation references in the same way it validates configuration references. The intended checks are:

- documented SDD phases exist in the Kernel;
- documented agents and prompts exist;
- documented MCP servers exist;
- documented repository paths exist;
- documented commands correspond to configured commands or scripts.

Until an automated validator exists, treat `ARCHITECTURE.md` and the component contracts as the authoritative architectural references.
