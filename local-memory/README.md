# TonyMem

Memoria persistente local para Tony-AI, integrada con OpenCode 1.18.22 mediante el transporte MCP local.

## Arquitectura

OpenCode inicia `local-memory/server.py` como un MCP server por workspace. El servidor recibe JSON-RPC por stdin/stdout y guarda memoria en SQLite con WAL y FTS5.

Por defecto la base queda en:

```text
<workspace>/.tonymem/memory.db
```

También se puede sobrescribir con `LOCAL_MEMORY_DB`.

## Herramientas

- `mem_save`: guarda o actualiza memoria mediante `topic_key`.
- `mem_search`: búsqueda full-text con filtros por proyecto, tipo y scope.
- `mem_get_observation`: obtiene el contenido completo por id.
- `mem_update`: modifica título, contenido o tipo.
- `mem_context`: recupera contexto reciente y soporta paginación.
- `mem_session_summary`: guarda un resumen de sesión por `session_id`.
- `mem_suggest_topic_key`: genera una clave estable sin guardar datos.
- `mem_save_prompt`: conserva el último prompt de una sesión.
- `mem_review`: gestiona `active`, `proven` y `needs_review`.

## OpenCode 1.18.22

La configuración usa el soporte MCP local nativo de OpenCode:

```jsonc
"tonymem": {
  "enabled": true,
  "type": "local",
  "command": ["python3", "local-memory/server.py"],
  "timeout": 5000
}
```

OpenCode ejecuta los MCP locales con el workspace como `cwd`; por eso TonyMem usa `os.getcwd()` para resolver la base por proyecto.

## Principio de memoria

TonyMem no reemplaza la evidencia del repositorio. Una memoria recuperada sirve como contexto previo, pero cualquier afirmación sobre el estado actual del código debe volver a validarse contra herramientas de OpenCode.

La integración automática de eventos del Execution Graph (sesiones, tareas, herramientas y evidencia) se implementará separadamente en el plugin de Tony-AI. El MCP server se mantiene deliberadamente independiente de OpenCode.
