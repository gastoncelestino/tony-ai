# Tony-AI - ARQUITECTURA
## Persistencia y memoria

Tony-AI separa la persistencia según el tipo de conocimiento que administra.

- **TonyMem** utiliza SQLite como almacenamiento persistente de observaciones y contexto.
- **Judgment Memory** utiliza un ledger SQLite independiente para registrar juicios y, además, Qdrant para recuperación semántica.
- **Code Indexer** utiliza Qdrant como almacenamiento vectorial del índice semántico del código.
- **Tony Kernel** mantiene su estado operativo en el directorio `.tony-kernel/`.
```
                         ┌──────────────────────────┐
                         │        OpenCode          │
                         │   Agent Orchestrator     │
                         │          + SDD           │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │       Tony Kernel        │
                         │                          │
                         │ Phase Gate · Scope Guard │
                         │ Artifacts · Checksums    │
                         │ Evidence · Transitions   │
                         └────────────┬─────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 │                    │                    │
                 ▼                    ▼                    ▼
        ┌────────────────┐   ┌────────────────┐   ┌──────────────────┐
        │ local-memory   │   │   code-index   │   │ judgment-memory  │
        │                │   │                │   │                  │
        │ Memoria        │   │ Búsqueda       │   │ Memoria de       │
        │ persistente    │   │ semántica      │   │ juicios          │
        │ SQLite         │   │ del código     │   │                  │
        └───────┬────────┘   └───────┬────────┘   └────────┬─────────┘
                │                    │                     │
                ▼                    ▼                     ▼
        ┌──────────────┐      ┌────────────────┐    ┌────────────────┐
        │    SQLite    │      │ Ollama +       │    │ SQLite +       │
        │              │      │ Qdrant         │    │ Qdrant         │
        │ decisiones + │      │ embeddings +   │    │ ledger +       │
        │ contexto     │      │ vector search  │    │ recuperación   │
        └──────────────┘      └────────────────┘    └────────────────┘
```
Este patrón permite un acceso directo al archivo SQLite en modo **WAL**, que es el modo de concurrencia que SQLite está diseñado para soportar: **un escritor a la vez, lectores nunca bloquean**.

## Reglas del proyecto
* Usa Conventional Commits.
* No permite atribuciones Co-Authored-By ni atribuciones de IA en commits.
* Prioriza respuestas y cambios concisos cuando no se necesita más detalle.
* Exige verificar afirmaciones técnicas antes de darlas por ciertas.
* Cuando hay una afirmación incorrecta, se debe explicar técnicamente por qué.
* Promueve alternativas cuando existen trade-offs reales.
* Filosofía de desarrollo

## Ideas importantes:
* Concepts > Code — entender arquitectura y fundamentos antes de escribir código.
* AI is a tool — el humano dirige y la IA ejecuta.
* Solid foundations — arquitectura, patrones y fundamentos antes que soluciones superficiales.
* Against immediacy — no priorizar atajos por encima de diseño y comprensión.

## Alcance de la personalidad
* La personalidad del agente controla cómo responde al usuario, pero no modifica los artifacts técnicos que produce.
* El agente puede hablar en español rioplatense, pero un README.md, código, identificadores, mensajes de error o comentarios técnicos siguen las convenciones del proyecto.

## Skills
* `AGENTS.md` también obliga al agente a verificar si existe una skill aplicable antes de responder o ejecutar una tarea y cargarla cuando corresponda.

## Tres conceptos clave:
1. **Judgment Day es un flujo de revisión explícito y separado de la revisión 4R.**
   Por defecto, después de la implementación se ejecuta la revisión 4R ordinaria. Judgment Day se activa explícitamente y utiliza los jueces configurados `jd-judge-a` y `jd-judge-b`.

2. **TonyMem, Code Indexer/Qdrant y DCP participan transversalmente en el workflow.**  
   Los agentes pueden consultar y actualizar estos componentes durante las diferentes fases según las necesidades de contexto, búsqueda semántica y persistencia. No existe una etapa aislada de "leer memoria" al final del pipeline.

3. **Judgment Day tiene memoria propia.**  
   Antes de lanzar a los jueces, se llama `jd_recall` (¿ya vimos un problema parecido?). Cuando la lineage llega a un estado terminal, el orquestador llama `jd_record`, que persiste en un ledger SQLite propio (`judgment-memory/ledger.py`) y lo embebe/indexa en Qdrant (colección `jdmem_{project}`, separada del Code Indexer). Ver `judgment-memory/README.md`.

## Tony Kernel
- **Orquestación determinista** — `kernel/orchestrator_integration.py` gobierna las 8 fases SDD (explore → archive) con checksums de fase, gate de artifacts, scope guard, retry budget y evidencias.
- **Plugin OpenCode** — `plugins/tony-kernel/index.ts` intercepta `tool.execute.before/after` para forzar `can_start_phase` antes de delegar y `record_phase_completion` después de ejecutar.
- **CLI** — `kernel/cli.py` expone `can_start_phase`, `record_delegation`, `record_phase_completion`, `check_scope`, `reset`, `status`.
- **Persistencia** — `kernel/persistence.py` mantiene el estado operativo del Kernel en `.tony-kernel/kernel-state.json`. Los componentes auxiliares registran tareas y evidencias mediante sus respectivos ledgers.

Tony Kernel aplica una política fail-closed para las fases que controla.   
Cuando una delegación no corresponde a una fase válida, cuando una transición no está permitida o cuando faltan condiciones obligatorias, bloquea la ejecución en lugar de permitir que el agente continúe bajo una suposición implícita.   
El agente puede proponer una acción, pero la autorización para avanzar de fase pertenece al Kernel.

## Servicios de contexto
- **TonyMem** — Memoria persistente para decisiones, hallazgos y compartición de contexto entre sesiones. Servidor MCP Python (`local-memory/server.py`) + plugin OpenCode (`plugins/tonymem.ts`) comparten el mismo `memory.db` en modo WAL. Lifecycle de memorias con 3 estados: `active` (default), `proven` (solución verificada, rankea primero en `mem_search`), `needs_review` (stale, no confiar sin verificar).
- **Code Indexer + Qdrant** — Búsqueda semántica sobre el código usando embeddings locales (`bge-m3`). Servidor MCP Python (`code-index/server.py`) con indexación incremental.
- **Poda de Contexto Dinámica (DCP)** — Gestión automática de la ventana de contexto (plugin externo en `.opencode/dcp.jsonc`).
- **Judgment Memory** — Puente entre Judgment Day y TonyMem. Persiste juicios en SQLite (`judgment-memory/ledger.py`) y los indexa en Qdrant (`jdmem_{project}`) para recall semántico.

## Protocolos compartidos
- **SDD Phase Common** (`skills/_shared/sdd-phase-common.md`) — Contrato común mínimo para ejecutores SDD: disciplina de contexto, persistencia de artifacts, contrato de retorno y reglas de seguridad.
- **TonyMem Convention** (`skills/_shared/tonymem-convention.md`) — Topic keys, contratos de `mem_save`/`mem_get_observation`/`mem_search`/`mem_review`, aislamiento por proyecto, manejo de concurrencia, lifecycle de memorias (active/proven/needs_review).
- **OpenSpec Convention** (`skills/_shared/openspec-convention.md`) — Directorios, paths y delta spec sections para artifacts en filesystem.
- **Skill Resolver** (`skills/_shared/skill-resolver.md`) — Protocolo de resolución de skills desde el registry.

## Flujo arquitectónico
Una tarea atraviesa varias capas antes de producir un cambio verificable:
```text
Usuario
   │
   ▼
OpenCode
   │
   ▼
Tony Orchestrator
   │
   ├──────────────► TonyMem
   │
   ├──────────────► Code Index
   │
   ├──────────────► Judgment Memory
   │
   └──────────────► DCP
   │
   ▼
SDD Phase
   │
   ▼
Tony Kernel
   │
   ├── Phase Gate
   ├── Artifact Gate
   ├── Scope Guard
   ├── Evidence
   ├── Checksums
   └── Retry Budget
   │
   ▼
Sub-agent
   │
   ▼
Phase Result
   │
   ▼
Tony Kernel
   │
   ├── valida artifacts
   ├── valida evidencia
   ├── valida scope
   └── registra completion
   │
   ▼
Siguiente fase
```
El orquestador decide qué agente debe ejecutar una fase, pero el Kernel determina si esa transición está permitida.
Esta separación permite mantener dos responsabilidades independientes:
- **Orquestación:** decidir qué debe ejecutarse.
- **Enforcement:** determinar si puede ejecutarse.

## Prompts de fases SDD
Cada fase tiene su propio prompt en `prompts/sdd/`:
`sdd-explore` → `sdd-propose` → `sdd-spec` → `sdd-design` → `sdd-tasks` → `sdd-apply` → `sdd-verify` → `sdd-archive`
Más `sdd-init` (bootstrap) y `sdd-onboard` (walkthrough guiado).
Cuando se activa explícitamente (por keywords como "juzgar" o "dual review"), ejecuta dos jueces de IA independientes:
- `jd-judge-a` (DeepSeek-R1 14B)
- `jd-judge-b` (Qwen3-Coder 30B) — deliberadamente distinto de `jd-judge-a` para verdadera corroboración

Antes de juzgar, `jd_recall` busca juicios similares anteriores. Después de completar, `jd_record` persiste el veredicto.

## Prompts fuente
Los agentes SDD usan directamente sus prompts fuente. No existe una etapa de generación o materialización de bundles.
- `prompts/agents/tony-orchestrator.md`: coordinación mínima del workflow.
- `prompts/agents/phase-capabilities.md`: mapa de capacidades y routing.
- `prompts/agents/includes/phase-launcher.md`: contrato mínimo de lanzamiento.
- `prompts/sdd/<phase>.md`: instrucciones específicas de cada fase SDD.
- `prompts/agents/phase-prompts/*.md`: reviewers y agentes de Judgment Day.
- `skills/_shared/sdd-phase-common.md`: contrato común de los ejecutores SDD.

## Persistencia de Prompts
Hook chat.message → auto-guarda con type='prompt-capture'
Incluido en mem_context por defecto
Excluido de mem_search (bookkeeping)
Filtrar explícitamente: mem_search(query="...", type='prompt-capture')

## Contexto mínimo y delegación
`tony-orchestrator` mantiene únicamente el contexto necesario para enrutar el workflow:

1. entiende el estado SDD actual;
2. consulta `phase-capabilities.md` para determinar la capacidad correspondiente;
3. selecciona el agente de fase;
4. delega únicamente la información necesaria para iniciar esa fase;
5. recibe el resultado estructurado y decide el siguiente paso.

El orquestador no carga prompts de ejecutores para decidir el routing, no ejecuta trabajo de fase inline y no copia artifacts completos en la delegación. Los ejecutores recuperan sus artifacts upstream desde el backend configurado cuando su fase los necesita.

## Separación entre SDD y Review/Judgment Day
Los agentes SDD y los agentes de review/Judgment Day tienen responsabilidades independientes.

- Los agentes `review-*` inspeccionan dimensiones específicas de una implementación y son read-only.
- `review-refuter` valida únicamente las inferencias suministradas y no agrega findings.
- `jd-judge-a` y `jd-judge-b` ejecutan contratos de juicio independientes.
- `jd-fix-agent` aplica únicamente correcciones confirmadas.

Estos agentes no forman parte del contexto común de ejecución de las fases SDD.

## Flujo con el Kernel
El Kernel diferencia entre:

**Fases SDD controladas por el FSM**
```text
explore
propose
spec
design
tasks
apply
verify
archive
```
y agentes auxiliares que no representan una transición del workflow:
```text
sdd-init
sdd-onboard
review-*
jd-*
gga-reviewer
```
Estos agentes pueden participar del workflow sin convertirse en fases adicionales del FSM.


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
│   ├── artifact_store.py              # Persistencia de artifacts + SHA-256
│   ├── persistence.py                 # Persistencia JSON + lock del estado del Kernel
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

## Propiedades emergentes del diseño
La separación entre memoria persistente, búsqueda semántica y enforcement del workflow permite que el sistema acumule conocimiento operativo sin modificar los modelos.

El valor acumulado proviene de tres fuentes:

1. **Memoria de proyecto** — decisiones y descubrimientos persistentes.
2. **Conocimiento del código** — representación semántica e incremental del codebase.
3. **Memoria de juicios** — resultados y lecciones obtenidas durante revisiones.

El sistema reutiliza estas tres fuentes en tareas posteriores para reducir la dependencia del contexto de una única sesión.


## Principios de diseño
- **Local-first**: el almacenamiento es SQLite y está pensado para quedarse en tu máquina.
- **Dependency-light**: los servidores en Python usan solo stdlib, deliberadamente.
- **Separación de responsabilidades**:
  - `local-memory/` almacena observaciones de texto libre y estado de sesión.
  - `code-index/` busca código real semánticamente.
  - `judgment-memory/` almacena resultados normalizados de flujos de revisión completados.
- **Contratos explícitos**: cada fase SDD devuelve un envelope estructurado (Section D en `skills/_shared/sdd-phase-common.md`), con `status`, `executive_summary`, `artifacts`, `next_recommended`, `risks`, `skill_resolution`.
- **Indexado incremental**: el indexador de código saltea archivos sin cambios y limpia los borrados del índice.
- **Prompt separation**: los prompts son artifacts versionados independientes de `opencode.json`. La configuración referencia los archivos fuente mediante `{file:...}`, evitando duplicar instrucciones dentro del JSON.
- **Skill registry**: las skills se resuelven una vez por sesión desde el registry y se inyectan como rutas exactas en cada sub-agente, no se buscan ad-hoc.

## Disciplina de contexto
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
Esta separación evita que `tony-orchestrator` se convierta en un ejecutor monolítico y permite que cada fase mantenga su propio contrato, prompt y conjunto mínimo de contexto.

## Documentación
[INSTALL.md](INSTALL.md) — instalación y configuración detallada.  
[ARCHITECTURE.md](ARCHITECTURE.md) — arquitectura interna y componentes.  
[AGENTS.md](AGENTS.md) — define las reglas de comportamiento y desarrollo que deben seguir los agentes.  
[TESTING.md](TESTING.md) — es la guía oficial de estrategia y ejecución de pruebas.