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

### Kernel (Tony Kernel)
- **Orquestación determinista** — `kernel/orchestrator_integration.py` gobierna las 8 fases SDD (explore → archive) con checksums de fase, gate de artifacts, scope guard, retry budget y evidencias.
- **Plugin OpenCode** — `plugins/tony-kernel/index.ts` intercepta `tool.execute.before/after` para forzar `can_start_phase` antes de delegar y `record_phase_completion` después de ejecutar.
- **CLI** — `kernel/cli.py` expone `can_start_phase`, `record_delegation`, `record_phase_completion`, `check_scope`, `reset`, `status`.
- **Persistencia** — `kernel/persistence.py` guarda estado en `.tony-kernel/kernel-state.json` (WAL mode en SQLite). `task_ledger.py` trackea tareas por fase. `evidence_ledger.py` guarda evidencias.

### Servicios de contexto
- **TonyMem** — Memoria persistente para decisiones, hallazgos y compartición de contexto entre sesiones. Servidor MCP Python (`local-memory/server.py`) + plugin OpenCode (`plugins/tonymem.ts`) comparten el mismo `memory.db` en modo WAL. Lifecycle de memorias con 3 estados: `active` (default), `proven` (solución verificada, rankea primero en `mem_search`), `needs_review` (stale, no confiar sin verificar).
- **Code Indexer + Qdrant** — Búsqueda semántica sobre el código usando embeddings locales (`bge-m3`). Servidor MCP Python (`code-index/server.py`) con indexación incremental.
- **Poda de Contexto Dinámica (DCP)** — Gestión automática de la ventana de contexto (plugin externo en `.opencode/dcp.jsonc`).
- **Judgment Memory** — Puente entre Judgment Day y TonyMem. Persiste juicios en SQLite (`judgment-memory/ledger.py`) y los indexa en Qdrant (`jdmem_{project}`) para recall semántico.

### Protocolos compartidos
- **SDD Phase Common** (`skills/_shared/sdd-phase-common.md`) — Contrato común mínimo para ejecutores SDD: disciplina de contexto, persistencia de artifacts, contrato de retorno y reglas de seguridad.
- **TonyMem Convention** (`skills/_shared/tonymem-convention.md`) — Topic keys, contratos de `mem_save`/`mem_get_observation`/`mem_search`/`mem_review`, aislamiento por proyecto, manejo de concurrencia, lifecycle de memorias (active/proven/needs_review).
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
├── ARCHITECTURE.md                    # Documentación técnica de arquitectura
├── INSTALL.md                         # Guía de instalación detallada
├── TESTING.md                         # Estrategia y guía de ejecución de pruebas
├── Makefile                           # Wrappers de tests, bootstrap, health, docker
├── requirements-dev.txt               # pytest (para desarrollo y CI)
├── requirements-optional.txt          # tree-sitter (opt-in)
│
├── tests/                             # suite centralizada de tests
│   ├── test_kernel_state_machine.py   # Tests unitarios FSM + enforcement
│   ├── test_kernel_integration.py     # Tests de integración plugin ↔ Python
│   ├── test_kernel_cli.py             # Tests CLI (reset, record_delegation, etc.)
│   ├── test_kernel_hardening.py       # Tests de hardening (validaciones adversarias)
│   ├── test_kernel_enforcement.py     # Contrato de enforcement fail-closed
│   ├── test_sdd_flow_e2e.py           # Flujo aislado explore→archive, 28 checks adversariales
│   ├── test_python_test_runner.py     # Cobertura unitaria del runner standalone stdlib
│   ├── test_local_memory_server.py    # Regression test (MCP framing, UPSERT, FTS)
│   ├── test_code_index_core.py        # Regression test (mock HTTP, incremental)
│   ├── test_judgment_memory_ledger.py # Regression test (mock Ollama/Qdrant)
│   ├── judgment_memory_hooks.test.ts  # Test harness TypeScript para hooks
│   ├── tony_kernel_e2e.test.ts        # End-to-end adversarial TypeScript
│   ├── tony_kernel_hooks.test.ts      # Unit tests del plugin TypeScript
│   └── tony_kernel_integration.test.ts# Puente TS → Python real
│
├── kernel/                            # Tony Kernel — orquestación determinista SDD
│   ├── cli.py                         # CLI: can_start_phase, record_phase_completion, check_scope, reset, status
│   ├── orchestrator_integration.py    # Phase controller + artifact gate + scope check + retry budget
│   ├── state_machine.py               # FSM de fases SDD
│   ├── phase_gate.py                  # Validación de transiciones de fase
│   ├── artifact_gate.py               # Validación de artifacts (exists + hash + validated + integral)
│   ├── artifact_store.py              # disk_artifact_store (sha256 + WAL)
│   ├── persistence.py                 # Persistencia WAL en .tony-kernel/kernel-state.json
│   ├── phase_checksum.py              # Detección de tampering post-completion
│   ├── retry_budget.py                # Presupuesto de reintentos por fase
│   ├── evidence_ledger.py             # Registro de evidencias por tarea
│   ├── task_ledger.py                 # Track de tareas por fase
│   ├── schemas.py                     # ArtifactRef, DelegationRecord, PhaseCompletion
│   └── mcp_server.py                  # MCP server para kernel (registrado en opencode.json)
│
├── tools/                             # Herramientas auxiliares y test runners
│   ├── run-python-tests.py            # Runner de tests Python standalone (solo stdlib)
│   └── validate-config.ts             # Validador de opencode.json, prompts, agents y MCP
│
├── plugins/                           # Plugins para OpenCode
│   ├── tonymem.ts                     # Hook OpenCode: auto-guardar sesiones + prompts
│   ├── qdrant.ts                      # Cliente REST Qdrant + Ollama (Bun)
│   ├── judgment-memory.ts             # Bridge: recall antes de JD, captura después
│   └── tony-kernel/                   # Tony Kernel plugin (enforcement determinista)
│       └── index.ts                   # Hook entry: checks antes y después de fases
│
├── prompts/                           # Prompts fuente y contratos de agentes
│   ├── agents/                         # Orquestador, routing y agentes de review/Judgment Day
│   │   ├── tony-orchestrator.md       # Orquestador SDD mínimo
│   │   ├── phase-capabilities.md      # Mapa de routing por capacidad
│   │   └── phase-prompts/             # Reviewers y agentes Judgment Day
│   └── sdd/                            # Prompts directos de las fases SDD
│
├── skills/                            # Skills registradas y protocolos comunes
│   └── _shared/                       # sdd-phase-common, tonymem-convention, openspec-convention
│
├── local-memory/                      # TonyMem — MCP server (8 tools)
│   ├── server.py
│   └── README.md
│
├── code-index/                        # Code Indexer + Qdrant — MCP server (3 tools)
│   ├── core.py                        # Chunking, embeddings, Qdrant client (stdlib)
│   ├── server.py
│   └── README.md
│
├── judgment-memory/                   # Judgment Day <-> TonyMem bridge
│   ├── ledger.py                      # SQLite ledger + normalize + embed + Qdrant
│   ├── server.py                      # jd_recall / jd_record / jd_history / jd_stats
│   └── README.md
│
└── docker/                            # Entorno de soporte (Ollama + Qdrant)
    └── docker-compose.yml
```

> **Estrategia de Tests**: Los tests Python pueden ejecutarse mediante `pytest tests/` (desarrollo/CI) o con el runner standalone sin dependencias `python3 tools/run-python-tests.py tests`. Los tests TypeScript usan `bun test tests`. Ver [`TESTING.md`](TESTING.md) y el `Makefile`.


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
| `/kernel-status` | Estado del Kernel (fase actual, artifacts, checksums) | kernel-state.json | ✅ |
| `/kernel-reset` | Resetear estado del Kernel (solo desarrollo) | kernel-state.json | ✅ |

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

## Integración de agentes SDD con OpenCode

### 1. Prompts fuente

Los agentes SDD usan directamente sus prompts fuente. No existe una etapa de generación o materialización de bundles.

- `prompts/agents/tony-orchestrator.md`: coordinación mínima del workflow.
- `prompts/agents/phase-capabilities.md`: mapa de capacidades y routing.
- `prompts/agents/phase-launcher.md`: contrato mínimo de lanzamiento.
- `prompts/sdd/<phase>.md`: instrucciones específicas de cada fase SDD.
- `prompts/agents/phase-prompts/*.md`: reviewers y agentes de Judgment Day.
- `skills/_shared/sdd-phase-common.md`: contrato común de los ejecutores SDD.

### 2. Configuración de OpenCode

`opencode.json` conecta cada agente directamente con su prompt fuente mediante `{file:...}`.

Conceptualmente:

```json
{
  "agent": {
    "tony-orchestrator": {
      "prompt": "{file:./prompts/agents/tony-orchestrator.md}"
    },
    "sdd-apply": {
      "prompt": "{file:./prompts/sdd/sdd-apply.md}"
    }
  }
}
```

OpenCode resuelve el prompt del agente seleccionado. El orquestador no debe copiar el prompt completo del ejecutor dentro de la delegación.

### 3. Contexto mínimo y delegación

`tony-orchestrator` mantiene únicamente el contexto necesario para enrutar el workflow:

1. entiende el estado SDD actual;
2. consulta `phase-capabilities.md` para determinar la capacidad correspondiente;
3. selecciona el agente de fase;
4. delega únicamente la información necesaria para iniciar esa fase;
5. recibe el resultado estructurado y decide el siguiente paso.

El orquestador no carga prompts de ejecutores para decidir el routing, no ejecuta trabajo de fase inline y no copia artifacts completos en la delegación. Los ejecutores recuperan sus artifacts upstream desde el backend configurado cuando su fase los necesita.

### 4. Separación entre SDD y Review/Judgment Day

Los agentes SDD y los agentes de review/Judgment Day tienen responsabilidades independientes.

- Los agentes `review-*` inspeccionan dimensiones específicas de una implementación y son read-only.
- `review-refuter` valida únicamente las inferencias suministradas y no agrega findings.
- `jd-judge-a` y `jd-judge-b` ejecutan contratos de juicio independientes.
- `jd-fix-agent` aplica únicamente correcciones confirmadas.

Estos agentes no forman parte del contexto común de ejecución de las fases SDD.

### 5. Disciplina de contexto

La arquitectura evita generar prompts agregados para cada fase.

```text
orchestrator
    ↓
routing data only
    ↓
phase agent
    ↓
phase prompt + required upstream artifacts
    ↓
phase result
```

El objetivo es que cada modelo reciba el mínimo contexto efectivo necesario para completar su responsabilidad.

## 6. Flujo con el Kernel

Para las ocho fases SDD core, el plugin de Tony Kernel intercepta la delegación:

```ts
const args = input.arguments as Record<string, unknown>
const requestedPhase = derivePhase(args)

if (requestedPhase === null) return // agente de protocolo fuera del FSM

const result = await client.canStartPhase(requestedPhase)
if (!result.allowed) {
  throw new KernelBlockedError("Phase transition blocked")
}

await client.recordDelegation(requestedPhase, "sub-agent")
```

Después de la ejecución, el hook de completion valida artifacts, evidencia, scope y estado de la fase antes de registrar `recordPhaseCompletion`.

Los agentes `review-*`, `jd-*`, `sdd-init` y `sdd-onboard` deben estar explícitamente clasificados como agentes conocidos fuera del FSM. Un `subagent_type` desconocido sigue siendo bloqueado por `KernelBlockedError` (fail-closed).

## 7. Checklist de configuración

```bash
bun run tools/validate-config.ts
make test
git diff --check
```

`validate-config.ts` valida la configuración de OpenCode, las referencias `{file:...}`, los recursos compartidos, los agentes y la configuración MCP. La suite no depende de prompts generados.

## Notas
- `AGENTS.md` define convenciones de orquestación, reglas de respuesta y patrones de uso de memoria/indexación esperados por el ecosistema de agentes circundante.
- `opencode.json` está presente en la raíz del repositorio, indicando que el repo está pensado para integrarse con una configuración de MCP/tooling compatible con OpenCode.
- El setup de Docker es solo para **Ollama** y **Qdrant**; los servidores MCP en Python están pensados para correr directamente sobre stdio en lugar de dentro de contenedores.
- Los prompts de fases SDD usan el patrón `{file:./prompts/sdd/<phase>.md}` para mantener `opencode.json` limpio y los prompts editables sin tocar JSON.
- `skills/_shared/` contiene contratos reutilizables; cada fase carga solo los recursos que su prompt requiere.