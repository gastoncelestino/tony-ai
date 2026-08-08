# Tony-AI Code Indexer (+ Qdrant)

Búsqueda semántica (RAG) sobre tu codebase. Complementa a TonyMem, no lo reemplaza: TonyMem recuerda decisiones y conversaciones; esto busca en el código real por significado, no por string exacto.

Cero dependencias nuevas de Python — `core.py` habla con Ollama y Qdrant por HTTP plano (`urllib`), mismo espíritu stdlib-only que `local-memory/`.

## Requisitos

1. **Qdrant** corriendo en algún lado (local, WSL, o el mismo servidor donde ya tenés otros servicios):
   ```bash
   docker run -d --name qdrant -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
   ```

2. **Ollama** con el modelo de embeddings ya descargado (usás `bge-m3` en tu stack actual, así que probablemente ya lo tenés):
   ```bash
   ollama pull bge-m3
   ```

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `TONY_OLLAMA_URL` | `http://localhost:11434` | Endpoint de Ollama |
| `TONY_EMBED_MODEL` | `bge-m3` | Modelo de embeddings |
| `TONY_QDRANT_URL` | `http://localhost:6333` | Endpoint de Qdrant |
| `TONY_INDEX_ROOT` | cwd | Raíz del repo a indexar (solo lo usa `server.py`) |
| `TONY_INDEX_MAX_CHUNK_LINES` | `260` | Tamaño máximo de chunk |
| `TONY_INDEX_MIN_CHUNK_LINES` | `8` | Chunks más chicos que esto se fusionan con el siguiente |
| `TONY_INDEX_CHUNK_OVERLAP` | `30` | Overlap entre chunks cuando cae a ventana fija |

## Uso por CLI (recomendado para el primer índice completo de un repo grande)

```bash
cd code-index
python3 core.py index --path /ruta/al/repo --project mi-proyecto
python3 core.py search --query "manejo de reintentos HTTP" --project mi-proyecto
python3 core.py status --path /ruta/al/repo --project mi-proyecto
```

`index` es incremental: si corrés el mismo comando de nuevo, los archivos sin cambios (por hash de contenido) se saltan; los que cambiaron se re-chunkean y re-embeben (borrando los chunks viejos de Qdrant que ya no corresponden); los archivos borrados del disco se limpian del índice también. El estado de qué se indexó vive en `.codeindex/manifest.db` (sqlite) dentro del repo indexado — agregalo a tu `.gitignore`.

## Uso desde el agente (MCP)

Una vez registrado en `opencode.json` (ya viene hecho en este proyecto, ver `INSTALL.md`), el agente tiene 3 tools:

- `code_index_status` — chequea si el repo está indexado
- `code_reindex` — indexa/reindexa incrementalmente (llamalo antes de confiar en `code_search` si no estás seguro de que el índice esté al día)
- `code_search` — búsqueda semántica

## Cómo chunkea

No usa tree-sitter ni ningún parser AST — sería una dependencia más y más mantenimiento del que vale la pena para el primer corte. En cambio, usa regex para detectar el inicio de funciones/clases/procedures por lenguaje (`def`/`class` en Python, `function`/`class`/`interface` en TS/JS, `CREATE OR REPLACE PROCEDURE/FUNCTION/PACKAGE` en SQL/PL-SQL, `func` en Go, etc. — ver `BOUNDARY_PATTERNS` en `core.py`) y corta ahí. Si un archivo no tiene un lenguaje reconocido, o el patrón no encuentra un número razonable de límites, cae a ventanas de tamaño fijo con overlap. Cubre bien Python, TS/JS, PL/SQL — que es la mayoría de tu stack — sin la complejidad de un parser real.

## Test

```bash
python3 test_core.py
```

Corre el pipeline completo (chunking → embeddings → Qdrant upsert → reindex incremental → búsqueda → status) contra un mock HTTP en memoria de Ollama/Qdrant, sin necesitar ninguno de los dos servicios corriendo. Últimas corridas: 4/4 escenarios (índice inicial, no-op en re-run, update incremental al cambiar un archivo, limpieza al borrar un archivo) pasando.

## Limitaciones conocidas (a propósito, no reinventadas de más)

- El chunking por regex no es perfecto — puede cortar mal código muy denso sin blank lines entre funciones. Si en el futuro esto molesta, la mejora natural es tree-sitter, pero no lo agregué preventivamente.
- `code_reindex` es síncrono y bloquea el turno del agente mientras corre. Para el primer índice completo de un repo grande, usá el CLI en vez del tool MCP.
- No hay borrado de colección completa expuesto como tool (a propósito — es una operación destructiva; si necesitás resetear, borrá la colección directamente en Qdrant o `rm -rf .codeindex/`).
