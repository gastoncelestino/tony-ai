# Tony-AI — Architecture

## Propósito y principios arquitectónicos

Tony-AI es un sistema de orquestación de agentes de IA para desarrollo de software basado en Spec-Driven Development (SDD).

La arquitectura separa dos responsabilidades que no deben depender únicamente del comportamiento de un LLM:

- **Orquestación:** decidir qué trabajo debe ejecutarse y qué agente tiene la capacidad correspondiente.
- **Enforcement:** determinar de forma determinista si una fase puede comenzar, completarse o avanzar.

El sistema combina agentes especializados, memoria persistente, búsqueda semántica y un Kernel determinista que aplica las condiciones críticas del workflow.

Tony-AI no es un sistema de entrenamiento de modelos. Su objetivo es conservar, indexar, recuperar y aplicar conocimiento operativo durante tareas posteriores.

---

## Arquitectura

```text
                         OpenCode
                            │
                            ▼
                    Tony Orchestrator
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
      TonyMem          Context sources   Judgment Memory
                            │
                     ┌──────┴──────┐
                     ▼             ▼
                 Context7      Code Index
                 allowlist
                     │             │
                     └──────┬──────┘
                            ▼
                     Context Assembly
                            │
                            ▼
                       SDD Workflow
                            │
                            ▼
                       Tony Kernel
```

- OpenCode proporciona el runtime del agente.
- Tony Orchestrator coordina el workflow y enruta el trabajo.
- Los servicios de contexto aportan información durante las distintas fases.
- Tony Kernel aplica las reglas deterministas que autorizan o bloquean las transiciones.

## Estructura del repositorio
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

## Componentes principales

| Componente | Responsabilidad |
|---|---|
| **OpenCode** | Runtime y ejecución del agente, plugins y herramientas |
| **Tony Orchestrator** | Routing, coordinación y contexto mínimo |
| **Tony Kernel** | FSM, gates, scope, dependencias de tareas, evidencias, checksums y enforcement |
| **TonyMem** | Memoria persistente de decisiones, hallazgos y contexto |
| **Code Index** | Búsqueda semántica sobre el código |
| **Judgment Memory** | Persistencia y recuperación de juicios anteriores |
| **DCP** | Gestión dinámica de la ventana de contexto |

---

## Responsabilidades de los componentes
OpenCode aloja la ejecución del agente, los plugins y las herramientas utilizadas por el workflow. La configuración de agentes y MCP servers se encuentra en `opencode.json`.
OpenCode puede ejecutar acciones, pero la autorización de una transición de fase controlada pertenece al Tony Kernel.

## Tony Orchestrator
Mantiene el contexto necesario para enrutar el workflow:
- Entiende el estado SDD actual;
- Consulta `phase-capabilities.md` para determinar la capacidad correspondiente;
- Selecciona el agente de fase;
- Delega únicamente la información necesaria para iniciar esa fase;
- Recibe el resultado estructurado y decide el siguiente paso.

El orquestador no carga prompts completos de los ejecutores para decidir el routing, no ejecuta el trabajo de fase inline y no copia artifacts completos en la delegación.

## Tony Kernel
Controla:
- transiciones de fase;
- artifacts requeridos;
- integridad mediante checksums;
- allowed scope;
- dependencias entre tareas;
- evidencia;
- retry budget;
- estado de finalización de las fases.

El agente puede proponer una acción, pero la autorización para avanzar pertenece al Kernel.
El Kernel utiliza una política **fail-closed**: cuando falta una condición obligatoria, la transición se bloquea en lugar de continuar bajo una suposición implícita.

## TonyMem
Proporciona memoria persistente para decisiones, descubrimientos y contexto compartido entre sesiones.
- servidor MCP: `local-memory/server.py`;
- plugin OpenCode: `plugins/tonymem.ts`;
- persistencia SQLite;
- modo WAL para concurrencia;
- lifecycle de memorias: `active`, `proven`, `needs_review`.

Utiliza SQLite en modo WAL para permitir múltiples lectores concurrentes mientras mantiene la restricción de un escritor a la vez.

## Persistencia y almacenamiento
Separa la persistencia según el tipo de conocimiento o estado que administra.

| Sistema | Almacenamiento | Propósito |
|---|---|---|
| TonyMem | SQLite | Observaciones, decisiones y contexto |
| Judgment Memory | SQLite + Qdrant | Ledger y recuperación semántica de juicios |
| Code Index | Qdrant | Índice semántico del código |
| Tony Kernel | JSON + archivos locales | Estado operativo y artifacts |

## Aislamiento de datos
Las bases persistentes configuradas para OpenCode se encuentran bajo `.tonymem/`, mientras que los servidores que acceden a ellas viven en `local-memory/` y `judgment-memory/`.

```text
.tonymem/
├── memory.db
└── judgment-memory.db
```

## Code Index
Proporciona búsqueda semántica sobre el código mediante embeddings locales y Qdrant.
- servidor MCP: `code-index/server.py`;
- embeddings: `bge-m3`;
- almacenamiento vectorial: Qdrant;
- indexación incremental;
- chunking estructural mediante tree-sitter.

Qdrant proporciona almacenamiento y recuperación vectorial para Code Index y Judgment Memory. Las colecciones de Judgment Memory están separadas de las utilizadas por Code Index.

## Context7
**Context7** aporta documentación externa únicamente desde las fuentes autorizadas en `config/knowledge_sources.json`. No se permite resolución abierta de bibliotecas ni acceso a fuentes no configuradas.

## Context Assembly
El contexto autorizado se compone por sesión antes de llegar al agente.

- Context7 aporta documentación autorizada.
- Code Index es la única fuente de búsqueda semántica del código.
- La composición se realiza por `sessionID`.
- El contexto ensamblado se consume una sola vez.
- No se persiste como una nueva memoria.
- Se preserva el system prompt existente.

La arquitectura separa así **adquisición**, **autorización** y **ensamblado de contexto** antes de entregarlo al agente.

```text
Context7 ──────┐
               ├──► Validation ─► Deduplication ─► Relevance
Code Index ────┘                                     │
                                                     ▼
                                               Context Budget
                                                     │
                                                     ▼
                                                 Provenance
                                                     │
                                                     ▼
                                            Context Assembly
                                                     │
                                                     ▼
                                                   Tony
```

- **Validation** acepta únicamente documentación autorizada y resultados válidos de Code Index.
- **Relevance** conserva el `score` semántico real de Code Index y prioriza los resultados con mayor relevancia antes de aplicar el presupuesto.
- Cada resultado de código conserva la **query de búsqueda que lo originó**, de modo que el contexto mantiene la intención de recuperación junto con la evidencia y su score.
- **Deduplication** evita incorporar dos veces la misma evidencia.
- **Context Budget** limita el contexto adicional a 24.000 caracteres y reparte el presupuesto entre documentación y código cuando ambas fuentes están presentes.
- **Provenance** conserva el origen de cada fragmento incorporado.
- El contexto sigue aislado por `sessionID`, preserva el system prompt existente y se consume una sola vez.
- **Observability** permite registrar estadísticas de decisión por sesión —elementos recibidos, aceptados, deduplicados, rechazados por presupuesto y caracteres utilizados— sin almacenar el contenido del contexto.

## Judgment Memory
Conserva juicios y resultados de Judgment Day para permitir recuperación semántica en tareas posteriores.
- ledger SQLite propio: `judgment-memory/ledger.py`;
- almacenamiento vectorial en Qdrant;
- colección separada `jdmem_{project}`;
- recuperación mediante `jd_recall`;
- persistencia mediante `jd_record`.

## DCP
Dynamic Context Pruning gestiona la cantidad de contexto utilizada por OpenCode y permite conservar las partes relevantes durante workflows extensos.

## Arquitectura del workflow
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
   ├──────────────► Context7 ──► documentación autorizada
   ├──────────────► Code Index ─► código relacionado
   ├──────────────► Judgment Memory
   └──────────────► DCP
                  │
                  ▼
          Context Assembly
                  │
                  ▼
              SDD Phase
                  │
                  ▼
            Tony Kernel
                  │
                  ├── State Machine
                  ├── Phase Gate
                  ├── Artifact Gate
                  ├── Scope Guard
                  ├── Task dependencies
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
                  ├── valida dependencias de tareas
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

## State machine y fases SDD
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
`kernel/state_machine.py` define las fases válidas y las transiciones permitidas.

## Fases del FSM vs agentes auxiliares
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

## Arquitectura de contexto y memoria

Los servicios de contexto participan transversalmente en el workflow. No existe una única etapa aislada de "leer memoria" al final del pipeline.

```text
Nueva tarea
    │
    ├── TonyMem ──────────────► decisiones y contexto previo
    ├── Context7 ─────────────► documentación autorizada
    ├── Code Index ───────────► código relacionado
    ├── Judgment Memory ──────► revisiones y juicios previos
    └── DCP ──────────────────► contexto relevante
                                      │
                                      ▼
                              Context Assembly
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

## Arquitectura de Review y Judgment Day
## Review 4R
Después de la implementación, el workflow puede ejecutar la revisión 4R ordinaria. Los agentes `review-*` inspeccionan dimensiones específicas de la implementación y son read-only.

`review-refuter` valida únicamente las inferencias suministradas y no agrega findings nuevos.

## Judgment Day
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

## Correcciones posteriores

`jd-fix-agent` aplica únicamente correcciones confirmadas por el proceso de juicio.

Los agentes de review y Judgment Day no forman parte del contexto común de ejecución de las fases SDD.


## Documentación
[README.md](README.md) — qué es Tony-AI, propuesta de valor, quickstart y visión general.
[INSTALL.md](INSTALL.md) — instalación y configuración del entorno.
[ARCHITECTURE.md](ARCHITECTURE.md) — componentes, responsabilidades, flujos, contratos y persistencia.
[AGENTS.md](AGENTS.md) — reglas operativas para agentes y desarrollo.
[TESTING.md](TESTING.md) — estrategia, comandos y cobertura de pruebas.
