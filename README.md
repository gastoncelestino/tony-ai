# Integración: motor de descomposición atómica en tony-ai (rama `ai`)

Reemplaza el bootstrap de un solo shot (`bootstrapPrompt()` delegado a
`sdd-explore`) por un motor recursivo Python que descompone en N llamadas
chicas, inspirado en `Nichonauta/atomic_ai`. `kernel/boundary.py` **no se
modifica** — el output respeta el mismo contrato `{"tasks":[...]}`.

## Archivos en este paquete

- `kernel/atomic_decompose.py` — **nuevo**, motor de descomposición recursiva.
- `kernel/protocol.ts` — modificado, campo opcional `decomposedAtDepth`.
- `kernel/authorize-execution.ts` — modificado, llama al motor en vez de
  delegar a `sdd-explore`.
- `protocol.ts.diff`, `authorize-execution.ts.diff`, `combined.patch` —
  mismos cambios en formato diff, por si preferís aplicar con `git apply`
  en vez de copiar los archivos completos.

## Cómo aplicar

### Opción A — copiar archivos completos (más simple)

Desde la raíz de tu repo, rama `ai`:

```bash
cp kernel/atomic_decompose.py   <tu-repo>/kernel/atomic_decompose.py
cp kernel/protocol.ts           <tu-repo>/kernel/protocol.ts
cp kernel/authorize-execution.ts <tu-repo>/kernel/authorize-execution.ts
```

### Opción B — aplicar el patch

Desde la raíz de tu repo:

```bash
git apply combined.patch
```

Si falla por line endings o whitespace, probá:

```bash
git apply --whitespace=fix combined.patch
```

`atomic_decompose.py` es un archivo nuevo — el patch no lo incluye, copialo
a mano con el comando de la Opción A.

## Config nueva — agregar a `.env`

```
TONY_MAX_DECOMPOSITION_DEPTH=3
TONY_MAX_SUBTASKS_PER_NODE=6
TONY_LLM_URL=http://127.0.0.1:8080/v1/chat/completions
TONY_DECOMPOSE_MODEL=qwen-3.8-9b
TONY_DECOMPOSE_TIMEOUT=60
```

`qwen-3.8-9b` a propósito — es tu modelo chico con `reasoning-budget`
acotado, no uses `qwen3-coder-30b` para el chequeo de atomicidad, es
desperdiciar tu modelo más caro en una decisión binaria por nodo.

## Cómo probar ANTES de tocar OpenCode

Con `llama-swap` corriendo en :8080, probá el módulo solo, sin pasar por
el kernel entero:

```bash
cd <tu-repo>
echo '{"description": "agregar rate limiting al endpoint de login con Redis", "phase": "explore"}' \
  | TONY_DECOMPOSE_MODEL=qwen-3.8-9b python3 -m kernel.atomic_decompose
```

Esperás un JSON tipo:

```json
{"tasks": [
  {"id": "atomic-1", "description": "...", "phase": "explore", "dependencies": [], "files": []},
  {"id": "atomic-2", "description": "...", "phase": "design", "dependencies": ["atomic-1"], "files": []},
  ...
]}
```

Si el modelo devuelve basura o timeoutea, el módulo cae a fallback seguro
(trata la tarea como atómica) en vez de romper — revisá `stderr` para ver
si hubo fallback silencioso, y ajustá el prompt en `ATOMICITY_PROMPT` si
ves que descompone de más o de menos.

## Qué cambia en el flujo real (una vez aplicado)

1. Primer `task()` de una sesión nueva → `authorizeExecution()` detecta
   `SDD state unavailable` → `prepareBootstrap()` (sin cambios).
2. **Antes**: se delegaba una tarea a `sdd-explore` pidiéndole el TaskSet
   completo en una respuesta.
   **Ahora**: `runAtomicDecompose()` spawnea
   `python3 -m kernel.atomic_decompose`, que hace su propia recursión
   contra `llama-swap` directamente (sin pasar por el orquestador de
   OpenCode), y devuelve el TaskSet ya armado.
3. `completeBootstrap()` recibe ese output — mismo código que antes, sin
   cambios.
4. `boundary.py::op_complete_bootstrap` valida con `_valid_task()` — mismo
   código, sin cambios.

## Rollback

Si algo no anda, revertí solo copiando los 2 archivos originales que
bajaste de la rama `ai` (`protocol.ts`, `authorize-execution.ts`) y borrando
`atomic_decompose.py`. No tocamos `boundary.py`, `evidence-ledger.ts`,
`evidence-gate.ts`, `execution-graph.ts` ni `trace.ts` — nada de eso
necesita rollback.
