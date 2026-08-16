# Tony-AI — Architecture

## 1. Purpose and architectural principles

Tony-AI is an agent orchestration system for software development based on Spec-Driven Development (SDD).

The architecture separates two responsibilities that must not depend solely on LLM behavior:

- **Orchestration:** decide what work should be executed and which agent has the required capability.
- **Enforcement:** deterministically decide whether a phase may start, complete, or advance.

Tony-AI combines specialized agents, persistent memory, semantic search, dynamic context management, and a deterministic Kernel.

Tony-AI does not train models. Its purpose is to preserve, index, retrieve, and apply operational knowledge during later tasks.

---

## 2. High-level architecture

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

| Component | Responsibility |
|---|---|
| **OpenCode** | Agent runtime, plugins, and tools |
| **Tony Orchestrator** | Routing, coordination, and minimum routing context |
| **Tony Kernel** | FSM, gates, scope, evidence, checksums, and enforcement |
| **TonyMem** | Persistent decisions, discoveries, and shared context |
| **Code Index** | Semantic search over the codebase |
| **Judgment Memory** | Persistence and retrieval of previous judgments |
| **DCP** | Dynamic context management |

The key boundary is:

```text
Orchestrator → decides what should run
Kernel       → decides whether it may run
Sub-agent    → performs the phase work
Context      → supplies information when needed
```

---

## 3. Component responsibilities

### OpenCode

OpenCode hosts agent execution, plugins, and tools. Agent and MCP configuration is defined through `opencode.json` and related project configuration.

OpenCode can execute actions, but authorization for a Kernel-controlled phase transition belongs to Tony Kernel.

### Tony Orchestrator

The orchestrator keeps only the context required to route the workflow:

1. understands the current SDD state;
2. resolves the required capability through `phase-capabilities.md`;
3. selects the appropriate phase agent;
4. delegates only the information required to start the phase;
5. receives a structured result and routes the next operation.

The orchestrator does not need to load every executor prompt to make a routing decision, does not perform phase work inline, and does not copy complete upstream artifacts into every delegation.

### Tony Kernel

Tony Kernel is the deterministic enforcement layer. It controls:

- valid phase transitions;
- required artifacts;
- artifact integrity and checksums;
- allowed scope;
- evidence;
- retry budget;
- phase completion state.

The Kernel is **fail-closed**. If a mandatory condition is missing, the transition is blocked instead of being inferred from an agent response.

### TonyMem

TonyMem provides persistent memory for decisions, discoveries, and context shared across sessions.

- MCP server: `local-memory/server.py`;
- OpenCode integration: `plugins/tonymem.ts`;
- SQLite persistence;
- WAL mode for concurrent access;
- memory lifecycle: `active`, `proven`, `needs_review`.

### Code Index

Code Index provides semantic search over the codebase using local embeddings and Qdrant.

- MCP server: `code-index/server.py`;
- embeddings: `bge-m3`;
- vector storage: Qdrant;
- incremental indexing;
- structural chunking through tree-sitter.

### Judgment Memory

Judgment Memory persists judgments and lessons from Judgment Day so they can be recalled by later evaluations.

- SQLite ledger: `judgment-memory/ledger.py`;
- Qdrant vector storage;
- separate collection `jdmem_{project}`;
- retrieval through `jd_recall`;
- persistence through `jd_record`.

### DCP

Dynamic Context Pruning manages the amount of context used by OpenCode during long workflows and preserves relevant context when the available window is constrained.

---

## 4. Workflow architecture

A task passes through several layers before producing a verified change:

```text
User
  │
  ▼
OpenCode
  │
  ▼
Tony Orchestrator
  │
  ├──────────────► TonyMem
  ├──────────────► Code Index
  ├──────────────► Judgment Memory
  └──────────────► DCP
  │
  ▼
SDD Phase
  │
  ▼
Tony Kernel
  │
  ├── Phase Gate
  ├── Artifact Gate
  ├── Scope Guard
  ├── Evidence
  ├── Checksums
  └── Retry Budget
  │
  ▼
Sub-agent
  │
  ▼
Phase Result
  │
  ▼
Tony Kernel
  │
  ├── validates artifacts
  ├── validates evidence
  ├── validates scope
  └── records completion
  │
  ▼
Next phase
```

Context services are transversal. There is no single final "read memory" stage.

---

## 5. SDD state machine

The main FSM contains exactly eight phases:

```text
explore
  ↓
propose
  ↓
spec
  ↓
design
  ↓
tasks
  ↓
apply
  ↓
verify
  ↓
archive
```

`kernel/state_machine.py` is the source of truth for valid FSM phases and transitions.

### FSM phases vs auxiliary agents

Not every agent participating in the workflow is an FSM phase.

**Kernel-controlled phases:**

```text
explore
propose
spec
design
tasks
apply
verify
archive
```

**Auxiliary workflows/agents:**

```text
sdd-init
sdd-onboard
review-*
jd-*
gga-reviewer
```

Auxiliary agents may participate in the workflow without becoming additional FSM transitions.

Review 4R and Judgment Day therefore do **not** increase the number of SDD phases.

---

## 6. Tony Kernel enforcement

### Phase Gate

Prevents a phase from starting when the current state, transition, or preconditions are invalid.

### Artifact Gate

Validates that required artifacts exist and satisfy the integrity requirements of the current phase.

### Scope Guard

Ensures changes remain inside the scope allowed by the change request.

### Evidence

Records evidence associated with tasks and phase completion so advancement does not depend solely on a textual claim by an agent.

### Checksums

Detects changes to artifacts that were already validated.

### Retry Budget

Limits retries per phase to prevent uncontrolled loops.

### OpenCode integration

The OpenCode Kernel plugin intercepts tool execution events to enforce phase start checks before delegation and completion recording after execution.

The Kernel CLI exposes operations such as:

```text
can_start_phase
record_delegation
record_phase_completion
check_scope
reset
status
```

Operational Kernel state is stored under `.tony-kernel/` according to the current persistence implementation.

---

## 7. Context and memory architecture

```text
New task
   │
   ├── TonyMem ──────────────► previous decisions and context
   ├── Code Index ───────────► related code
   ├── Judgment Memory ──────► previous judgments and lessons
   └── DCP ──────────────────► relevant working context
                                      │
                                      ▼
                               Agent / Orchestrator
                                      │
                                      ▼
                                  SDD Phase
                                      │
                                      ▼
                                 Tony Kernel
```

### TonyMem

Memories have three lifecycle states:

- `active` — usable by default;
- `proven` — verified knowledge that can be prioritized;
- `needs_review` — potentially stale knowledge that must be verified before being trusted.

### Code Index

The Code Index locates semantically related code without requiring the agent to know exact paths or identifiers in advance.

### Judgment Memory

Before a Judgment Day evaluation, `jd_recall` retrieves similar previous judgments. When a judgment reaches a terminal state, `jd_record` persists the result and indexes it for later retrieval.

### Prompt persistence

Prompt captures are bookkeeping/context data and should not be mixed with normal semantic memory searches unless explicitly requested.

---

## 8. Review 4R and Judgment Day

### Review 4R

Review 4R is the ordinary post-implementation review workflow. Review agents inspect defined dimensions of the implementation and are read-only.

`review-refuter` validates supplied inferences and does not invent new findings.

### Judgment Day

Judgment Day is an explicit workflow separate from Review 4R and is **not an additional FSM phase**.

Conceptually:

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

Judgment Memory exists specifically so previous judgments can inform later judgments without turning those judgments into ordinary project memory.

`jd-fix-agent` applies only corrections confirmed by the judgment process.

---

## 9. Persistence and storage

Tony-AI separates storage by responsibility:

| System | Storage | Purpose |
|---|---|---|
| TonyMem | SQLite | Decisions, observations, and context |
| Judgment Memory | SQLite + Qdrant | Judgment ledger and semantic recall |
| Code Index | Qdrant | Semantic code index |
| Tony Kernel | JSON/files | Operational state and artifacts |

The exact filesystem paths and environment variables used by the current implementation are documented in `INSTALL.md` and the corresponding component READMEs. This avoids duplicating implementation-specific paths in multiple architecture documents.

---

## 10. Shared contracts

Shared contracts define behavior that multiple agents or subsystems depend on.

- `skills/_shared/sdd-phase-common.md` — common SDD executor contract.
- `skills/_shared/tonymem-convention.md` — TonyMem topics, operations, isolation, concurrency, and lifecycle.
- `skills/_shared/openspec-convention.md` — filesystem paths and delta-spec conventions.
- `skills/_shared/skill-resolver.md` — skill resolution protocol.

The shared contract files are the source of truth for their respective protocols; this document only explains their architectural role.

---

## 11. Prompt and agent architecture

SDD agents use source prompts directly. Prompt generation or bundle materialization is not an architectural requirement.

Important prompt responsibilities include:

- `prompts/agents/tony-orchestrator.md` — orchestration.
- `prompts/agents/phase-capabilities.md` — capability/routing map.
- `prompts/agents/includes/phase-launcher.md` — phase launch contract.
- `prompts/sdd/<phase>.md` — phase-specific instructions.
- `prompts/agents/phase-prompts/*.md` — review and Judgment Day agents.

The orchestrator keeps minimum routing context. Phase executors retrieve upstream artifacts when their phase requires them.

---

## 12. Repository structure

```text
tony-ai/
├── README.md
├── ARCHITECTURE.md
├── TESTING.md
├── INSTALL.md
├── AGENTS.md
├── opencode.json
│
├── kernel/                 # deterministic workflow enforcement
├── local-memory/           # TonyMem MCP server
├── code-index/             # Code Index MCP server
├── judgment-memory/        # Judgment Memory
├── plugins/                # OpenCode integrations
├── prompts/                # orchestrator, phases, and reviewers
├── skills/                 # shared contracts and capabilities
├── tests/                  # test suite
├── tools/                  # tooling and runners
└── docker/                 # local infrastructure
```

---

## 13. Documentation boundaries and sources of truth

Documentation has explicit ownership to prevent multiple conflicting definitions.

| Document | Source of truth for |
|---|---|
| `README.md` | Project overview, quickstart, and user-facing concepts |
| `INSTALL.md` | Installation and environment configuration |
| `ARCHITECTURE.md` | Architectural model and component responsibilities |
| `TESTING.md` | Test strategy, commands, coverage, CI, and troubleshooting |
| `AGENTS.md` | Agent/development operating rules |
| Component READMEs | Subsystem implementation details |
| `skills/_shared/*` | Shared agent protocols and conventions |
| `kernel/state_machine.py` | FSM phases and valid transitions |
| `opencode.json` + source configuration | Active agent/MCP wiring |
| Code + tests | Definitive implemented behavior |

When documentation conflicts with the implementation, verify the code and tests first. Then update the document that is not authoritative for that subject.

Architecture should describe stable responsibilities and contracts, not duplicate every implementation detail.

---

## 14. Future documentation validation

The documentation model should eventually be machine-checked by a repository validation command such as `make validate-docs`.

The validator should detect at least:

- documented SDD phases that do not exist in the Kernel;
- documented agents or prompts that do not exist;
- documented MCP servers that do not exist;
- documented repository paths that do not exist;
- documented commands that are not configured or implemented.

This keeps documentation aligned with the same deterministic principles used by Tony Kernel and configuration validation.
