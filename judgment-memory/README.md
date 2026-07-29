# judgment-memory

Judgment Day <-> TonyMem bridge. Persists the outcome of every Judgment Day
lineage (`skills/judgment-day/SKILL.md`) so future reviews of a similar
target start from "we saw this before" instead of a blank slate.

Not a replacement for `local-memory/` (free-text TonyMem observations) or
`code-index/` (semantic code search) — a third, narrower store for one
specific shape of record: a finished judgment.

## Pipeline

```
Decision (judge_a/judge_b verdicts + Agreement Engine outcome)
  -> Normalize (ledger.py:normalize — flatten to one embeddable passage)
  -> Embedding (Ollama /api/embed, same contract as code-index/core.py)
  -> Qdrant (collection jdmem_{project}, separate from code-index's collections)
  -> Future Recall (jd_recall — cosine search against new task descriptions)
```

## Files

| File | Role |
|---|---|
| `ledger.py` | Core library + CLI. SQLite ledger (`judgment-memory.db`, WAL) is the durable source of truth; embedding/Qdrant indexing is best-effort on top of it. |
| `server.py` | MCP tool server (stdio, JSON-RPC, zero deps) exposing `jd_recall` / `jd_record` / `jd_history` / `jd_stats`. |
| `schema.json` | JSON Schema for one judgment record — what `jd_record` expects and `jd_recall`/`jd_history` return. |
| `test_ledger.py` | Regression test against an in-process mock of Ollama/Qdrant — covers the full happy path (embed + upsert + search), upsert-not-duplicate, stats aggregation, validation, and graceful degradation. Run with `python3 test_ledger.py`, no real Ollama/Qdrant needed. |

## Tools (via MCP)

- **jd_recall(task, project?, limit?)** — semantic search for past judgments similar to a new task. Call before launching Judgment Day's judges. Degrades gracefully (`available: false`) if Ollama/Qdrant aren't reachable — never blocks Judgment Day from running.
- **jd_record(execution_id, task, final, ...)** — persist a finished judgment: ledger write + normalize + embed + Qdrant upsert. Call once a lineage reaches a terminal state. Only the parent orchestrator calls this, same rule as `skills/_shared/review-ledger-contract.md`.
- **jd_history(project?, limit?, all_projects?)** — recent judgments, SQLite-only, always available.
- **jd_stats(project?)** — total judgments, breakdown by outcome/agreement, contradiction rate.

## Storage

- **Ledger**: SQLite, one row per `(project, execution_id)`, upserted (re-recording the same execution_id updates in place). Same file both `ledger.py`/`server.py` (Python, via `sqlite3`) and `plugins/judgment-memory.ts` (Bun, via `bun:sqlite`) read/write — one schema, two clients, same pattern as `local-memory/server.py` <-> `plugins/tonymem.ts`.
- **Vectors**: Qdrant collection `jdmem_{project}` (see `plugins/qdrant.ts:collectionName`), point id deterministically derived from `(project, execution_id)` so re-indexing upserts instead of duplicating.

## Env vars

| Var | Default | Used by |
|---|---|---|
| `JUDGMENT_MEMORY_DB` | `./judgment-memory.db` (relative to this dir) | `ledger.py`, `server.py`, `plugins/judgment-memory.ts` |
| `TONY_OLLAMA_URL` | `http://localhost:11434` | embedding calls |
| `TONY_EMBED_MODEL` | `nomic-embed-text` | embedding model — short natural-language text, not code, so this differs from code-index's `bge-m3` default |
| `TONY_QDRANT_URL` | `http://localhost:6333` | vector store |

See `config/tony-memory.yaml` for the full documented reference.

## Testing

| Script | Covers | Needs real Ollama/Qdrant? |
|---|---|---|
| `test_ledger.py` | Full pipeline (mocked HTTP): record, recall, upsert-not-duplicate, stats, validation, graceful degradation | No — in-process mock |
| `scripts/verify-qdrant.ts` | The TS/Bun HTTP client (`plugins/qdrant.ts`) end-to-end: embed, ensureCollection, upsert, search, semanticSearch, degradation | **Yes** — this is the one that closes the "never ran against the real thing" gap. Run it once after install, before trusting `plugins/judgment-memory.ts` inside a real session. |

```bash
python3 test_ledger.py                          # no services needed
bun run scripts/verify-qdrant.ts                 # needs ollama serve + qdrant up
```

`verify-qdrant.ts` uses a throwaway project (`__verify_qdrant_ts__`) and deletes its Qdrant collection when it finishes, pass or fail — safe to run against your real local Ollama/Qdrant, it never touches real judgment data.

## CLI (no MCP client needed)

```bash
python3 ledger.py record --file record.json     # validate + save + index
python3 ledger.py recall --task "optimize query" --project default
python3 ledger.py history --project default --limit 10
python3 ledger.py stats --project default
```

## Local dependencies

Same as `code-index/`: [Ollama](https://ollama.com) running locally with
the embedding model pulled (`ollama pull nomic-embed-text`), and
[Qdrant](https://qdrant.tech) reachable (`docker run -p 6333:6333
qdrant/qdrant`). Neither is required for the SQLite ledger itself —
`jd_record`/`jd_history`/`jd_stats` all work without them; only semantic
`jd_recall` needs both up.
