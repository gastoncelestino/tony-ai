# Tony-AI — Testing

## 1. Testing strategy

Tony-AI separates deterministic tests from runtime/infrastructure smoke tests.

```text
                    Tony-AI Testing
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
    Python tests      TypeScript tests   Configuration
        │                 │                   │
      pytest           Bun test        validate-config
        │                 │                   │
        └────────────── deterministic ───────┘
                          │
                          ▼
                 Smoke / health checks
                    Ollama + Qdrant
```

The distinction is intentional:

- **Tests** answer whether deterministic behavior is correct.
- **Health/smoke checks** answer whether the configured runtime and external services are available and working.

## 2. Quick start

For normal changes:

```bash
make test
```

For Kernel, MCP, configuration, or infrastructure changes:

```bash
make test-all
make health
```

Before push:

```bash
make test
bun run tools/validate-config.ts
git diff --check
```

## 3. Commands by change type

| Change | Command |
|---|---|
| Normal feature/bugfix | `make test` |
| Kernel/MCP/config | `make test-all` |
| Kernel + infrastructure | `make test-all` + `make health` |
| Code Index | `make test-all` |
| Judgment Memory | `make test-all` |
| Python only | `make test-python` |
| TypeScript only | `make test-ts` |
| SDD flow | `make verify-sdd-flow` |
| Real Qdrant roundtrip | `make verify-qdrant` |

The Makefile is the source of truth for the available targets. This document describes how they are intended to be used.

## 4. Test layers

### Python

Kernel, Code Index, Judgment Memory, local-memory, and deterministic SDD flow tests.

```bash
make test-python
python3 -m pytest tests -v
```

If pytest is unavailable, the repository may use its standalone Python test runner where supported.

### TypeScript

OpenCode plugin and hook tests:

```bash
make test-ts
bun test tests
```

### Configuration

```bash
bun run tools/validate-config.ts
```

This validates configuration structure and referenced agents, prompts, MCP servers, and files according to the current validator implementation.

### SDD flow

```bash
make verify-sdd-flow
```

This verifies the deterministic SDD flow without requiring the complete LLM/runtime stack.

## 5. What is tested

### Tony Kernel

The Kernel suite covers the state machine, gates, checksums, scope, evidence, retry behavior, ledgers, and fail-closed enforcement.

The exact test inventory is defined by `tests/` and the Makefile targets.

### MCP servers

Tests cover the JSON-RPC contract of the MCP servers, including initialization, tool discovery, tool calls, invalid requests, and unknown tools where applicable.

### Judgment Memory

Tests cover ledger persistence, judgment normalization, retrieval behavior, thresholds, filters, and degraded behavior when external indexing is unavailable.

### Code Index

Tests cover structural chunking, incremental indexing, semantic search, and file changes.

### Configuration and prompts

Configuration validation checks source prompts, agents, MCP registrations, references, and naming conventions according to the validator implementation.

## 6. Discovery conventions

Python tests should follow the repository's configured discovery conventions, normally:

```text
tests/test_*.py
tests/*_test.py
```

TypeScript tests use:

```text
tests/*.test.ts
```

Use:

```bash
make check-test-discovery
```

to validate the current rules.

## 7. Coverage

Python:

```bash
make coverage-python
```

TypeScript:

```bash
make coverage-ts
```

Combined:

```bash
make coverage
```

Coverage thresholds and generated artifact names are controlled by the repository tooling. Avoid duplicating a numeric threshold here unless the tooling exposes it as a stable contract.

## 8. Smoke tests and external infrastructure

These checks are intentionally separate from the deterministic test suite.

### Qdrant roundtrip

```bash
make verify-qdrant
```

### Full health check

```bash
make health
```

A useful interpretation is:

```text
make test   PASS + make health FAIL
        │
        └── likely runtime/infrastructure problem

make test   FAIL
        │
        └── investigate code/config behavior first
```

## 9. CI

CI configuration is authoritative for the exact matrix and jobs. This document intentionally avoids duplicating every CI implementation detail.

At a high level, CI should validate:

1. test discovery;
2. deterministic Python tests;
3. deterministic TypeScript tests;
4. configuration validation;
5. coverage where configured;
6. Docker/build checks where configured.

## 10. Troubleshooting

### Isolate one Python test

```bash
python3 -m pytest tests/test_<module>.py::test_<name> -vv -s
```

### Validate configuration

```bash
bun run tools/validate-config.ts
```

### Check external services

```bash
curl http://localhost:11434/api/tags
curl http://localhost:6333/readyz
```

### Test without external infrastructure

Prefer `make test` or the relevant deterministic target instead of `make health`.

## 11. Documentation consistency

Testing documentation follows the same source-of-truth rule as the rest of the project:

| Subject | Source of truth |
|---|---|
| Test targets | `Makefile` |
| Test discovery | Test runner / Makefile validation |
| CI matrix and jobs | `.github/workflows/*` |
| Coverage configuration | Test tooling/configuration |
| Test behavior | `tests/` |
| Architecture | `ARCHITECTURE.md` |
| Installation | `INSTALL.md` |

If this document conflicts with the actual test runner, Makefile, CI workflow, or tests, the implementation is authoritative and this document should be corrected.

## 12. Future documentation validation

A future `make validate-docs` target should verify that documented commands, paths, phases, agents, prompts, and MCP servers correspond to the repository implementation.
