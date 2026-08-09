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

### Servicios de contexto
- **TonyMem** — Memoria persistente para decisiones, hallazgos y compartición de contexto entre sesiones. Servidor MCP Python (`local-memory/server.py`) + plugin OpenCode (`plugins/tonymem.ts`) comparten el mismo `memory.db` en modo WAL.
- **Code Indexer + Qdrant** — Búsqueda semántica sobre el código usando embeddings locales (`bge-m3`). Servidor MCP Python (`code-index/server.py`) con indexación incremental.
- **Poda de Contexto Dinámica (DCP)** — Gestión automática de la ventana de contexto (plugin externo en `.opencode/dcp.jsonc`).
- **Judgment Memory** — Puente entre Judgment Day y TonyMem. Persiste juicios en SQLite (`judgment-memory/ledger.py`) y los indexa en Qdrant (`jdmem_{project}`) para recall semántico.

### Protocolos compartidos
- **SDD Phase Common** (`skills/_shared/sdd-phase-common.md`) — Contrato de salida estructurado (Section D) que todas las fases SDD deben devolver: `status`, `executive_summary`, `artifacts`, `next_recommended`, `risks`, `skill_resolution`.
- **TonyMem Convention** (`skills/_shared/tonymem-convention.md`) — Topic keys, contratos de `mem_save`/`mem_get_observation`/`mem_search`, aislamiento por proyecto, manejo de concurrencia.
- **OpenSpec Convention** (`skills/_shared/openspec-convention.md`) — Directorios, paths y delta spec sections para artifacts en filesystem.
- **Skill Resolver** (`skills/_shared/skill-resolver.md`) — Protocolo de resolución de skills desde el registry.

### Prompts de fases SDD
Cada fase tiene su propio prompt en `prompts/sdd/`:
`sdd-explore` → `sdd-propose` → `sdd-spec` → `sdd-design` → `sdd-tasks` → `sdd-apply` → `sdd-verify` → `sdd-archive`
Más `sdd-init` (bootstrap) y `sdd-onboard` (walkthrough guiado).
Cuando se activa explícitamente (por keywords como "juzgar" o "dual review"), ejecuta dos jueces de IA independientes:
- `jd-judge-a` (DeepSeek-R1 14B)
- `jd-judge-b` (Qwen3-Coder 30B) — deliberadamente distinto de `jd-judge-a` para verdadera corroboración

Antes de juzgar, `jd_recall` busca juicios similares anteriores. Después de completar, `jd_record` persiste el veredicto.

## Estructura del proyecto
```
tony-ai/
├── README.md                          # Introducción y quickstart
├── opencode.json                      # Config de agentes, MCP servers, permisos
├── AGENTS.md                          # Reglas de orquestación, idioma, memoria
├── ARCHITECTURE.md                    # Documentación técnica para entender el proyecto
├── INSTALL.md                         # Guía de instalación detallada
├── Makefile                           # Wrappers de tests, bootstrap, health, docker
├── requirements.txt                   # Filosofía stdlib-only
├── requirements-optional.txt          # tree-sitter (opt-in)
│
├── config/
│   └── tony-memory.yaml               # Referencia documentada de env vars
│
├── docker/
│   ├── docker-compose.yml             # Ollama + Qdrant (backing services)
│   ├── docker-compose.gpu.yml         # Override opcional NVIDIA
│   ├── .env.example
│   └── README.md                      # Servicios de soporte en Linux
│
├── scripts/
│   ├── setup.sh                       # Bootstrap idempotente
│   └── health.sh                      # Verificación end-to-end
│
├── plugins/
│   ├── tonymem.ts                     # Hook OpenCode: auto-guardar sesiones + prompts
│   ├── qdrant.ts                      # Cliente REST Qdrant + Ollama (Bun)
│   └── judgment-memory.ts             # Bridge: recall antes de JD, captura después
│
├── prompts/
│   └── sdd/                           # Prompts de fases SDD (uno por fase)
│       ├── sdd-explore.md
│       ├── sdd-propose.md
│       ├── sdd-spec.md
│       ├── sdd-design.md
│       ├── sdd-tasks.md
│       ├── sdd-apply.md
│       ├── sdd-verify.md
│       ├── sdd-archive.md
│       ├── sdd-init.md
│       └── sdd-onboard.md
│
├── skills/
│   ├── _shared/                       # Protocolos comunes a todas las fases SDD
│   │   ├── SKILL.md
│   │   ├── sdd-phase-common.md        # Secciones A-E: skill loading, retrieval,
│   │   │                            # persistence, return envelope, review workload
│   │   ├── openspec-convention.md     # Directorios, paths, delta spec sections
│   │   ├── tonymem-convention.md      # Topic keys, mem_save/mem_search contracts
│   │   ├── sdd-status-contract.md     # Schema de structured status
│   │   ├── persistence-contract.md    # Contratos de persistencia por artifact store
│   │   ├── review-ledger-contract.md  # Contrato de review ledger para Judgment Day
│   │   └── skill-resolver.md          # Skill registry protocol
│   ├── sdd-explore/
│   ├── sdd-propose/
│   ├── sdd-spec/
│   ├── sdd-design/
│   ├── sdd-tasks/
│   ├── sdd-apply/
│   ├── sdd-verify/
│   ├── sdd-archive/
│   ├── sdd-init/
│   ├── sdd-onboard/
│   ├── judgment-day/
│   ├── chained-pr/
│   ├── branch-pr/
│   ├── work-unit-commits/
│   ├── comment-writer/
│   ├── issue-creation/
│   ├── go-testing/
│   ├── cognitive-doc-design/
│   └── skill-creator/
│
├── local-memory/                      # TonyMem — MCP server (8 tools)
│   ├── server.py
│   ├── test_server.py                 # Regression test (MCP framing, UPSERT, FTS)
│   └── README.md
│
├── code-index/                        # Code Indexer + Qdrant — MCP server (3 tools)
│   ├── core.py                        # Chunking, embeddings, Qdrant client (stdlib)
│   ├── server.py
│   ├── test_core.py                   # Regression test (mock HTTP, incremental)
│   └── README.md
│
├── judgment-memory/                   # Judgment Day <-> TonyMem bridge
│   ├── ledger.py                      # SQLite ledger + normalize + embed + Qdrant
│   ├── server.py                      # jd_recall / jd_record / jd_history / jd_stats
│   ├── schema.json                    # Shape de un judgment record
│   ├── test_ledger.py                 # Regression test (mock Ollama/Qdrant)
│   ├── test_hooks.ts                  # Test harness para hooks de plugin
│   ├── scripts/
│   │   └── verify-qdrant.ts           # Smoke test del cliente TS real
│   └── README.md
│
└── .opencode/
    └── dcp.jsonc                      # Config de DCP (plugin externo)
```

## Comandos
| Comando | Descripción | Fuente | Offline |
|---------|-------------|--------|---------|
| `/sdd-init` | Inicializar contexto SDD | SQLite + config | ✅ |
| `/sdd-new <change>` | Nuevo cambio con SDD completo | Sub-agentes planning | ❌ |
| `/sdd-explore <task>` | Investigar una idea | Sub-agente explore | ❌ |
| `/sdd-propose` | Crear propuesta PRD | Sub-agente propose | ❌ |
| `/sdd-spec` | Especificación técnica | Sub-agente spec | ❌ |
| `/sdd-design` | Diseño técnico | Sub-agente design | ❌ |
| `/sdd-tasks` | Generar plan de tareas | Sub-agente tasks | ❌ |
| `/sdd-apply [change]` | Implementar tareas | Sub-agente writer | ❌ |
| `/sdd-verify [change]` | Validar implementación | Sub-agente verify | ❌ |
| `/sdd-archive [change]` | Cerrar cambio y archivar | SQLite/JSON | ✅ |
| `/sdd-onboard` | Walkthrough guiado de SDD | Sub-agente onboard | ❌ |
| `/sdd-status [change]` | Ver estado del cambio | Artifact store | ✅ |
| `/sdd-continue [change]` | Ejecutar siguiente fase | Sub-agentes | ❌ |
| `/sdd-ff <name>` | Fast-forward: propuesta → tareas | Sub-agentes planning | ❌ |
| `/memory-search "query"` | Búsqueda semántica en TonyMem + Judgment Memory | SQLite + Qdrant | ✅ / ❌ |
| `/memory-stats` | Estadísticas de memoria | SQLite | ✅ |
| `/judgment-history [project]` | Ver historial de juicios | SQLite ledger | ✅ |
| `juzgar esto` | Activar Judgment Day | 2 jueces + memoria | ❌ |

💡 Todo funciona offline excepto los comandos que requieren sub-agentes (`/sdd-new`, `/sdd-explore`, `/sdd-propose`, `/sdd-spec`, `/sdd-design`, `/sdd-tasks`, `/sdd-apply`, `/sdd-verify`, `/sdd-onboard`, `/sdd-continue`, `/sdd-ff`, `juzgar esto`) y búsqueda semántica (`/memory-search` con Qdrant/Ollama).

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

| Rol | Modelo | Agentes |
|-----|--------|---------|
| Planificación | `ollama/qwen3-coder:30b` | `tony-orchestrator`, `sdd-explore`, `sdd-propose`, `sdd-design`, `sdd-spec`, `sdd-tasks`, `sdd-init`, `sdd-onboard` |
| Implementación | `ollama/omnicoder:9b` | `sdd-apply` |
| Revisión | `ollama/deepseek-r1:14b` | `sdd-verify`, `review-*` (5), `jd-judge-a` |
| Revisión (juez B) | `ollama/qwen3-coder:30b` | `jd-judge-b` — deliberadamente distinto de `jd-judge-a` |
| Ejecución | `ollama/ornith:9b` | `sdd-archive`, `jd-fix-agent` |

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

1. `/sdd-new` → delega `sdd-explore` + `sdd-propose` a sub-agentes
2. `mem_search()` → encuentra decisión previa sobre JWT
3. `code_search()` → encuentra cómo funciona auth actual
4. `jd_recall()` → recuerda lección sobre token expiration
5. `/sdd-tasks` → genera plan de implementación
6. `/sdd-apply` → implementa las tareas
7. `/sdd-verify` → valida contra specs
8. `/sdd-archive` → cierra el cambio, guarda `archive-report`
9. `juzgar esto` → dos jueces review + lesson guardada en `jd_record`

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
  - `judgment-memory/` almacena resultados normalizados de flujos de revisión completados.
- **Contratos explícitos**: cada fase SDD devuelve un envelope estructurado (Section D en `skills/_shared/sdd-phase-common.md`), con `status`, `executive_summary`, `artifacts`, `next_recommended`, `risks`, `skill_resolution`.
- **Indexado incremental**: el indexador de código saltea archivos sin cambios y limpia los borrados del índice.
- **Prompt separation**: los prompts de orquestación y fases viven en `prompts/sdd/` como archivos `.md` referenciados desde `opencode.json`, no inline en JSON.
- **Skill registry**: las skills se resuelven una vez por sesión desde el registry y se inyectan como rutas exactas en cada sub-agente, no se buscan ad-hoc.


## Notas
- `AGENTS.md` define convenciones de orquestación, reglas de respuesta y patrones de uso de memoria/indexación esperados por el ecosistema de agentes circundante.
- `opencode.json` está presente en la raíz del repositorio, indicando que el repo está pensado para integrarse con una configuración de MCP/tooling compatible con OpenCode.
- El setup de Docker es solo para **Ollama** y **Qdrant**; los servidores MCP en Python están pensados para correr directamente sobre stdio en lugar de dentro de contenedores.
- Los prompts de fases SDD usan el patrón `{file:./prompts/sdd/<phase>.md}` para mantener `opencode.json` limpio y los prompts editables sin tocar JSON.
- `skills/_shared/` contiene los protocolos comunes que todas las fases SDD cargan: `sdd-phase-common.md` (secciones A-E), `tonymem-convention.md`, `openspec-convention.md`, `sdd-status-contract.md`, `persistence-contract.md`, `review-ledger-contract.md`, y `skill-resolver.md`.