# Tony-AI — Arquitectura

Este documento explica cada pieza que cambia sobre Gentle-AI, por qué se
construyó así, y qué se verificó realmente (no solo "compila"). Para el
paso a paso de instalación, ver `TONY-AI-INSTALL.md`. Para la vista rápida,
ver `README.md`.

## Principio rector

Gentle-AI ya resuelve SDD, comandos, skills, prompts y runtime. Nada de eso
se reinventa acá. Cada componente de este documento existe porque:
(a) reemplaza algo que dejó de existir (Engram → TonyMem), o
(b) llena un nodo del pipeline que estaba vacío (Code Indexer/Qdrant), o
(c) integra una herramienta externa ya madura en vez de reconstruirla (DCP), o
(d) corrige un defecto real en algo que ya existía (Double Review), o
(e) conecta dos piezas que ya existían por separado pero nunca se hablaban
entre sí (TonyMem/Qdrant <-> Judgment Day — sección 5).

Ninguno reescribe SDD, comandos o prompts para adaptarse a sí mismo — se
adaptan ellos a lo que ya existe.

---

## 1. TonyMem (reemplaza Engram)

### Por qué dos piezas, no una

Engram original era dos componentes acoplados: un MCP server (`engram mcp`,
13 tools) y un plugin de OpenCode (`plugins/engram.ts`) que hablaba por HTTP
contra un daemon Go (`engram serve`) para todo lo que un tool call de MCP no
puede hacer por sí solo — reaccionar a eventos de sesión, inyectar contexto
en compactación, capturar el prompt del usuario antes de que el LLM lo vea.

TonyMem mantiene la misma separación de responsabilidades (MCP server para
tool calls explícitos del agente, plugin para hooks de eventos) pero **sin
el daemon HTTP**: `plugins/tonymem.ts` usa `bun:sqlite` (built-in de Bun, el
runtime que ya usa OpenCode para plugins) para leer/escribir directamente el
mismo archivo SQLite que usa `local-memory/server.py`. Ambos procesos abren
la base en modo WAL, que es exactamente el modo de concurrencia que SQLite
está diseñado para soportar (un escritor a la vez, lectores nunca bloquean).
Esto elimina una clase entera de fallas que tenía Engram (daemon caído,
puerto ocupado, carrera de spawn) sin agregar ninguna dependencia nueva.

### Los 8 tools

Los 4 originales (`mem_save`, `mem_search`, `mem_get_observation`,
`mem_update`) son los que ya usan `commands/`, `skills/`, `prompts/sdd/` —
esos archivos **no se tocaron**. Pero `AGENTS.md` y algunos `skills/_shared/`
(`persistence-contract.md`, `sdd-phase-common.md`, `engram-convention.md`)
llaman además `mem_context`, `mem_session_summary`, `mem_suggest_topic_key`,
`mem_save_prompt` — tools que Engram exponía pero que la implementación
mínima de referencia no tenía. Se agregaron como implementaciones reales
sobre la misma tabla `observations` (no stubs), precisamente para que esos
archivos siguieran funcionando **sin modificarlos**. Ver
`local-memory/README.md` para el detalle de cada uno.

Un detalle que se corrigió durante el desarrollo: `mem_save_prompt` guarda
el prompt crudo del usuario con `type='prompt-capture'` para que
`mem_context` pueda usarlo — pero esas entradas no deben aparecer como
resultado de una búsqueda normal. La primera versión de `mem_search` no
excluía ese tipo por defecto (se filtraba solo en `mem_context`), lo cual se
detectó al testear end-to-end y se corrigió antes de entregar.

### Qué se verificó

- `server.py` compila (`python3 -m py_compile`) y se probó con una sesión
  JSON-RPC completa (save, search, context, session-summary, prompt-capture,
  y el caso de exclusión de `prompt-capture` en `mem_search`).
- `tonymem.ts` se tipó con `tsc` contra stubs de `bun:sqlite` y
  `@opencode-ai/plugin` — 0 errores.
- Diff programático confirmando que `opencode.json` y `AGENTS.md` no
  cambiaron nada fuera de lo documentado (prompts, permisos, y el resto de
  cada agente quedan byte-idénticos).

---

## 2. Code Indexer + Qdrant

### Por qué es un solo componente, no dos

El diagrama original los lista como nodos separados, pero en la práctica es
un solo pipeline: no hay nada que embeber sin chunking, y no hay nada que
buscar sin un vector store. `code-index/core.py` hace las tres cosas
(chunking, embeddings vía Ollama, almacenamiento/búsqueda vía Qdrant) porque
separarlas en archivos distintos solo agregaría imports cruzados sin
beneficio real.

### Chunking sin AST parser

No usa tree-sitter ni ningún parser real — sería una dependencia más y más
mantenimiento del que vale la pena para un primer corte. En cambio, detecta
límites de función/clase/procedure por regex según extensión (`def`/`class`
en Python, `CREATE OR REPLACE PROCEDURE/FUNCTION/PACKAGE` en SQL/PL-SQL,
`function`/`class`/`interface` en TS/JS, `func` en Go, etc. — ver
`BOUNDARY_PATTERNS` en `core.py`), y corta ahí. Si el archivo no tiene un
lenguaje reconocido, o el patrón no encuentra un número razonable de
límites, cae a ventanas de tamaño fijo con overlap. Cubre bien Python,
TS/JS y PL/SQL — la mayoría de este stack — sin la complejidad de un parser
real. Limitación conocida y documentada en `code-index/README.md`: código
muy denso sin blank lines entre funciones puede cortarse mal.

### Indexado incremental de verdad

Cada archivo tiene su hash de contenido guardado en un manifest SQLite
(`.codeindex/manifest.db`, dentro del repo indexado). Reindexar:
- Salta archivos sin cambios (mismo hash).
- Para archivos que cambiaron, borra de Qdrant los chunks viejos que ya no
  corresponden y sube los nuevos.
- Para archivos borrados del disco, limpia sus puntos de Qdrant y su fila
  del manifest.

Esto no es un detalle menor: sin esto, cada reindex duplicaría chunks o
dejaría basura semántica de código que ya no existe.

### Qué se verificó

- El chunker se corrió contra archivos reales del propio proyecto
  (`local-memory/server.py`, `plugins/tonymem.ts`) — cobertura línea por
  línea exacta, cortes en los `def`/`function` correctos.
- Se armó un mock HTTP en memoria de las APIs de Ollama y Qdrant
  (`code-index/test_core.py`) para probar el pipeline completo sin necesitar
  ninguno de los dos servicios corriendo. 4 escenarios pasando: índice
  inicial, no-op en re-run sin cambios, actualización incremental al
  modificar un archivo, limpieza al borrar uno.
- El server MCP (`code-index/server.py`) se probó con `tools/list` y
  `tools/call` reales — incluyendo el caso sin Qdrant/Ollama corriendo, para
  confirmar que falla con un mensaje claro y accionable en vez de crashear.

### Integración

`mcp.code-index` agregado a `opencode.json` (mismo patrón que `tonymem`).
Bloque nuevo y delimitado en `AGENTS.md`
(`<!-- tony-ai:code-index-protocol -->`) explicando cuándo usar
`code_search` en vez de `grep`/`glob`. No se tocó ningún skill/comando
existente — es funcionalidad nueva, no un reemplazo.

---

## 3. DCP (Dynamic Context Pruning)

### Por qué se integra en vez de construirse

Antes de escribir código se investigó qué hooks de plugin de OpenCode sirven
hoy para pruning real:

- `experimental.chat.messages.transform` — el hook obvio para reescribir el
  historial de mensajes — **no recibe mensajes** en la versión actual
  (`input: {}`, issue conocido en el tracker de OpenCode).
- `experimental.chat.system.transform` tiene un bug reportado donde las
  mutaciones no siempre se propagan en algunas versiones.

Escribir un DCP casero contra esa superficie hubiera sido frágil desde el
día uno. En cambio, `Opencode-DCP/opencode-dynamic-context-pruning`
(paquete npm `@tarquinen/opencode-dcp`) ya existe: activamente mantenido,
maduro, y probablemente el mismo "DCP" al que ya se refería este stack.
Reduce contexto exponiéndole al modelo un tool `compress` que el modelo
mismo decide cuándo usar — no depende de los hooks frágiles de arriba.

### Qué se configuró específicamente para Tony-AI

`.opencode/dcp.jsonc` (validado contra el `dcp.schema.json` real del
plugin — `additionalProperties: false` en todos los objetos, así que
cualquier clave mal tipeada lo hubiera rechazado):

- **Límites de contexto por modelo** (`modelMaxLimits`/`modelMinLimits`)
  usando las mismas strings `ollama/qwen3-coder:30b` etc. del Model Router,
  en vez de un límite global genérico — los modelos locales tienen ventanas
  de contexto muy distintas entre sí.
- **`nudgeForce: "strong"`** en vez del default `"soft"` — modelos locales
  más chicos son menos proactivos decidiendo comprimir por su cuenta que un
  frontier model.
- **`protectedFilePatterns`** con `openspec/changes/**` — ahí vive el
  proposal/design/tasks/specs de una sesión SDD activa; nunca debería
  podarse a mitad de sesión.
- **`turnProtection`** habilitado (4 turnos) — colchón antes de podar algo,
  útil cuando una tool call reciente puede necesitarse un par de turnos
  después con modelos locales más lentos en converger.

### Qué NO se tocó

`AGENTS.md` no necesita ningún cambio para esto — DCP inyecta sus propias
instrucciones de sistema de forma autónoma.

---

## 4. Double Review (Judgment Day) — dos correcciones, no una reconstrucción

Judgment Day ya existía completo en Gentle-AI (`skills/judgment-day/SKILL.md`
+ agentes `jd-judge-a`/`jd-judge-b`/`jd-fix-agent`). Al leerlo con cuidado
aparecieron dos problemas reales, ambos corregidos sin tocar el mecanismo.

### 4a. Los dos jueces ciegos compartían modelo

`jd-judge-a` y `jd-judge-b` tienen prompts byte-idénticos por diseño — la
intención es que ambos apliquen el mismo criterio de forma aislada, y el
skill es explícito: *"two-judge agreement is the corroboration mechanism"*.
Pero corroboración requiere independencia real. Al asignar modelos en el
Model Router, ambos jueces habían quedado con el mismo modelo
(`deepseek-r1:14b`) — dos instancias del mismo modelo con el mismo prompt no
son corroboración independiente, son la misma opinión preguntada dos veces.

Corregido: `jd-judge-b` → `ollama/qwen3-coder:30b` (linaje de entrenamiento
distinto de `jd-judge-a`). Verificado programáticamente que el resto de
`opencode.json` no cambió.

### 4b. El contrato de ledger que faltaba

`judgment-day/SKILL.md` referencia `../_shared/review-ledger-contract.md`
como *"canonical transaction, ledger, persistence, and lifecycle contract"*.
Ese archivo no existe en ningún lado del proyecto base — confirmado
listando los 68 archivos del zip original. Sin él, cada corrida de Judgment
Day (y de la revisión 4R ordinaria, que comparte los mismos 5 artefactos:
`transaction`, `ledger`, `receipt`, `chain-bundle`, `gate-context`) tiene que
improvisar el schema.

Se agregó `skills/_shared/review-ledger-contract.md` — consolidación de
reglas que ya estaban dispersas y afirmadas en `sdd-status-contract.md`
(paths/topics exactos por artifact store), `sdd-archive/SKILL.md` (qué debe
matchear el receipt), `sdd-verify/SKILL.md` (qué artefactos no deben existir
antes de terminal) y `judgment-day/references/prompts-and-formats.md` (shape
de los findings). No inventa mecánica nueva; es la única excepción a "no
tocar skills" en todo este fork, y es estrictamente aditiva.

### Qué NO se tocó

Los 5 agentes de la revisión 4R ordinaria (`review-risk/readability/
reliability/resilience/refuter`) — su mecanismo de corroboración es
distinto (el refuter corrobora afirmaciones, no re-deriva el juicio desde
cero), así que diversificar modelos ahí no tiene el mismo fundamento y no
se aplicó sin pedido explícito.

---

## 5. Judgment Day Memory Bridge

### El problema que resuelve

Judgment Day (sección 4) es *stateless* entre corridas: cada vez que se
juzga un target, los dos jueces parten de cero, aunque un target parecido
ya se haya juzgado antes y ya exista una lección aprendida ("faltaba una
capa de validación", "revisar el plan de ejecución antes de optimizar").
TonyMem (sección 1) y Code Indexer/Qdrant (sección 2) ya resuelven memoria
de proyecto y búsqueda semántica de código respectivamente — pero ninguno
de los dos habla con Judgment Day. Este componente cierra ese circuito:

```
Decision (judge_a/judge_b + Agreement Engine)
  -> Normalize (task + veredictos + lección, una sola pasada de texto)
  -> Embedding (Ollama, mismo contrato que code-index)
  -> Qdrant (colección jdmem_{project}, separada de codeidx_{project})
  -> Future Recall (jd_recall, antes del próximo Judgment Day)
```

### Por qué un ledger propio y no reusar `observations` de TonyMem

Se evaluó extender la tabla `observations` de TonyMem en vez de crear
`judgment-memory/ledger.py`, y se descartó: un judgment record tiene campos
estructurados y obligatorios (`judge_a`/`judge_b`/`agreement`/`final`) que
no encajan en el esquema libre `(title, content, type)` de `observations`
sin forzarlo — y `mem_search` es full-text sobre texto libre, no el
`agreement`/`contradiction_rate` que `jd_stats` necesita agregar. Separar
el store evita que un cambio de schema en uno rompa al otro, al costo de
un segundo archivo SQLite (`judgment-memory.db`, mismo patrón WAL que
`memory.db`).

### Por qué una colección Qdrant separada de Code Indexer

`code-index` embebe *chunks de código* con `bge-m3`; acá se embeben
*lecciones en texto natural corto* con `nomic-embed-text` — mismo motivo
por el que un modelo de embedding de código no es la mejor opción para
frases como "revisar el plan de ejecución antes de optimizar". Mezclar
ambos en una sola colección Qdrant además acoplaría dos ciclos de vida de
indexado que no tienen relación (reindexar código no debería tocar juicios,
y viceversa).

### Dos caminos de escritura, mismo patrón que TonyMem

Igual que la sección 1 (MCP server para tool calls explícitos + plugin para
hooks de evento), acá hay dos caminos que escriben al mismo archivo SQLite:

- **Explícito (`jd_record`, autoritativo)**: el orquestador lo llama cuando
  una lineage llega a estado terminal — record completo, coincide con
  `schema.json` exactamente. Es el único camino que produce
  `judge_a`/`judge_b`/`agreement`/`confidence` reales.
- **Pasivo (best-effort, red de seguridad)**: `plugins/judgment-memory.ts`
  observa la salida del tool `Task` buscando la línea terminal del Output
  Contract (`JUDGMENT: APPROVED ✅` / `JUDGMENT: ESCALATED ⚠️`, literal de
  `judgment-day/SKILL.md`) y guarda un record mínimo si el orquestador se
  olvidó de llamar `jd_record`. Deliberadamente conservador: solo completa
  los campos que puede parsear con confianza del texto (task, outcome,
  lección si hay una línea `Lesson:`/`Learned:`) — nunca inventa veredictos
  de jueces o un `confidence` que no vio.

El recall proactivo (antes de lanzar a los jueces) usa el mismo puente de
dos hooks que ya usa `tonymem.ts` para su nudge de guardado: `chat.message`
detecta las keywords de activación de Judgment Day (las mismas del
frontmatter de `judgment-day/SKILL.md`: "judgment day, dual review,
adversarial review, juzgar"), dispara `semanticSearch` contra Qdrant, y
guarda el resultado en un `Map` en memoria por `sessionID`; el siguiente
`experimental.chat.system.transform` de esa misma sesión lo consume una
vez y lo limpia. No inyecta nada si Qdrant/Ollama no responden — degrada a
silencio, no a error.

### Qué se verificó

- `ledger.py` probado por CLI end-to-end (`record`/`history`/`stats`,
  con y sin `--no-index`) — upsert por `(project, execution_id)` confirmado
  no duplica filas al re-grabar el mismo `execution_id`.
- `judgment-memory/test_ledger.py` — mismo patrón de mock HTTP en memoria
  que `code-index/test_core.py` (un `HTTPServer` local respondiendo tanto
  `/api/embed` de Ollama como los endpoints de Qdrant). A diferencia de la
  primera entrega, esto sí ejercita el **camino feliz completo**: embed
  real (mock) → upsert real (mock) → search real (mock) → recall con
  resultados. 7 escenarios: guardado solo-ledger, pipeline completo,
  upsert-no-duplica al re-grabar el mismo `execution_id`, recall semántico
  devuelve ambos records esperados, agregación de `stats` (incluyendo
  `contradiction_rate`), validación rechaza un `final` inválido, y
  degradación controlada apuntando a un puerto cerrado (confirma
  `indexed: false` + `index_error` sin excepción, y que el ledger igual
  quedó escrito).
- `server.py` probado con una sesión JSON-RPC completa (`initialize`,
  `tools/list`, `jd_record`, `jd_history`) — cubre el protocolo MCP, no
  la lógica de embedding/Qdrant en sí (eso lo cubre `test_ledger.py`).
- `qdrant.ts` y `judgment-memory.ts` tipados con `tsc` contra los mismos
  stubs que ya usa `tonymem.ts` (`bun:sqlite`, `@opencode-ai/plugin`,
  Node/Bun globals) — mismo conjunto de errores esperables por falta de
  ambient types, cero errores de lógica adicionales. `qdrant.ts` además
  tiene `judgment-memory/scripts/verify-qdrant.ts` — un smoke test que
  ejercita las 6 funciones exportadas contra Ollama/Qdrant **reales**
  (embed, ensureCollection, upsert, search, semanticSearch, degradación).
  No se ejecutó desde este entorno (no hay Bun ni los servicios acá) — se
  entrega listo para correr en la máquina real de instalación, ver
  `TONY-AI-INSTALL.md` sección 10. `judgment-memory.ts` en sí (los hooks
  de plugin — `chat.message`, `tool.execute.after`,
  `experimental.chat.system.transform`) sigue sin tener equivalente
  ejecutable fuera de una sesión real de OpenCode; eso es lo que queda
  pendiente de validar con más confianza.
- `opencode.json` validado como JSON después de agregar el bloque
  `mcp.judgment-memory` — diff aislado al bloque nuevo, resto sin tocar.

### Qué NO se tocó

`skills/_shared/review-ledger-contract.md` queda exactamente igual — el
ledger de una transacción SDD/4R/Judgment Day en curso (efímero, se archiva
al terminar) y el ledger de `judgment-memory` (memoria de largo plazo entre
corridas) son conceptos distintos a propósito. `judgment-day/SKILL.md` solo
recibió las 2 líneas de diff descritas en `TONY-AI-INSTALL.md` sección 10c
— ningún Hard Rule, Decision Gate ni el Output Contract cambiaron de
significado.

### Infra: por qué Docker solo para Ollama/Qdrant, no para los MCP servers

`docker/docker-compose.yml` containeriza Ollama y Qdrant — los dos
servicios con estado real, versionado y (para Ollama) consideraciones de
driver de GPU, que es exactamente para lo que sirve Docker Compose. Los
tres MCP servers (`local-memory`, `code-index`, `judgment-memory`) se
quedan nativos a propósito: son Python stdlib-only sin dependencias que
aislar, y OpenCode ya los invoca por stdio directo
(`mcp.<name>.command: ["python3", "./server.py"]`) — envolverlos en un
contenedor solo agregaría un salto de stdin/stdout por un beneficio nulo,
y en NixOS específicamente `pkgs.python3` ya cubre el único requisito real
(nada que compilar, nada que instalar con pip). Detalle NixOS-específico
(Docker vs Podman, GPU vía `nvidia-container-toolkit`) en
`docker/README.md`.

---

## Verificación transversal

Cada componente de este documento tuvo alguna forma de prueba real antes de
entregarse, no solo "el código parece correcto":

| Componente | Verificación |
|---|---|
| TonyMem server | Sesión JSON-RPC completa, bug de `prompt-capture` encontrado y corregido |
| TonyMem plugin | `tsc` contra stubs de `bun:sqlite`/`@opencode-ai/plugin`, 0 errores |
| Code Indexer | Chunking contra archivos reales + mock HTTP end-to-end, 4/4 escenarios |
| DCP config | Validado contra `dcp.schema.json` real con `jsonschema` |
| Double Review | Diff programático confirmando que solo cambió lo documentado |
| Judgment Day Memory Bridge | `test_ledger.py` (mock Ollama+Qdrant, 7/7 escenarios incl. camino feliz completo), `scripts/verify-qdrant.ts` (smoke test del cliente TS contra servicios reales, listo para correr en instalación), sesión JSON-RPC del MCP server, `tsc` sobre plugin/cliente TS (hooks del plugin sin equivalente de test runtime) |
| Todo `opencode.json` | Comparación campo por campo contra el original en cada paso |

## Qué queda fuera de este fork (a propósito)

- Diversificación de modelos en la revisión 4R ordinaria (ver 4b).
- Cualquier cambio a `commands/` más allá de los 3 agregados en la sección 5,
  la mayoría de `skills/`, `prompts/sdd/`, o la CLI — no había motivo para
  tocarlos.
- Mejoras al chunking de Code Indexer con un parser AST real (tree-sitter) —
  la versión por regex cubre el caso de uso actual; se documenta como
  limitación conocida, no se resuelve preventivamente.
- Un umbral de score configurable en runtime para `jd_recall` (hoy es una
  constante, `recall_score_threshold` en `config/tony-memory.yaml` es
  documentación, no un valor leído) — si hace falta tunearlo por proyecto,
  es la primera extensión natural del bridge.
- Un test runtime para los *hooks del plugin* (`plugins/judgment-memory.ts`
  — `chat.message`, `tool.execute.after`, `experimental.chat.system.transform`)
  equivalente a `test_ledger.py`. `judgment-memory/scripts/verify-qdrant.ts`
  ya cierra la brecha del cliente HTTP (`plugins/qdrant.ts`) contra
  servicios reales; lo que falta es específicamente la lógica de los
  hooks de OpenCode, que solo se puede ejercitar dentro de una sesión
  real (o con un mock del `Plugin` context de OpenCode, que no existe hoy).
