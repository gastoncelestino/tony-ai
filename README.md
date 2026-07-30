# Tony-AI

Fork de [Gentle-AI](https://github.com/gentleman-programming) — mismo SDD,
mismos comandos, mismos skills, mismo runtime. Se mantiene ~90% del proyecto
original sin tocar; el 10% que cambia son mejoras de mayor impacto,
integradas sin reinventar lo que ya funciona:

| Cambia | Reemplaza a | Estado |
|---|---|---|
| **TonyMem** | Engram | Reescrito desde cero (MCP server + plugin) |
| **Code Indexer + Qdrant** | *(no existía)* | Construido desde cero |
| **DCP** | *(no existía)* | Plugin externo integrado, no reinventado |
| **Double Review** | *(ya existía como Judgment Day)* | 2 correcciones aplicadas |
| **Model Router** | *(sin usar)* | 18 agentes ahora con modelo local asignado |
| **Judgment Day Memory Bridge** | *(no existía)* | TonyMem + Qdrant conectados a Judgment Day: recall antes de juzgar, ledger persistente después |

Todo lo demás — `commands/`, `skills/` (salvo un archivo agregado, ver abajo),
`prompts/sdd/`, la CLI, el runtime — es **byte-idéntico** a Gentle-AI. Esto
está verificado programáticamente en cada paso, no asumido.

## Arquitectura de memoria: patrón "shared SQLite file"

Cada servicio de memoria tiene un MCP server (Python) y un plugin (Bun) que comparten el mismo archivo SQLite en modo WAL:

```
┌─────────────────────────┐    ┌─────────────────────────┐
│  local-memory/server.py │    │   plugins/tonymem.ts    │
│  SQLite: memory.db      │◄──►│  bun:sqlite (WAL mode)  │
└─────────────────────────┘    └─────────────────────────┘

┌─────────────────────────┐    ┌─────────────────────────┐
│  judgment-memory/       │    │  plugins/judgment-      │
│  SQLite: judgment-      │◄──►│  memory.ts + qdrant.ts  │
│  memory.db              │    │  bun:sqlite (WAL mode)  │
└─────────────────────────┘    └─────────────────────────┘
```

## Cómo funciona (visión general)

```mermaid
flowchart TD
    U["Proyecto / pedido del usuario"] --> P["Planning Engine<br/>Qwen3-Coder 30B"]
    P --> I["Implementation<br/>OmniCoder 9B"]

    I --> R4["Revisión 4R<br/>DeepSeek-R1 14B"]
    I -.->|"explícito: juzgar esto"| JD["Judgment Day<br/>DeepSeek-R1 + Qwen3-Coder"]

    JDM["TonyMem Recall<br/>jd_recall"] -.->|"antes de juzgar"| JD
    JD -.->|"después: terminal state"| JDR["jd_record<br/>ledger + Qdrant"]

    R4 --> V["Verify<br/>sdd-verify"]
    JD --> V
    V --> A["Archive<br/>Ornith 9B"]

    P -.->|"consulta / guarda"| CTX
    I -.->|"consulta / guarda"| CTX
    V -.->|"consulta / guarda"| CTX

    subgraph CTX["Servicios de contexto"]
        direction TB
        TM["TonyMem<br/>memoria de decisiones"]
        CI["Code Indexer<br/>búsqueda semántica de código"]
        QD["Qdrant<br/>vector store"]
        DCP["DCP<br/>poda continua de contexto"]
    end

    TM -.->|"shared SQLite file"| TM2["local-memory/server.py"]
    CI -.->|"HTTP API"| QD
    DCP -.->|"plugin global"| OC["OpenCode"]
```

### Arquitectura de memoria: el patrón "shared SQLite file"

El diseño central de Tony-AI es que **cada servicio de memoria tiene un MCP server (Python) y un plugin (Bun) que comparten el mismo archivo SQLite**:

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

Este patrón **elimina el daemon HTTP** que tenía Engram (Go binary + puerto 7437),
remplazándolo por acceso directo al archivo SQLite en modo WAL. WAL es el modo
de concurrencia que SQLite está diseñado para soportar: un escritor a la vez,
lectores nunca bloquean.

### Tres cosas que no son obvias mirando el diagrama

1. **Judgment Day reemplaza a la revisión 4R, no corre en paralelo con ella.**
   Por defecto, después de Implementation corre la revisión 4R ordinaria
   (`review-risk/readability/reliability/resilience` + `review-refuter`).
   Judgment Day (dos jueces ciegos, `jd-judge-a`/`jd-judge-b`) solo se activa
   si lo pedís explícitamente — nunca los dos a la vez.

2. **TonyMem, Code Indexer/Qdrant y DCP no son un paso final.** Se consultan
   y escriben durante cada fase (contexto previo antes de arrancar, guardado
   de decisiones al terminar, poda de contexto continua). No hay una etapa
   "leer memoria" al final del pipeline.

3. **Judgment Day ahora tiene memoria propia.** Antes de lanzar a los jueces,
   se llama `jd_recall` (¿ya vimos un problema parecido?); cuando la
   lineage llega a un estado terminal, el orquestador llama `jd_record`,
   que persiste en un ledger SQLite propio (`judgment-memory/ledger.py`) y
   lo embebe/indexa en Qdrant (colección `jdmem_{project}`, separada de la
   de Code Indexer). Ver `judgment-memory/README.md`.

Ver [`ARCHITECTURE.md`](./ARCHITECTURE.md) para el detalle de cada pieza y
las decisiones detrás de cada cambio.

## Instalación

Este repo es un **overlay**: contiene solo lo que cambia sobre una
instalación existente de Gentle-AI. Ver
[`TONY-AI-INSTALL.md`](./TONY-AI-INSTALL.md) para el paso a paso exacto
(10 secciones, copy-paste, con verificación en cada una). Si corrés esto
desde NixOS, `docker/README.md` tiene las notas puntuales (Docker vs
Podman, GPU vía `nvidia-container-toolkit`) para levantar Ollama + Qdrant
en contenedor sin instalarlos nativos.

## Uso de los comandos nuevos

### `/memory-search`

Busca en TonyMem (decisiones, arquitectura, bugs, patrones) y en
judgment-memory (lecciones de revisiones anteriores). Combina `mem_search`
y `jd_recall` en una sola interfaz.

```
/memory-search "manejo de reintentos HTTP"
```

### `/memory-stats`

Muestra estadísticas de uso de memoria por proyecto: número de observaciones,
tipos más comunes, última actividad.

```
/memory-stats
```

### `/judgment-history`

Lista los últimos juicios de Judgment Day para el proyecto actual. Lee
directamente del SQLite ledger (`judgment-memory.db`), sin depender de
Qdrant/Ollama.

```
/judgment-history
```

## Estructura del repo

```
tony-ai-fork/
├── README.md                          # este archivo
├── ARCHITECTURE.md                    # documentación técnica profunda
├── TONY-AI-INSTALL.md                 # instrucciones de instalación exactas
├── opencode.json                      # mcp.tonymem/code-index/judgment-memory + Model Router
├── AGENTS.md                          # bloque TonyMem + bloque nuevo Code Indexer
├── config/
│   └── tony-memory.yaml               # referencia documentada de env vars
├── docker/
│   ├── docker-compose.yml             # Ollama + Qdrant (backing services)
│   ├── docker-compose.gpu.yml         # override opcional, passthrough NVIDIA
│   ├── .env.example
│   └── README.md                      # notas específicas NixOS
├── Makefile                           # wrappers de conveniencia sobre tests
├── plugins/
│   ├── tonymem.ts                     # reemplaza plugins/engram.ts
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
        └── review-ledger-contract.md  # contrato faltante
```

## Modelos locales (Model Router)

| Rol | Modelo | Agentes |
|---|---|---|
| Planning | `ollama/qwen3-coder:30b` | `gentle-orchestrator`, `sdd-explore`, `sdd-propose`, `sdd-design`, `sdd-spec`, `sdd-tasks`, `sdd-init`, `sdd-onboard` |
| Implementation | `ollama/omnicoder:9b` | `sdd-apply` |
| Review | `ollama/deepseek-r1:14b` | `sdd-verify`, `review-*` (5), `jd-judge-a` |
| Review (juez B) | `ollama/qwen3-coder:30b` | `jd-judge-b` — deliberadamente distinto de `jd-judge-a` |
| Execution | `ollama/ornith:9b` | `sdd-archive`, `jd-fix-agent` |

Verificá los tags reales contra `ollama list` antes de confiar en ellos —
ver `TONY-AI-INSTALL.md` sección 3b.

## Qué NO se tocó (y por qué está bien así)

`commands/*.md` (salvo los 3 nuevos de memoria, que son archivos agregados,
no modificados), la mayoría de `skills/*/SKILL.md` (`judgment-day/SKILL.md`
es la única excepción — 2 líneas de diff, ver `ARCHITECTURE.md`) y
`skills/_shared/*.md`, `prompts/sdd/*.md`, la CLI, el runtime. Los nombres
de tool (`mem_search`, `mem_save`, etc.) son idénticos a los que Engram
exponía, así que estos archivos funcionan contra TonyMem sin saber que
Engram ya no existe. Detalle completo de esta decisión en `ARCHITECTURE.md`.

### La convención `prompt-capture`

`mem_save_prompt` (llamado por el hook `chat.message` en `tonymem.ts`)
guarda el prompt crudo del usuario con `type='prompt-capture'`. Estas
entradas se usan para `mem_context` (recuperar el contexto de la sesión
actual) pero **se excluyen por defecto de `mem_search`** — no son
decisiones ni descubrimientos, son bookkeeping interno. Si necesitás
buscar prompts, filtrá explícitamente por `type='prompt-capture'`.

## Tests

```bash
# Tests de Python (ledger, code-index)
make test-python

# Tests de TypeScript (hooks de plugin, cliente Qdrant)
make test-ts

# Smoke test del cliente Qdrant contra servicios reales
make verify-qdrant

# Todo
make test
```

| Componente | Test | Qué cubre |
|---|---|---|
| TonyMem server | `local-memory/server.py` (manual JSON-RPC) | Sesión completa: save, search, context, session-summary, prompt-capture |
| TonyMem plugin | `plugins/tonymem.ts` (tipado `tsc`) | Tipado contra stubs de `bun:sqlite`/`@opencode-ai/plugin` |
| Code Indexer | `code-index/test_core.py` | Chunking + mock HTTP end-to-end, 4/4 escenarios |
| DCP config | validado contra `dcp.schema.json` | Schema completo, `additionalProperties: false` |
| Judgment Day Memory Bridge | `judgment-memory/test_ledger.py` | Mock Ollama+Qdrant, 7/7 escenarios incl. camino feliz |
| Judgment Day Memory Bridge | `judgment-memory/test_hooks.ts` | Hooks de plugin (`chat.message`, `tool.execute.after`, `system.transform`) |
| Judgment Day Memory Bridge | `judgment-memory/scripts/verify-qdrant.ts` | Smoke test del cliente TS contra servicios reales |

## Fases pendientes

Ninguna, por ahora — los 4 componentes originalmente planeados (TonyMem,
Code Indexer + Qdrant, DCP, Double Review) más el Judgment Day Memory
Bridge agregado después están integrados. Si en algún momento se agrega
algo nuevo, va acá.

## Configuración avanzada

```bash
# Umbral de recall configurable (default 0.5)
export TONY_RECALL_SCORE_THRESHOLD=0.8

# Logging de captura pasiva
export JUDGMENT_MEMORY_DEBUG=1
```

## Limitaciones conocidas

- **Chunking por regex**: puede cortar mal código denso. tree-sitter opcional disponible.
- **Umbral de recall**: configurable via `TONY_RECALL_SCORE_THRESHOLD`.
- **Captura pasiva**: robusta con múltiples patrones y validación.