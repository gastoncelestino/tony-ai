# Tony-AI — Installation

## 1. Installation layers

Tony-AI has two execution levels:

- **Development/test environment:** Python 3.10+, Bun, and `requirements-dev.txt`.
- **Full runtime:** additionally requires OpenCode CLI, Ollama, Docker + Compose, Qdrant, GGA, and tree-sitter dependencies.

| Requirement | Purpose | Required for |
|---|---|---|
| Python 3.10+ | MCP servers, Kernel, tooling | Development and runtime |
| Bun | Plugins and TypeScript tests | Development and OpenCode runtime |
| OpenCode CLI | Agent runtime and SDD orchestration | Full runtime |
| Ollama | Local models and embeddings | Full runtime |
| Docker + Compose | Service infrastructure | Full runtime/setup |
| GGA | Code review | Full runtime/setup |
| tree-sitter + language pack | Structural Code Index chunking | Code Index |

`setup.sh` is the implementation authority for the actual installation sequence. This document explains the supported setup rather than duplicating every script branch.

## 2. Clone

```bash
git clone https://github.com/gastoncelestino/tony-ai.git
cd tony-ai
git checkout dev
```

## 3. Recommended setup

```bash
./scripts/setup.sh
```

Then run:

```bash
./scripts/health.sh
```

`setup.sh` prepares the environment. `health.sh` verifies an already configured environment; it does not replace installation.

## 4. Environment and persistence

The repository uses `.env.example` as the configuration template. The setup process creates the local `.env` when needed.

Typical runtime configuration includes:

```env
TONY_REPO_ROOT=/path/to/tony-ai
TONY_OLLAMA_URL=http://localhost:11434
TONY_QDRANT_URL=http://localhost:6333
TONY_INDEX_CHUNKER=tree-sitter
```

The exact defaults consumed by each subsystem are defined by the component configuration and setup scripts. Avoid treating this document as the source of truth for internal storage paths.

For subsystem-specific persistence details, see `ARCHITECTURE.md` and the relevant component README.

## 5. Ollama and Qdrant

### Existing native Ollama

If Ollama is already available on `http://localhost:11434`, reuse it rather than starting a second instance.

```bash
curl http://localhost:11434/api/tags
```

### Qdrant

```bash
cd docker
docker compose up -d qdrant
```

Verify:

```bash
curl http://localhost:6333/readyz
docker compose ps
```

### Both services

If neither service is available:

```bash
cd docker
docker compose up -d ollama qdrant
```

## 6. GGA

Verify:

```bash
gga --version
```

The setup script attempts to install GGA when it is missing, according to the current installer implementation.

## 7. Troubleshooting

### Python version

```bash
python3 --version
```

Must be 3.10 or newer.

### Bun, OpenCode, or GGA missing

```bash
command -v bun
command -v opencode
command -v gga
```

### Docker unavailable

```bash
docker info
docker compose version
```

### Ollama unavailable

```bash
curl http://localhost:11434/api/tags
```

### Qdrant unavailable

```bash
curl http://localhost:6333/readyz
cd docker && docker compose up -d qdrant
```

### tree-sitter unavailable

```bash
python3 -m pip install -r requirements-dev.txt
python3 -c 'import tree_sitter, tree_sitter_language_pack'
```

### OpenCode configuration reports invalid paths

```bash
./scripts/setup.sh
bun run tools/validate-config.ts
```

The generated configuration should use the current repository root and valid source paths.

### Health fails while tests pass

This can be expected. `make test` is designed to run deterministic local tests without requiring external services, while `make health` validates the configured runtime and real service connectivity.

## Documentation map

| Document | Responsibility |
|---|---|
| `README.md` | Overview and quickstart |
| `INSTALL.md` | Installation and environment configuration |
| `ARCHITECTURE.md` | Architecture and component responsibilities |
| `TESTING.md` | Tests, CI, coverage, and troubleshooting |
| `AGENTS.md` | Agent/development rules |
| Component READMEs | Subsystem-specific implementation details |

If this document conflicts with `setup.sh`, the installer behavior is authoritative.
