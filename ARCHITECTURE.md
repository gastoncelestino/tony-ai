# Tony-AI - ARQUITECTURA
## Patrón de memoria: archivo "SQLite compartido"
El diseño central de Tony-AI es que **cada servicio de memoria tiene un servidor MCP (Python) y un plugin (Bun) que comparten el mismo archivo SQLite**:
```
┌─────────────────────────┐    ┌─────────────────────────┐
│  local-memory/server.py │    │   plugins/tonymem.ts    │
│  (MCP server, 8 tools)  │    │  (OpenCode hooks)       │
│                         │    │                         │
│  SQLite: memory.db      │◄──►│  bun:sqlite (WAL mode)  │
│  observations table     │    │  same file, same schema │
└─────────────────────────┘    └─────────────────────────┘

┌─────────────────────────┐    ┌─────────────────────────┐
│  judgment-memory/       │    │  plugins/judgment-      │
│  ledger.py + server.py  │    │  memory.ts + qdrant.ts  │
│  (MCP server, 4 tools)  │    │  (OpenCode hooks)       │
│                         │    │                         │
│  SQLite: judgment-      │◄──►│  bun:sqlite (WAL mode)  │
│  memory.db              │    │  same file, same schema │
│  judgments table        │    │                         │
│                         │    │  HTTP → Qdrant/Ollama   │
│  Qdrant: jdmem_{proj}   │◄──►│  (via plugins/qdrant.ts)│
└─────────────────────────┘    └─────────────────────────┘
```
Este patrón permite un acceso directo al archivo SQLite en modo **WAL**, que es el modo de concurrencia que SQLite está diseñado para soportar: **un escritor a la vez, lectores nunca bloquean**.

## Tres conceptos clave:
1. **Judgment Day no corre en paralelo con revisión 4R.**  
   Por defecto, después de la implementación corre la revisión 4R ordinaria (`review-risk/readability/reliability/resilience` + `review-refuter`). Judgment Day (dos jueces ciegos, `jd-judge-a`/`jd-judge-b`) solo se activa explícitamente — nunca ambos a la vez.

2. **TonyMem, Code Indexer/Qdrant y DCP trabajan en cada fase.**  
   Se consultan y escriben durante cada fase (contexto previo antes de arrancar, guardado de decisiones al terminar, poda de contexto continua). No hay una etapa "leer memoria" al final del pipeline.

3. **Judgment Day tiene memoria propia.**  
   Antes de lanzar a los jueces, se llama `jd_recall` (¿ya vimos un problema parecido?). Cuando la lineage llega a un estado terminal, el orquestador llama `jd_record`, que persiste en un ledger SQLite propio (`judgment-memory/ledger.py`) y lo embebe/indexa en Qdrant (colección `jdmem_{project}`, separada del Code Indexer). Ver `judgment-memory/README.md`.

## Componentes

## Servicios de contexto
- **TonyMem** — Memoria persistente para decisiones, hallazgos y compartición de contexto entre sesiones.
- **Code Indexer + Qdrant** — Búsqueda semántica sobre el código usando embeddings locales.
- **Poda de Contexto Dinámica (DCP)** — Gestión automática de la ventana de contexto.

## Judgment Day
Cuando se activa explícitamente (por keywords como "juzgar" o "dual review"), ejecuta dos jueces de IA independientes:
- `jd-judge-a` (DeepSeek-R1 14B)
- `jd-judge-b` (Qwen3-Coder 30B) — deliberadamente distinto de `jd-judge-a` para verdadera corroboración

Antes de juzgar, `jd_recall` busca juicios similares anteriores. Después de completar, `jd_record` persiste el veredicto.

## Estructura del proyecto
```
tony-ai/
├── README.md                          # este archivo
├── opencode.json                      # mcp.tonymem/code-index/judgment-memory + Model Router
├── AGENTS.md                          # Reglas + Idioma + Instrucciones + TonyMem + Code Indexer
├── config/
│   └── tony-memory.yaml               # referencia documentada de env vars
├── docker/
│   ├── docker-compose.yml             # Ollama + Qdrant (backing services)
│   ├── docker-compose.gpu.yml         # override opcional, passthrough NVIDIA
│   ├── .env.example
│   └── README.md                      # notas específicas NixOS
├── Makefile                           # wrappers de conveniencia sobre tests
├── plugins/
│   ├── tonymem.ts                     # memoria local SQLite
│   ├── qdrant.ts                      # cliente REST Qdrant + Ollama (TS)
│   └── judgment-memory.ts             # bridge: recall antes de JD, captura después
├── local-memory/                      # TonyMem — MCP server (8 tools)
│   ├── server.py
│   └── README.md
├── code-index/                        # Code Indexer + Qdrant — MCP server (3 tools)
│   ├── core.py
│   ├── server.py
│   ├── test_core.py                   # regression test (mock Ollama/Qdrant)
│   └── README.md
├── judgment-memory/                   # Judgment Day <-> TonyMem bridge
│   ├── ledger.py                      # SQLite ledger + normalize + embed + Qdrant
│   ├── server.py                      # jd_recall / jd_record / jd_history / jd_stats
│   ├── schema.json                    # shape de un judgment record
│   ├── test_ledger.py                 # regression test (mock Ollama/Qdrant)
│   ├── test_hooks.ts                  # test harness para hooks de plugin
│   ├── __mocks__/                     # mocks para tests
│   │   ├── opencode-plugin.ts         # mock del Plugin context + eventos
│   │   └── http-mock.ts               # mock HTTP para Ollama/Qdrant
│   ├── scripts/
│   │   └── verify-qdrant.ts           # smoke test del cliente TS real
│   └── README.md
├── commands/
│   ├── memory-search.md               # /memory-search — TonyMem + judgment-memory
│   ├── memory-stats.md                # /memory-stats
│   └── judgment-history.md            # /judgment-history — solo SQLite
├── .opencode/
│   └── dcp.jsonc                      # config de DCP (plugin externo)
└── skills/
    ├── judgment-day/SKILL.md          # +paso de recall/record
    └── _shared/
        └── review-ledger-contract.md  
```

## Comandos
|			Comando				|			Descripción								|		Fuente			|  Offline 	|
|-------------------------------|---------------------------------------------------|-----------------------|-----------|
|/sdd-init						|Inicializar contexto SDD							|SQLite + config		|	 ✅		|
|/sdd-explore <task>			|Investigar una idea								|Sub-agente explore		| 	 ❌		|
|/sdd-status [change]			|Ver estado del cambio actual						|Artifact store			|  	 ✅		|
|/sdd-apply	[change]			|Implementar tareas									|Sub-agente writer		|	 ❌		|
|/sdd-verify	[change]		|Validar implementación								|Sub-agente verify		|	 ❌		|
|/sdd-archive	[change]		|Cerrar un cambio									|SQLite/JSON			|	 ✅		|
|/sdd-new "feature"				|Nuevo feature con SDD completo						|Sub-agentes			|	 ❌		|
|/sdd-tasks						|Ver plan de trabajo actual							|Artifact store			|	 ✅		|
|/sdd-ff						|Fast-forward propuesta → tareas					|Sub-agentes planning	|    ❌		|
|/memory-search "query"			|Búsqueda semántica en TonyMem + Judgment Memory	|SQLite + Qdrant		| ✅	❌	|
|/memory-stats					|Estadísticas de uso de memoria						|SQLite					|	 ✅		|
|/mem_save_prompt				|Hook interno de tonymem.ts							|TonyMem				|	 ✅		|
|/judgment-history [project]	|Ver historial de juicios							|SQLite ledger			|	 ✅		|
|juzgar esto: "feature"			|Activar Judgment Day (revisión adversarial)		|2 jueces + memoria		|	 ❌		|

💡 Todo funciona offline excepto `/sdd-explore, /sdd-apply, /sdd-verify, /sdd-new, /sdd-ff, /memory-search y /jd_recall`.

## Persistencia de Prompts
Hook chat.message → auto-guarda con type='prompt-capture'
Incluido en mem_context por defecto
Excluido de mem_search (bookkeeping)
Filtrar explícitamente: mem_search(query="...", type='prompt-capture')

## Variables de entorno

| Variable 						| Propósito 								| Valor por defecto 					| Usado por 							|
|-------------------------------|-------------------------------------------|---------------------------------------|---------------------------------------|
| `TONY_OLLAMA_URL` 			| Endpoint de Ollama 						| `http://localhost:11434` 				| Todos los servicios de embeddings 	|
| `TONY_QDRANT_URL` 			| Endpoint de Qdrant 						| `http://localhost:6333` 				| Code Indexer, Judgment Memory 		|
| `TONY_EMBED_MODEL` 			| Override del modelo de embeddings 		| `bge-m3` / `nomic-embed-text` 		| Por servicio de embeddings 			|
| `LOCAL_MEMORY_DB` 			| Archivo SQLite para TonyMem 				| `{cwd}/.tonymem/memory.db` 			| TonyMem 								|
| `JUDGMENT_MEMORY_DB` 			| Archivo SQLite para juicios 				| `{cwd}/.tonymem/judgment-memory.db` 	| Judgment Memory 						|
| `TONY_RECALL_SCORE_THRESHOLD` | Score mínimo para superficie de recall	| `0.5` 								| Filtrado de recall de Judgment Memory |

Por defecto, `code-index/` usa `bge-m3` para embeddings de código, mientras que `judgment-memory/` usa `nomic-embed-text` para tareas más cortas de recuperación en lenguaje natural.

## Modelos locales

| Rol 				| Modelo 					| Agentes 																												|
|-------------------|---------------------------|-----------------------------------------------------------------------------------------------------------------------|
| Planificación 	| `ollama/qwen3-coder:30b` 	| `tony-orchestrator`, `sdd-explore`, `sdd-propose`, `sdd-design`, `sdd-spec`, `sdd-tasks`, `sdd-init`, `sdd-onboard` 	|
| Implementación 	| `ollama/omnicoder:9b` 	| `sdd-apply` 																											|
| Revisión 			| `ollama/deepseek-r1:14b` 	| `sdd-verify`, `review-*` (5), `jd-judge-a` 																			|
| Revisión (juez B) | `ollama/qwen3-coder:30b` 	| `jd-judge-b` — deliberadamente distinto de `jd-judge-a` 																|
| Ejecución 		| `ollama/ornith:9b` 		| `sdd-archive`, `jd-fix-agent` 																						|

## Cómo lo utilizo?
```bash
/sdd-init — inicializar el entorno
```
💡 Tip: La primera vez que uses /sdd-init, vas a necesitar contestar unas preguntas sobre cómo querés trabajar (modo interactivo vs automático, dónde guardar las specs, etc.).


```bash
/sdd-new "mejorar login" — crear un nuevo cambio
/sdd-explore – si necesitás profundizar algo
/sdd-tasks – para ver el plan de trabajo
/sdd-apply – para implementar una fase
/sdd-verify – para evaluar resultados
/sdd-archive – para cerrar y archivar un cambio
```

```bash
/memory-search "manejo de errores HTTP"
```
✅ Combina búsquedas en TonyMem (decisiones, arquitectura, bugs, patrones) + judgment-memory (lecciones de revisiones anteriores)  
✅ Usa mem_search (de observation store) y jd_recall (de vector DB)  
✅ Es una interfaz unificada para recuperar contexto histórico  

```bash
/judgment-history — ver resultados de revisiones anteriores 
```
✅ Lee directamente del SQLite ledger (`judgment-memory.db`). Lista los últimos juicios de Judgment Day para el proyecto actual.  
✅ No depende de Qdrant/Ollama (offline-first)  
✅ Útil para revisar decisiones anteriores sin embedding  

```bash
/memory-stats
```
✅ Muestra métricas de uso de memoria (número de observaciones, tipos más comunes, última actividad)  
✅ Filtrado por proyecto  

```bash
/mem_save_prompt 
```
✅ Llamado por el hook `chat.message` en `tonymem.ts`  
✅ Captura prompts crudos con type='prompt-capture'  
✅ Excluido de búsquedas por defecto (bookkeeping)  
✅ Se puede filtrar explícitamente si necesitás revisar prompts  


Estas entradas se usan para `mem_context` (recuperar el contexto de la sesión actual) pero  **se excluyen por defecto de `mem_search`** 
— no son decisiones ni descubrimientos, son bookkeeping interno.  
Si necesitás buscar prompts, filtrá explícitamente por `type='prompt-capture'`. — no son decisiones ni descubrimientos, son bookkeeping interno.


## TonyMem - Memoria Persistente
```bash
# Cada decisión/descubrimiento se guarda en SQLite
mem_save(task="manejo retry HTTP", observation="usar exponential backoff")

# Luego se recupera en nuevas conversaciones
mem_search("retry HTTP") → encuentra la decisión guardada
```
Aprende de: Decisiones arquitectónicas, bugs resueltos, patrones de código

## Judgment Memory - Lecciones de Revisiones
```bash
# Después de cada Judgment Day:
jd_record(task="validar JWT", final="approve", lesson="siempre verificar signature expiration")
# Futuras tareas similares recuerdan esta lección
```
Aprende de: Errores de review, mejores prácticas validadas

## Code Indexer - Conocimiento del Codebase
- Indexa incrementalmente (solo cambios)
- Embeddings semánticos con bge-m3
- Búsquedas como "cómo se maneja la autenticación" te encuentran código relevante

Aprende de: Crecimiento del codebase, patrones emergentes

## Hooks de OpenCode (tonymem.ts)
```bash
// Hook que captura automáticamente lo que haces
"chat.message" → mem_save_prompt() // guarda prompts
"task.execute.after" → guarda discoveries importantes
```

## Cómo funciona el aprendizaje en práctica:
```bash
Usuario: "Implementa login con refresh token"
```
```bash
Tony-AI:
```
1. mem_search() → encuentra decisión previa sobre JWT
2. code_search() → encuentra cómo funciona auth actual
3. jd_recall() → recuerda lección sobre token expiration
4. Implementa → tony_mem guarda la nueva decisión
5. juzgar esto → dos jueces review + lesson guardada


## Beneficios concretos:
1. Primera tarea: Configuras todo desde cero  
2. Segunda tarea: Sistema te sugiere patrones similares  
3. Tercera tarea: Ya tiene memoria de errores evitados  
4. Tu sistema es progresivamente más útil con el uso. No es ML tradicional, es memoria semántica operacional.  


## Principios de diseño
- **Local-first**: el almacenamiento es SQLite y está pensado para quedarse en tu máquina.
- **Dependency-light**: los servidores en Python usan solo stdlib, deliberadamente.
- **Separación de responsabilidades**:
	- `local-memory/` almacena observaciones de texto libre y estado de sesión.
	- `code-index/` busca código real semánticamente.
	- `judgment-memory/`/ almacena resultados normalizados de flujos de revisión completados.
**Indexado incremental**: el indexador de código saltea archivos sin cambios y limpia los borrados del índice.


## Notas
- `AGENTS.md` define convenciones de orquestación, reglas de respuesta y patrones de uso de memoria/indexación esperados por el ecosistema de agentes circundante.
- `opencode.json` está presente en la raíz del repositorio, indicando que el repo está pensado para integrarse con una configuración de MCP/tooling compatible con OpenCode.
El setup de Docker es solo para **Ollama** y **Qdrant**; los servidores MCP en Python están pensados para correr directamente sobre stdio en lugar de dentro de contenedores.