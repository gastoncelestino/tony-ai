# TonyMem (local-memory)
Memoria local persistente para el orquestador SDD de OpenCode —
observaciones con `topic_key` que hacen *upsert*, scoping por proyecto,
búsqueda full-text, expuesto como tools MCP. 

- **Storage**: SQLite local (memory.db) con tabla observations
- **MCP Server (local-memory/server.py)**: 8 herramientas (mem_save, mem_search, mem_get_observation, mem_update, mem_context, mem_session_summary, mem_suggest_topic_key, mem_save_prompt)
- **Plugin de OpenCode (plugins/tonymem.ts)**: Hooks que auto-guardan sesiones y capturan prompts
- **Arquitectura**: Comparte el archivo SQLite directamente (modo WAL) entre el MCP server y el plugin
- **Uso**: Recordar decisiones, bugs, patrones, configuraciones entre sesiones
- **100% tuyo**: un solo archivo Python (`server.py`, stdlib puro — nada de `pip install`) + un `memory.db` de SQLite que se crea solo.
- **100% local**: no hay servidor, no hay cloud sync, no hay telemetría. Todo vive en tu disco.
- **Sin instalador**: copiás la carpeta `local-memory/` donde quieras y apuntás OpenCode a `server.py`. Listo.

## Requisitos
Solo Python 3.10+ (ya lo tenés si usás NixOS/WSL). No hace falta `pip`
ni ningún paquete adicional — `sqlite3` viene en la librería estándar.

## Instalación (copiar y usar)
1. Copiá la carpeta `local-memory/` a donde prefieras, por ejemplo:
   ```
   ~/tools/local-memory/
   ```
2. Abrí (o creá) `~/.config/opencode/opencode.json` y agregá:

   ```jsonc
   {
     "$schema": "https://opencode.ai/config.json",
     "mcp": {
       "tonymem": {
         "type": "local",
         "command": ["python3", "/home/gas/tools/local-memory/server.py"],
         "enabled": true
       }
     }
   }
   ```

   Reemplazá la ruta por la real. Si querés una base de datos distinta
   por proyecto en vez de una global, agregá:

   ```jsonc
   "environment": { "LOCAL_MEMORY_DB": "{cwd}/.local-memory/memory.db" }
   ```

3. Reiniciá OpenCode. Verificá con `opencode mcp list` que `tonymem`
   aparece conectado.

Eso es todo — no hay paso de build, no hay migración, no hay setup wizard.

## Tools que expone
| Tool | Uso |
|------|-----|
| `mem_save` | Guarda contenido. Si pasás `topic_key`, hace upsert por `(project, topic_key)` — volver a guardar actualiza, no duplica. |
| `mem_search` | Búsqueda full-text (SQLite FTS5) con snippets truncados. Filtros: `project`, `type`, `scope`, `all_projects`, `match_mode` (`all`/`any`). Excluye por defecto `type='prompt-capture'`. |
| `mem_get_observation` | Trae el contenido completo por `id` (los resultados de `mem_search` vienen truncados a propósito). |
| `mem_update` | Actualiza título/contenido/tipo de una observación existente por `id`. |
| `mem_context` | Lookup rápido: último `session-summary` del proyecto + observaciones recientes. Sin FTS, más barato que `mem_search`. |
| `mem_session_summary` | Guarda el cierre de sesión (Goal/Instructions/Discoveries/Accomplished/Next Steps/Relevant Files). Upsert por `(project, session_id)`. |
| `mem_suggest_topic_key` | Sugiere un `topic_key` slug sin colisiones para un título dado. No guarda nada. |
| `mem_save_prompt` | Guarda el último prompt crudo del usuario por sesión (`type='prompt-capture'`), separado del resto para no ensuciar `mem_search`. |

Esto cubre exactamente lo que el AGENTS.md del orquestador espera:
`mem_search(query, project)` → `mem_get_observation(id)` como patrón de
dos pasos, y `mem_save` con `topic_key` siguiendo la convención
`sdd/{change-name}/{artifact-type}` (proposal, spec, design, tasks,
apply-progress, verify-report, archive-report).

## Cómo probarlo sin OpenCode
```bash
cd local-memory
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"mem_save","arguments":{"title":"Test","content":"hola mundo","topic_key":"test/1","project":"demo"}}}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"mem_search","arguments":{"query":"hola","project":"demo"}}}' \
  | python3 server.py
```

## Diseño deliberadamente mínimo
`tonymem` implementa **solo el contrato que el orquestador SDD realmente usa** sin:
- servidor HTTP, sync, cloud, ni cuentas
- dependencias externas o build step (Go, npm, etc.)
- telemetría de ningún tipo

Si en algún momento querés más (por ejemplo un `mem_context` con las
últimas N observaciones, o pines), se agregan como funciones nuevas en
`TOOLS` siguiendo el mismo patrón — el archivo es intencionalmente
chico para que se pueda leer entero en un par de minutos.

## Dónde vive la base de datos
Por defecto: junto a `server.py`, como `memory.db` (+ archivos WAL de
SQLite). Se puede mover con la variable de entorno `LOCAL_MEMORY_DB`.
Podés respaldarla como cualquier archivo (`cp memory.db backup.db`) o
versionarla con `sqlite3 memory.db .dump > memory.sql`.
