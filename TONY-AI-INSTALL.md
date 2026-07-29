# Tony-AI — instrucciones de instalación exactas

Este paquete es un **overlay**, no un repo completo. Contiene solo lo que cambia
sobre tu Gentle-AI actual. Todo lo demás (skills/ salvo `judgment-day/SKILL.md`
y `_shared/review-ledger-contract.md`, prompts/sdd/, tui.json, tui-plugins/,
plugins/model-variants.ts, plugins/skill-registry.ts) **no se toca** — cópialo
tal cual está en tu instalación de Gentle-AI, byte por byte. `commands/` tiene
3 archivos nuevos agregados en la sección 10 (`memory-search.md`,
`memory-stats.md`, `judgment-history.md`) — el resto tampoco se toca.

## 0. Ubicaciones asumidas

- Config de OpenCode: `~/.config/opencode/` (ajustá si la tuya es otra)
- TonyMem va a vivir en: `~/tools/tonymem/` (podés ponerlo donde quieras,
  pero ajustá las rutas del paso 2 si lo movés)

## 1. Copiar TonyMem (reemplaza Engram por completo)

```bash
mkdir -p ~/tools/tonymem
cp -r local-memory ~/tools/tonymem/local-memory
```

Verificá que corre standalone antes de tocar OpenCode:

```bash
cd ~/tools/tonymem/local-memory
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | python3 server.py
```

Deberías ver 8 tools en la respuesta de `tools/list`: `mem_save`, `mem_search`,
`mem_get_observation`, `mem_update` (los 4 originales) + `mem_context`,
`mem_session_summary`, `mem_suggest_topic_key`, `mem_save_prompt` (los 4 que
agregué para que `AGENTS.md` y los skills de Gentle-AI funcionen sin tocarlos).

## 2. Reemplazar el plugin

```bash
rm ~/.config/opencode/plugins/engram.ts
cp plugins/tonymem.ts ~/.config/opencode/plugins/tonymem.ts
```

El resto de `plugins/` (`model-variants.ts`, `skill-registry.ts`) **no se toca**.

`tonymem.ts` usa `bun:sqlite` (built-in de Bun, el runtime que ya usa
OpenCode para plugins) — no requiere `npm install` ni ningún paso de build.

## 3. `opencode.json` — dos cambios puntuales

No pisés tu `opencode.json` completo (tiene tus agentes/prompts actuales).
Aplicá manualmente estos dos cambios — están aislados y son fáciles de
mergear con un diff:

### 3a. Bloque `mcp`

Reemplazá:
```jsonc
"mcp": {
  "context7": { ... },
  "engram": {
    "command": ["/home/tony/.local/bin/engram", "mcp", "--tools=agent"],
    "type": "local"
  }
}
```

Por:
```jsonc
"mcp": {
  "context7": { ... },
  "tonymem": {
    "command": ["python3", "/home/tony/tools/tonymem/local-memory/server.py"],
    "type": "local",
    "environment": {
      "LOCAL_MEMORY_DB": "{cwd}/.tonymem/memory.db"
    }
  }
}
```

`{cwd}/.tonymem/memory.db` te da una base de datos **por proyecto** (misma
convención que ya documentaba el README de local-memory). Si preferís una
sola base global como tenías con Engram, usá una ruta fija en vez de `{cwd}`.

**Importante**: el plugin `tonymem.ts` lee la ruta de la base desde la misma
variable `LOCAL_MEMORY_DB`. Si cambiás esta ruta, el plugin la sigue
automáticamente — no hay que tocar el `.ts`.

### 3b. Model Router — `agent.<nombre>.model`

Este campo ya existe en el schema de OpenCode y ya es "autoritativo" según
tu propio `AGENTS.md` (`## Model Assignments` — sección que no toqué).
Hoy ningún agente lo tiene seteado; le agregué el modelo por rol:

| Rol | Modelo | Agentes |
|---|---|---|
| Planning | `ollama/qwen3-coder:30b` | `gentle-orchestrator`, `sdd-explore`, `sdd-propose`, `sdd-design`, `sdd-spec`, `sdd-tasks`, `sdd-init`, `sdd-onboard` |
| Implementation | `ollama/omnicoder:9b` | `sdd-apply` |
| Review | `ollama/deepseek-r1:14b` | `sdd-verify`, `review-readability`, `review-refuter`, `review-reliability`, `review-resilience`, `review-risk`, `jd-judge-a`, `jd-judge-b` |
| Execution | `ollama/ornith:9b` | `sdd-archive`, `jd-fix-agent` |

**Verificá los tags de Ollama antes de aplicar** (`ollama list`) — usé nombres
consistentes con tu stack existente, pero si tus tags reales son otros
(ej. `qwen3-coder:30b-instruct-q4_K_M`), ajustalos. Esto asume que ya tenés
un provider `ollama` configurado en tu OpenCode global (el mismo que usa tu
stack de OpenCode+Ollama actual) — si no, esos agentes van a fallar a resolver
el modelo y necesitás agregar el provider primero.

El archivo `opencode.json` incluido en este paquete tiene AMBOS cambios ya
aplicados sobre una copia idéntica del original (verifiqué con diff que el
resto — todos los `prompt`, `permission`, `default_agent`, `share` — es
byte-idéntico). Si tu `opencode.json` real no difiere del que subiste, podés
directamente reemplazarlo por el incluido. Si vos ya lo modificaste desde
que lo subiste, aplicá los diffs 3a/3b a mano.

## 4. `AGENTS.md` — un solo bloque

Reemplazá únicamente el contenido entre estos dos marcadores (no toques nada
fuera de ellos):

```
<!-- gentle-ai:engram-protocol -->
...
<!-- /gentle-ai:engram-protocol -->
```

Por el bloque incluido en el `AGENTS.md` de este paquete (mismo rango de
líneas). Dejé el nombre del marcador (`gentle-ai:engram-protocol`) sin tocar
a propósito — por si tenés tooling propio que busca ese string exacto para
gestionar el bloque.

Cambios dentro del bloque: "Engram" → "TonyMem" en el texto, y saqué las
menciones a `mem_judge` y `mem_review` — ninguna herramienta real las
implementaba (ni Engram las exponía en su whitelist de tools del plugin
original, `ENGRAM_TOOLS` en `engram.ts`), y ningún skill/prompt las llama.
Todo lo demás — `mem_save`, `mem_search`, `mem_get_observation`, `mem_update`,
`mem_context`, `mem_session_summary`, `mem_suggest_topic_key`,
`mem_save_prompt` — quedó exactamente igual, porque TonyMem los implementa
todos con el mismo nombre y misma firma.

## 5. Lo que NO se toca (y por qué funciona igual)

`commands/*.md`, `skills/*/SKILL.md`, `skills/_shared/*.md`, `prompts/sdd/*.md`
siguen diciendo "Engram" en el texto y siguen usando `artifact_store.mode:
"engram"` como valor literal del enum. **No los edité.** Esto es intencional:

- Los nombres de tool (`mem_search`, `mem_save`, etc.) son idénticos —
  cualquier llamada que esos archivos generen funciona contra TonyMem sin
  que el archivo sepa que Engram ya no existe.
- El string `"engram"` como valor de `artifact_store.mode` es un enum
  interno, no una referencia al binario — no rompe nada que TonyMem responda
  a esas llamadas.
- Si en algún momento querés rebrandear esos textos también, es un
  find-and-replace de "Engram" → "TonyMem" en esos archivos, pero no es
  necesario para que el sistema funcione — es puramente cosmético.

## 6. Verificación post-instalación

```bash
opencode mcp list          # debería mostrar "tonymem" conectado, no "engram"
```

Abrí una sesión, disparé cualquier flujo SDD (`/sdd-new algo-de-prueba`) y
confirmá:
1. Que el agente llama `mem_save` sin error (tool encontrada).
2. Que `~/.tonymem/memory.db` (o `{cwd}/.tonymem/memory.db` según cómo lo
   configuraste) se crea y crece.
3. Que cerrando la sesión ("listo", "dale, terminamos") dispara
   `mem_session_summary` — abrí el `.db` con `sqlite3` y buscá una fila
   `type='session-summary'`.

```bash
sqlite3 ~/.tonymem/memory.db "SELECT type, title, topic_key FROM observations ORDER BY updated_at DESC LIMIT 10;"
```

## 7. Code Indexer + Qdrant

```bash
cp -r code-index ~/tools/tonymem/code-index
```

Para Ollama + Qdrant, la forma recomendada ahora es `docker/` (Docker
Compose, con notas específicas para NixOS — Docker vs Podman, GPU opcional
vía `nvidia-container-toolkit`, healthchecks, y cómo verificar que
realmente están arriba):

```bash
cd docker
docker compose up -d
docker compose logs -f ollama-pull   # pull de nomic-embed-text + bge-m3, sale solo al terminar
```

Ver `docker/README.md` para el detalle completo (incluye el snippet exacto
de `configuration.nix` para habilitar Docker/Podman en NixOS). Si preferís
instalar Ollama nativo en vez de en contenedor, el comando manual de antes
sigue funcionando igual — nada en `code-index/`/`judgment-memory/` asume
Docker, solo hablan HTTP a `localhost:11434`/`localhost:6333`:

```bash
docker run -d --name qdrant -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
ollama pull bge-m3   # si no lo tenés ya
```

El `opencode.json` de este paquete ya trae registrado `mcp.code-index`
apuntando a `~/tools/tonymem/code-index/server.py` — mismo patrón que
`tonymem`, mismo `{cwd}` para que cada proyecto tenga su propia colección
Qdrant (`codeidx_<project>`) sin pisarse.

Para el primer índice completo de un repo grande, no lo dispares desde el
agente (bloquearía el turno) — corré el CLI directo una vez:

```bash
cd ~/tools/tonymem/code-index
python3 core.py index --path /ruta/a/tu/repo --project nombre-del-proyecto
```

Después de esa primera vez, `code_reindex` desde el agente es incremental
y rápido. Ver `code-index/README.md` para el detalle completo, y
`code-index/test_core.py` para correr el test de regresión (no necesita
Qdrant/Ollama corriendo, usa un mock).

El bloque `<!-- tony-ai:code-index-protocol -->` en `AGENTS.md` (agregado
al final, después del bloque de TonyMem) le enseña al orquestador cuándo
usar `code_search` en vez de `grep`/`glob`.

## 8. DCP (Dynamic Context Pruning)

**No lo reinventé.** `DCP` ya existe como plugin real y mantenido de OpenCode
(`Opencode-DCP/opencode-dynamic-context-pruning`, paquete npm
`@tarquinen/opencode-dcp`) — casi seguro el mismo que ya nombrabas en tu
stack. Reduce tokens de contexto exponiéndole al modelo un tool `compress`
(el modelo decide cuándo comprimir, no es la compactación estática de
OpenCode) más deduplicación automática de tool calls repetidas y purga de
inputs de tool calls que fallaron.

### Instalación (una sola vez, global)

```bash
opencode plugin @tarquinen/opencode-dcp@latest --global
```

Esto es un plugin **global** (afecta a todos tus proyectos de OpenCode, no
solo Tony-AI) — se instala con el CLI, no editando `opencode.json` a mano.

### Config específica de Tony-AI (por proyecto)

```bash
cp -r .opencode ~/tu-repo/.opencode
```

`.opencode/dcp.jsonc` en este paquete tiene overrides pensados para tu setup:

- **`modelMaxLimits`/`modelMinLimits` por modelo** en vez de un límite
  global — usa las mismas strings `ollama/qwen3-coder:30b` etc. que ya
  quedaron en `agent.*.model`. **Verificá esto vos**: los porcentajes son
  sobre lo que tu config de OpenCode declara como ventana de contexto del
  modelo, que a su vez depende del `num_ctx` real que configuraste en
  Ollama — no del máximo teórico del modelo. Corré `ollama show <modelo>`
  y ajustá si no coincide.
- **`nudgeForce: "strong"`** en vez del default `"soft"` — modelos locales
  más chicos son menos proactivos decidiendo comprimir por su cuenta que un
  frontier model, así que empujé el nudge más fuerte.
- **`protectedFilePatterns`** incluye `openspec/changes/**` — ahí vive el
  proposal/design/tasks/specs de una sesión SDD activa (ver
  `skills/_shared/sdd-status-contract.md`) cuando `artifact_store` es
  `openspec` o `hybrid`. Nunca queremos que DCP pode esos archivos a mitad
  de una sesión larga.
- **`turnProtection`** habilitado (4 turnos) — da un colchón antes de que
  algo se pode, útil con modelos locales donde una tool call reciente puede
  necesitarse de nuevo un par de turnos después.

Validé `.opencode/dcp.jsonc` contra el `dcp.schema.json` real del plugin —
es JSON válido y cumple el schema completo (`additionalProperties: false`
en todos los objetos, así que cualquier typo de clave lo hubiera rechazado).

### Qué NO toqué

`AGENTS.md` no necesita ningún cambio para esto — DCP inyecta sus propias
instrucciones de sistema y expone su propio tool `compress` de forma
autónoma; no depende de nada del protocolo SDD/TonyMem para funcionar.

## 9. Double Review (judgment-day) — dos correcciones reales

**No construí nada nuevo.** Double Review ya existe en Gentle-AI:
`skills/judgment-day/SKILL.md` + agentes `jd-judge-a`/`jd-judge-b`/
`jd-fix-agent` en `opencode.json`. Al leerlo con cuidado encontré dos
problemas reales y los corregí:

### 9a. Los dos jueces ciegos ahora usan modelos distintos

`jd-judge-a` y `jd-judge-b` tienen prompts **byte-idénticos** (verificado
programáticamente) — por diseño, ambos corren con el mismo criterio de
forma aislada. El problema lo introduje yo en el paso del Model Router: les
había asignado el mismo modelo (`deepseek-r1:14b`) a los dos. El propio
skill dice *"two-judge agreement is the corroboration mechanism"* — pero
dos instancias del mismo modelo con el mismo prompt no son corroboración
independiente, son la misma opinión preguntada dos veces.

Corregido en `opencode.json`:
- `jd-judge-a` → `ollama/deepseek-r1:14b` (sin cambios)
- `jd-judge-b` → `ollama/qwen3-coder:30b` (linaje de entrenamiento distinto)

Verificado que el resto de `opencode.json` (todos los `prompt`,
`permission`) sigue byte-idéntico al original — solo cambió ese campo.

### 9b. El contrato de ledger que faltaba

`judgment-day/SKILL.md` referencia `../_shared/review-ledger-contract.md`
como *"canonical transaction, ledger, persistence, and lifecycle contract"*.
Ese archivo **no existe** en ningún lado del proyecto base — lo confirmé
listando los 68 archivos del zip completo. Sin él, cada corrida de Judgment
Day (y de la revisión 4R ordinaria, que comparte los mismos 5 artefactos:
`transaction`, `ledger`, `receipt`, `chain-bundle`, `gate-context`) tiene que
improvisar el schema en vez de tener uno consistente.

Agregué `skills/_shared/review-ledger-contract.md`. No inventé mecánica
nueva — es la consolidación de reglas que ya estaban dispersas y afirmadas
en `sdd-status-contract.md` (paths/topics exactos por artifact store,
`reviewGate` enum), `sdd-archive/SKILL.md` (qué debe matchear el receipt),
`sdd-verify/SKILL.md` (qué artefactos no deben existir antes de terminal),
y `judgment-day/references/prompts-and-formats.md` (shape de los findings y
del veredicto) — todo en un solo lugar, en el mismo formato que los otros
contratos de `_shared/`.

**Esto SÍ es un archivo nuevo dentro de `skills/_shared/`** — la única
excepción a "no tocar skills" en todo este overlay, y es estrictamente
aditiva: nada existente se modifica, se llena una referencia que ya existía
rota.

### Qué no toqué

Los 5 agentes de la revisión 4R ordinaria (`review-risk`, `review-readability`,
`review-reliability`, `review-resilience`, `review-refuter`) — su mecanismo
de corroboración es distinto (el refuter corrobora *afirmaciones*, no
vuelve a derivar el juicio desde cero como los jueces de Judgment Day), así
que diversificar modelos ahí no tiene el mismo fundamento y no lo apliqué
sin que me lo pidas explícitamente.

## 10. Judgment Day Memory Bridge

Conecta TonyMem/Qdrant con Judgment Day: recall de juicios pasados antes de
lanzar a los jueces, y persistencia del resultado (ledger + embedding +
Qdrant) cuando la lineage llega a estado terminal.

### 10a. Copiar el servidor y el plugin

```bash
cp -r judgment-memory ~/tools/tonymem/judgment-memory
cp plugins/qdrant.ts ~/.config/opencode/plugins/qdrant.ts
cp plugins/judgment-memory.ts ~/.config/opencode/plugins/judgment-memory.ts
```

`judgment-memory.ts` importa `./qdrant` (import relativo) — los dos archivos
tienen que quedar en el mismo directorio de plugins, junto a `tonymem.ts`.
Igual que `tonymem.ts`, usa `bun:sqlite` — no hace falta `npm install`.

Verificá que el servidor MCP corre standalone:

```bash
cd ~/tools/tonymem/judgment-memory
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | python3 server.py
```

Deberías ver 4 tools: `jd_recall`, `jd_record`, `jd_history`, `jd_stats`.

### 10b. `opencode.json` — un bloque nuevo en `mcp`

Ya viene incluido en el `opencode.json` de este paquete, al lado de
`tonymem` y `code-index`:

```jsonc
"judgment-memory": {
  "command": ["python3", "/home/tony/tools/tonymem/judgment-memory/server.py"],
  "type": "local",
  "environment": {
    "JUDGMENT_MEMORY_DB": "{cwd}/.tonymem/judgment-memory.db",
    "TONY_OLLAMA_URL": "http://localhost:11434",
    "TONY_QDRANT_URL": "http://localhost:6333",
    "TONY_EMBED_MODEL": "nomic-embed-text"
  }
}
```

Usa el mismo Qdrant/Ollama que ya levantaste para `code-index` en la sección
7 — no hace falta un segundo contenedor. Sí usa un modelo de embedding
distinto (`nomic-embed-text` en vez de `bge-m3`) porque acá se embeben
lecciones en texto natural corto, no chunks de código; si preferís usar el
mismo modelo para ambos, cambiá `TONY_EMBED_MODEL` acá (no afecta a
`code-index`, cada MCP tiene su propio bloque `environment`).

### 10c. `judgment-day/SKILL.md` — 2 líneas de diff

Única excepción, junto con `review-ledger-contract.md`, a "no tocar skills".
El diff es puramente aditivo:
- Un ítem en `## Hard Rules` pidiendo `jd_recall` antes de construir el target.
- Paso 1 nuevo en `## Execution Steps` (`jd_recall`) y paso final nuevo
  (`jd_record` tras el receipt terminal) — el resto de los pasos solo se
  renumeraron, ningún Decision Gate ni Hard Rule existente cambió de
  significado.

Si ya tenés tu propio `judgment-day/SKILL.md` modificado, aplicá el diff a
mano en vez de reemplazar el archivo completo — buscá el marcador
`jd_recall`/`jd_record` en el `SKILL.md` de este paquete para ubicar
exactamente qué se agregó.

### 10d. Comandos nuevos

```bash
cp commands/memory-search.md commands/memory-stats.md commands/judgment-history.md \
  ~/tu-repo/commands/
```

`/judgment-history` es el único de los tres sin dependencia de Qdrant/Ollama
(lee `jd_history`, que es SQLite puro) — útil para confirmar que `jd_record`
está persistiendo antes de meterte a depurar embeddings.

### Verificación

```bash
opencode mcp list          # debería mostrar "judgment-memory" conectado
```

**Antes de confiar en el plugin dentro de una sesión real**, corré el smoke
test contra tu Ollama/Qdrant reales — esto es lo único que faltaba validar
de verdad (el cliente TS/Bun solo estaba tipado con `tsc`, nunca ejecutado):

```bash
cd ~/tools/tonymem/judgment-memory
bun run scripts/verify-qdrant.ts
```

(Si copiaste también `docker/` y `Makefile` a la raíz de tu checkout,
`make verify-qdrant` hace lo mismo desde ahí.)

Debería terminar con `ALL CHECKS PASSED` y limpiar su colección de prueba
(`jdmem___verify_qdrant_ts__`) sola. Si falla acá, no tiene sentido seguir
al siguiente paso — el problema está en la conexión a Ollama/Qdrant, no en
el plugin.

Disparar Judgment Day una vez (`"juzgar esto: <target>"`), confirmar en la
transcripción que se llamó `jd_recall` antes de lanzar a los jueces y
`jd_record` después del receipt terminal, y:

```bash
python3 ~/tools/tonymem/judgment-memory/ledger.py stats --project <tu-proyecto>
```

debería mostrar `total_judgments: 1`.

### Qué NO toqué

`skills/_shared/review-ledger-contract.md` no cambió — el ledger de
`review/finalize` (transacciones SDD/4R/Judgment Day) y el ledger de
`judgment-memory` son cosas distintas a propósito: uno es el estado de una
corrida en curso (efímero, se archiva), el otro es memoria de largo plazo
entre corridas (persistente, se acumula). Mezclarlos hubiera acoplado el
protocolo de transacciones a una decisión de storage que puede cambiar.

## Overlay completo

Con esto, los 4 nodos del `Context Pipeline`/`Double Review` del diagrama
original están resueltos: TonyMem, Code Indexer + Qdrant, DCP (integrado,
no reinventado), y Double Review (existente, corregido) — más el Judgment
Day Memory Bridge (sección 10) conectando TonyMem/Qdrant al flujo de
Judgment Day. Cualquier cosa que sigas queriendo ajustar, decímelo.
