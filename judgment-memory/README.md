# judgment-memory

Puente entre Judgment Day y TonyMem. Persiste el resultado de cada lineage de Judgment Day (`skills/judgment-day/SKILL.md`) para que revisiones futuras de un target similar arranquen desde "ya vimos esto" en vez de una hoja en blanco.

No reemplaza a `local-memory/` (observaciones free-text de TonyMem) ni a `code-index/` (búsqueda semántica de código) — es un tercer store, más chico y específico, para una forma de registro muy puntual: un juicio terminado.

## Pipeline

```
Decisión (veredictos de judge_a/judge_b + resultado del Agreement Engine)
  -> Normalizar (ledger.py:normalize — aplana a un pasaje embebible)
  -> Embedding (Ollama /api/embed, mismo contrato que code-index/core.py)
  -> Qdrant (colección jdmem_{project}, separada de las colecciones de code-index)
  -> Recall futuro (jd_recall — búsqueda por cosine contra descripciones de nuevas tareas)
```

## Archivos

| Archivo | Rol |
|---|---|
| `ledger.py` | Librería core + CLI. El ledger SQLite (`judgment-memory.db`, WAL) es la fuente de verdad durable; el embedding/indexado en Qdrant es best-effort encima. |
| `server.py` | Servidor MCP de tools (stdio, JSON-RPC, cero deps) que expone `jd_recall` / `jd_record` / `jd_history` / `jd_stats`. |
| `schema.json` | JSON Schema para un registro de juicio — lo que `jd_record` espera y lo que `jd_recall`/`jd_history` devuelven. |
| `test_ledger.py` | Test de regresión contra un mock en-proceso de Ollama/Qdrant — cubre el camino feliz completo (embed + upsert + search), upsert-no-duplica, agregación de stats, validación y degradación gracefully. Correr con `python3 test_ledger.py`, no necesitás Ollama/Qdrant reales. |

## Tools (vía MCP)

- **jd_recall(task, project?, limit?)** — búsqueda semántica de juicios pasados similares a una tarea nueva. Llamalo antes de arrancar los jueces de Judgment Day. Degrada gracefully (`available: false`) si Ollama/Qdrant no están reachables — nunca bloquea que Judgment Day corra.
- **jd_record(execution_id, task, final, ...)** — persistí un juicio terminado: escritura en ledger + normalizar + embed + upsert en Qdrant. Llamalo una vez que un lineage llega a estado terminal. Solo el orquestador padre llama a este, misma regla que `skills/_shared/review-ledger-contract.md`.
- **jd_history(project?, limit?, all_projects?)** — juicios recientes, solo SQLite, siempre disponible.
- **jd_stats(project?)** — total de juicios, breakdown por outcome/agreement, tasa de contradicciones.

## Storage

- **Ledger**: SQLite, una fila por `(project, execution_id)`, upserted (re-grabar el mismo execution_id actualiza in-place). Mismo archivo leen/escriben `ledger.py`/`server.py` (Python, vía `sqlite3`) y `plugins/judgment-memory.ts` (Bun, vía `bun:sqlite`) — un schema, dos clientes, mismo patrón que `local-memory/server.py` <-> `plugins/tonymem.ts`.
- **Vectores**: colección Qdrant `jdmem_{project}` (ver `plugins/qdrant.ts:collectionName`), point id derivado deterministicamente de `(project, execution_id)` así el re-indexado hace upsert en vez de duplicar.

## Variables de entorno

| Variable | Default | Usado por |
|---|---|---|
| `JUDGMENT_MEMORY_DB` | `./judgment-memory.db` (relativo a este directorio) | `ledger.py`, `server.py`, `plugins/judgment-memory.ts` |
| `TONY_OLLAMA_URL` | `http://localhost:11434` | llamadas de embedding |
| `TONY_EMBED_MODEL` | `nomic-embed-text` | modelo de embeddings — texto natural corto, no código, por eso difiere del default `bge-m3` de code-index |
| `TONY_QDRANT_URL` | `http://localhost:6333` | vector store |

Ver `config/tony-memory.yaml` para la referencia completa documentada.

## Testing

| Script | Cubre | Necesita Ollama/Qdrant reales? |
|---|---|---|
| `test_ledger.py` | Pipeline completo (HTTP mockeado): record, recall, upsert-no-duplica, stats, validación, degradación gracefully | No — mock en-proceso |
| `tests/judgment_qdrant.test.ts` | Cliente HTTP TS/Bun (`plugins/qdrant.ts`) end-to-end: embed, ensureCollection, upsert, search, semanticSearch, degradación | **Sí** — este es el que cierra el gap de "nunca corrió contra algo real". Correr una vez después de instalar, antes de confiar en `plugins/judgment-memory.ts` en una sesión real. |

```bash
python3 test_ledger.py                          # no necesita servicios
bun run tests/judgment_qdrant.test.ts           # necesita ollama serve + qdrant arriba
```

`judgment_qdrant.test.ts` usa un proyecto descartable (`__judgment_qdrant.test__`) y borra su colección de Qdrant cuando termina, pase o falle — seguro correrlo contra tu Ollama/Qdrant local real, nunca toca datos de juicios reales.

## CLI (sin cliente MCP)

```bash
python3 ledger.py record --file record.json     # validar + guardar + indexar
python3 ledger.py recall --task "optimizar query" --project default
python3 ledger.py history --project default --limit 10
python3 ledger.py stats --project default
```

## Dependencias locales

Igual que `code-index/`: [Ollama](https://ollama.com) corriendo localmente con el modelo de embeddings descargado (`ollama pull nomic-embed-text`), y [Qdrant](https://qdrant.tech) reachable (`docker run -p 6333:6333 qdrant/qdrant`). Ninguno de los dos es requerido para el ledger SQLite en sí — `jd_record`/`jd_history`/`jd_stats` funcionan sin ellos; solo el `jd_recall` semántico necesita ambos arriba.
