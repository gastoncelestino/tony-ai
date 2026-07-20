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

Todo lo demás — `commands/`, `skills/` (salvo un archivo agregado, ver abajo),
`prompts/sdd/`, la CLI, el runtime — es **byte-idéntico** a Gentle-AI. Esto
está verificado programáticamente en cada paso, no asumido.

## Cómo funciona (visión general)

```mermaid
flowchart TD

    USER[Proyecto<br/>(pedido del usuario)]

    PLAN[Planning Engine<br/><b>Qwen3-Coder 30B</b>]

    IMPL[Implementation<br/><b>OmniCoder 9B</b>]

    REVIEW[Revisión 4R (default)<br/><b>DeepSeek-R1 14B</b>]

    JD[Judgment Day (explícito)<br/><b>DeepSeek-R1 + Qwen3</b>]

    VERIFY[Verify<br/><b>sdd-verify · tests/build</b>]

    ARCHIVE[Archive<br/><b>Ornith-9B</b>]


    subgraph CONTEXT["Servicios de contexto (todas las fases, no un paso)"]

        MEMORY[TonyMem]

        INDEX[Code Indexer]

        DCP[DCP<br/>Dynamic Context Pruning]

        QDRANT[Qdrant<br/>Vector Store<br/>para Code Indexer]

    end
```

Dos cosas que no son obvias mirando el diagrama:

1. **Judgment Day reemplaza a la revisión 4R, no corre en paralelo con ella.**
   Por defecto, después de Implementation corre la revisión 4R ordinaria
   (`review-risk/readability/reliability/resilience` + `review-refuter`).
   Judgment Day (dos jueces ciegos, `jd-judge-a`/`jd-judge-b`) solo se activa
   si lo pedís explícitamente — nunca los dos a la vez.
2. **TonyMem, Code Indexer/Qdrant y DCP no son un paso final.** Se consultan
   y escriben durante cada fase (contexto previo antes de arrancar, guardado
   de decisiones al terminar, poda de contexto continua). No hay una etapa
   "leer memoria" al final del pipeline.

Ver [`ARCHITECTURE.md`](./ARCHITECTURE.md) para el detalle de cada pieza y
las decisiones detrás de cada cambio.

## Instalación

Este repo es un **overlay**: contiene solo lo que cambia sobre una
instalación existente de Gentle-AI. Ver
[`TONY-AI-INSTALL.md`](./TONY-AI-INSTALL.md) para el paso a paso exacto
(9 secciones, copy-paste, con verificación en cada una).

## Estructura del repo

```
tony-ai-fork/
├── README.md                          # este archivo
├── ARCHITECTURE.md                    # documentación técnica profunda
├── TONY-AI-INSTALL.md                 # instrucciones de instalación exactas
├── opencode.json                      # mcp.tonymem/code-index + Model Router (diff mínimo sobre el original)
├── AGENTS.md                          # bloque TonyMem + bloque nuevo Code Indexer (diff mínimo)
├── plugins/
│   └── tonymem.ts                     # reemplaza plugins/engram.ts
├── local-memory/                      # TonyMem — MCP server (8 tools)
│   ├── server.py
│   └── README.md
├── code-index/                        # Code Indexer + Qdrant — MCP server (3 tools)
│   ├── core.py
│   ├── server.py
│   ├── test_core.py
│   └── README.md
├── .opencode/
│   └── dcp.jsonc                      # config de DCP (plugin externo, no incluido acá)
└── skills/_shared/
    └── review-ledger-contract.md      # contrato faltante que judgment-day/SKILL.md referenciaba
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

`commands/*.md`, la mayoría de `skills/*/SKILL.md` y `skills/_shared/*.md`,
`prompts/sdd/*.md`, la CLI, el runtime. Los nombres de tool (`mem_search`,
`mem_save`, etc.) son idénticos a los que Engram exponía, así que estos
archivos funcionan contra TonyMem sin saber que Engram ya no existe. Detalle
completo de esta decisión en `ARCHITECTURE.md`.

## Fases pendientes

Ninguna, por ahora — los 4 componentes planeados (TonyMem, Code Indexer +
Qdrant, DCP, Double Review) están integrados. Si en algún momento se agrega
algo nuevo, va acá.
