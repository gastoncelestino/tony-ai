# Tony-AI — Architecture

## 1. Propósito y principios arquitectónicos

Tony-AI es un sistema de orquestación de agentes de IA para desarrollo de software basado en Spec-Driven Development (SDD).

La arquitectura separa dos responsabilidades que no deben depender únicamente del comportamiento de un LLM:

- **Orquestación:** decidir qué trabajo debe ejecutarse y qué agente tiene la capacidad correspondiente.
- **Enforcement:** determinar de forma determinista si una fase puede comenzar, completarse o avanzar.

El sistema combina agentes especializados, memoria persistente, búsqueda semántica y un Kernel determinista que aplica las condiciones críticas del workflow.

Tony-AI no es un sistema de entrenamiento de modelos. Su objetivo es conservar, indexar, recuperar y aplicar conocimiento operativo durante tareas posteriores.

---

## 2. Arquitectura de alto nivel

```text
                         OpenCode
                            │
                            ▼
                    Tony Orchestrator
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
      TonyMem          Code Index       Judgment Memory
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                            ▼
                       SDD Workflow
                            │
                            ▼
                       Tony Kernel
                            │
                            ▼
                      Phase / Agent
```

OpenCode proporciona el runtime del agente. Tony Orchestrator coordina el workflow y enruta el trabajo. Los servicios de contexto aportan información durante las distintas fases. Tony Kernel aplica las reglas deterministas que autorizan o bloquean las transiciones.

### Componentes principales

| Componente | Responsabilidad |
|---|---|
| **OpenCode** | Runtime y ejecución del agente, plugins y herramientas |
| **Tony Orchestrator** | Routing, coordinación y contexto mínimo |
| **Tony Kernel** | FSM, gates, scope, evidencias, checksums y enforcement |
| **TonyMem** | Memoria persistente de decisiones, hallazgos y contexto |
| **Code Index** | Búsqueda semántica sobre el código |
| **Judgment Memory** | Persistencia y recuperación de juicios anteriores |
| **DCP** | Gestión dinámica de la ventana de contexto |

---

## 3. Responsabilidades de los componentes

### OpenCode

OpenCode aloja la ejecución del agente, los plugins y las herramientas utilizadas por el workflow. La configuración de agentes y MCP servers se encuentra en `opencode.json`.

OpenCode puede ejecutar acciones, pero la autorización de una transición de fase controlada pertenece al Tony Kernel.

### Tony Orchestrator

`tony-orchestrator` mantiene el contexto necesario para enrutar el workflow:

1. entiende el estado SDD actual;
2. consulta `phase-capabilities.md` para determinar la capacidad correspondiente;
3. selecciona el agente de fase;
4. delega únicamente la información necesaria para iniciar esa fase;
5. recibe el resultado estructurado y decide el siguiente paso.

El orquestador no carga prompts completos de los ejecutores para decidir el routing, no ejecuta el trabajo de fase inline y no copia artifacts completos en la delegación.

### Tony Kernel

Tony Kernel es la capa de enforcement determinista del workflow.

Controla:

- transiciones de fase;
- artifacts requeridos;
- integridad mediante checksums;
- allowed scope;
- evidencia;
- retry budget;
- estado de finalización de las fases.

El agente puede proponer una acción, pero la autorización para avanzar pertenece al Kernel.

El Kernel utiliza una política **fail-closed**: cuando falta una condición obligatoria, la transición se bloquea en lugar de continuar bajo una suposición implícita.

### TonyMem

TonyMem proporciona memoria persistente para decisiones, descubrimientos y contexto compartido entre sesiones.

- servidor MCP: `local-memory/server.py`;
- plugin OpenCode: `plugins/tonymem.ts`;
- persistencia SQLite;
- modo WAL para concurrencia;
- lifecycle de memorias: `active`, `proven`, `needs_review`.

### Code Index

Code Index proporciona búsqueda semántica sobre el código mediante embeddings locales y Qdrant.

- servidor MCP: `code-index/server.py`;
- embeddings: `bge-m3`;
- almacenamiento vectorial: Qdrant;
- indexación incremental;
- chunking estructural mediante tree-sitter.

### Judgment Memory

Judgment Memory conserva juicios y resultados de Judgment Day para permitir recuperación semántica en tareas posteriores.

- ledger SQLite propio: `judgment-memory/ledger.py`;
- almacenamiento vectorial en Qdrant;
- colección separada `jdmem_{project}`;
- recuperación mediante `jd_recall`;
- persistencia mediante `jd_record`.

### DCP

Dynamic Context Pruning gestiona la cantidad de contexto utilizada por OpenCode y permite conservar las partes relevantes durante workflows extensos.

---

## 4. Arquitectura del workflow

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
   ├──────────────► Code Index
   ├──────────────► Judgment Memory
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

La arquitectura mantiene una frontera clara:

- **Orquestador:** decide qué debe ejecutarse.
- **Kernel:** decide si puede ejecutarse.
- **Sub-agent:** ejecuta el trabajo de la fase.
- **Servicios de contexto:** aportan información cuando es necesaria.

---

## 5. State machine y fases SDD

Las fases controladas por el FSM son:

```text
explore
  ↓
propose
  ↓
spec
  ↓
design
  ↓
tasks
  ↓
apply
  ↓
verify
  ↓
archive
```

Cada fase tiene un prompt específico en `prompts/sdd/`.

### Fases del FSM vs agentes auxiliares

No todo agente que participa del workflow representa una transición del FSM.

**Fases controladas por el Kernel:**

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

**Agentes auxiliares:**

```text
sdd-init
sdd-onboard
review-*
jd-*
gga-reviewer
```

Los agentes auxiliares pueden participar del proceso sin convertirse en fases adicionales del state machine.

### SDD init y onboard

- `sdd-init` realiza el bootstrap inicial.
- `sdd-onboard` proporciona un walkthrough guiado.

No representan transiciones adicionales del FSM principal.

---

## 6. Tony Kernel

Tony Kernel aplica enforcement determinista sobre las fases que controla.

### State machine

`kernel/state_machine.py` define las fases válidas y las transiciones permitidas.

### Phase Gate

Impide comenzar una fase cuando la transición desde el estado actual no está permitida o no se cumplen sus precondiciones.

### Artifact Gate

Valida que los artifacts requeridos existan, sean íntegros y correspondan al estado esperado.

### Scope Guard

Comprueba que los cambios permanezcan dentro del alcance permitido por el change request.

### Evidence

El workflow registra evidencia asociada a tareas y completions para que una transición no dependa únicamente de una afirmación textual del agente.

### Checksums

Los checksums permiten detectar modificaciones posteriores de artifacts que ya habían sido validados.

### Retry Budget

El Kernel limita los reintentos permitidos por fase para evitar ciclos indefinidos.

### Integración con OpenCode

El plugin `plugins/tony-kernel/index.ts` intercepta eventos `tool.execute.before/after` para:

1. forzar `can_start_phase` antes de delegar;
2. ejecutar la herramienta cuando la transición está autorizada;
3. registrar `record_phase_completion` después de completar la operación.

La CLI `kernel/cli.py` expone operaciones como:

```text
can_start_phase
record_delegation
record_phase_completion
check_scope
reset
status
```

### Persistencia del Kernel

El estado operativo del Kernel se mantiene en:

```text
.tony-kernel/kernel-state.json
```

Los componentes auxiliares mantienen sus propios ledgers y almacenamiento.

---

## 7. Arquitectura de contexto y memoria

Los servicios de contexto participan transversalmente en el workflow. No existe una única etapa aislada de "leer memoria" al final del pipeline.

```text
Nueva tarea
    │
    ├── TonyMem ──────────────► decisiones y contexto previo
    ├── Code Index ───────────► código relacionado
    ├── Judgment Memory ──────► revisiones y juicios previos
    └── DCP ──────────────────► contexto relevante
                                      │
                                      ▼
                               Agente / Orchestrator
                                      │
                                      ▼
                                  SDD Phase
                                      │
                                      ▼
                                 Tony Kernel
```

Los agentes pueden consultar y actualizar estos componentes durante diferentes fases según las necesidades de contexto, búsqueda semántica y persistencia.

### TonyMem

TonyMem mantiene memoria persistente de decisiones y observaciones. Las memorias tienen tres estados:

- `active`: memoria utilizable por defecto;
- `proven`: solución verificada, priorizada en `mem_search`;
- `needs_review`: memoria potencialmente obsoleta que no debe aceptarse sin verificación.

### Code Index

El Code Index permite localizar código relacionado semánticamente sin requerir que el agente conozca previamente sus paths exactos.

### Judgment Memory

Judgment Memory conecta el proceso de Judgment Day con la persistencia de conocimiento de revisiones anteriores.

Antes de un nuevo juicio, `jd_recall` recupera resultados similares. Al finalizar una lineage terminal, `jd_record` persiste el veredicto en el ledger y lo indexa en Qdrant.

### Persistencia de prompts

El hook `chat.message` puede capturar prompts con `type='prompt-capture'`.

Estas capturas forman parte del contexto general, pero se excluyen de las búsquedas normales para evitar mezclar bookkeeping con conocimiento operativo. Pueden filtrarse explícitamente mediante `type='prompt-capture'`.

---

## 8. Arquitectura de Review y Judgment Day

### Review 4R

Después de la implementación, el workflow puede ejecutar la revisión 4R ordinaria. Los agentes `review-*` inspeccionan dimensiones específicas de la implementación y son read-only.

`review-refuter` valida únicamente las inferencias suministradas y no agrega findings nuevos.

### Judgment Day

Judgment Day es un flujo explícito y separado de la revisión 4R.

No se ejecuta como una fase adicional del FSM.

Cuando se activa explícitamente, utiliza dos jueces independientes:

- `jd-judge-a` — DeepSeek-R1 14B;
- `jd-judge-b` — Qwen3-Coder 30B.

La separación de modelos busca evitar que ambos jueces reproduzcan exactamente el mismo razonamiento.

El flujo conceptual es:

```text
Implementation
      │
      ├──────────────► Review 4R
      │
      └──────────────► Judgment Day
                              │
                         jd_recall
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
               jd-judge-a          jd-judge-b
                    │                   │
                    └─────────┬─────────┘
                              ▼
                         jd_record
                              │
                              ▼
                       Judgment Memory
                              │
                              ▼
                            Verify
```

### Correcciones posteriores

`jd-fix-agent` aplica únicamente correcciones confirmadas por el proceso de juicio.

Los agentes de review y Judgment Day no forman parte del contexto común de ejecución de las fases SDD.

---

## 9. Persistencia y almacenamiento

Tony-AI separa la persistencia según el tipo de conocimiento o estado que administra.

| Sistema | Almacenamiento | Propósito |
|---|---|---|
| TonyMem | SQLite | Observaciones, decisiones y contexto |
| Judgment Memory | SQLite + Qdrant | Ledger y recuperación semántica de juicios |
| Code Index | Qdrant | Índice semántico del código |
| Tony Kernel | JSON + archivos locales | Estado operativo y artifacts |

### SQLite y WAL

TonyMem utiliza SQLite en modo WAL para permitir múltiples lectores concurrentes mientras mantiene la restricción de un escritor a la vez.

### Qdrant

Qdrant proporciona almacenamiento y recuperación vectorial para Code Index y Judgment Memory. Las colecciones de Judgment Memory están separadas de las utilizadas por Code Index.

### Aislamiento de datos

Las bases persistentes configuradas para OpenCode se encuentran bajo `.tonymem/`, mientras que los servidores que acceden a ellas viven en `local-memory/` y `judgment-memory/`.

```text
.tonymem/
├── memory.db
└── judgment-memory.db
```

---

## 10. Protocolos y contratos compartidos

### SDD Phase Common

`skills/_shared/sdd-phase-common.md` define el contrato común mínimo de los ejecutores SDD:

- disciplina de contexto;
- persistencia de artifacts;
- contrato de retorno;
- reglas de seguridad.

### TonyMem Convention

`skills/_shared/tonymem-convention.md` define:

- topic keys;
- contratos de `mem_save`, `mem_get_observation`, `mem_search` y `mem_review`;
- aislamiento por proyecto;
- manejo de concurrencia;
- lifecycle `active` / `proven` / `needs_review`.

### OpenSpec Convention

`skills/_shared/openspec-convention.md` define directorios, paths y delta spec sections utilizados por los artifacts del filesystem.

### Skill Resolver

`skills/_shared/skill-resolver.md` define el protocolo de resolución de skills desde el registry.

---

## 11. Arquitectura de prompts y agentes

Los agentes SDD utilizan directamente sus prompts fuente. No existe una etapa de generación o materialización de bundles.

### Prompts principales

- `prompts/agents/tony-orchestrator.md` — coordinación mínima del workflow.
- `prompts/agents/phase-capabilities.md` — mapa de capacidades y routing.
- `prompts/agents/includes/phase-launcher.md` — contrato mínimo de lanzamiento.
- `prompts/sdd/<phase>.md` — instrucciones específicas de cada fase SDD.
- `prompts/agents/phase-prompts/*.md` — reviewers y agentes de Judgment Day.

### Contexto mínimo

El orquestador mantiene únicamente la información necesaria para enrutar el workflow. Los ejecutores recuperan artifacts upstream desde el backend configurado cuando su fase los necesita.

Esto evita que el prompt del orquestador se convierta en una copia del conocimiento de todos los ejecutores.

---

## 12. Estructura del repositorio

La estructura relevante para la arquitectura es:

```text
tony-ai/
├── README.md
├── ARCHITECTURE.md
├── TESTING.md
├── INSTALL.md
├── AGENTS.md
├── opencode.json
│
├── kernel/                 # Enforcement determinista del workflow
├── local-memory/           # TonyMem MCP server
├── code-index/             # Code Index MCP server
├── judgment-memory/        # Judgment Memory
├── plugins/                # Integraciones OpenCode
├── prompts/                # Orquestador, fases y reviewers
├── skills/                 # Contratos y capacidades compartidas
├── tests/                  # Suite de pruebas
├── tools/                  # Tooling y runners
└── docker/                 # Infraestructura local
```

Los archivos internos del Kernel y de los MCP servers deben documentarse en sus propios README cuando el detalle de implementación exceda el alcance de este documento.

---

## 13. Límites de responsabilidad entre documentos

Para mantener la documentación separada:

- **README.md** — qué es Tony-AI, propuesta de valor, quickstart y visión general.
- **INSTALL.md** — instalación y configuración del entorno.
- **TESTING.md** — estrategia, comandos y cobertura de pruebas.
- **ARCHITECTURE.md** — componentes, responsabilidades, flujos, contratos y persistencia.
- **AGENTS.md** — reglas operativas para agentes y desarrollo.
- **README específicos de componentes** — detalles de implementación de cada subsistema.

Las reglas de estilo, personalidad del agente, Conventional Commits, restricciones de atribución y filosofía de desarrollo no pertenecen a este documento; deben mantenerse en `AGENTS.md` o en documentación de contribución correspondiente.
