# Testing de Tony-AI

## Suite local

La suite local no necesita Ollama, Qdrant ni Docker. Soporta dos modos de ejecución para Python: **`pytest`** (para desarrollo y CI) y un **runner standalone** basado exclusivamente en la librería estándar (`tools/run-python-tests.py`, cero dependencias). Los tests TypeScript usan Bun.

La ejecución recomendada es:

```bash
python3 -m pip install -r requirements-dev.txt
make test
```

`make test` comienza con un preflight que verifica las dependencias y convenciones de descubrimiento. Luego ejecuta la suite Python (usando `pytest` si está presente o cayendo al runner standalone `tools/run-python-tests.py`), corre los tests TypeScript (`*.test.ts`) con Bun y valida las referencias de configuración.

### Ejecución directa por runner

```bash
# 1. Con Pytest (desarrollo y CI)
python3 -m pytest tests -v

# 2. Sin Pytest (Runner Standalone con cero dependencias)
python3 tools/run-python-tests.py tests

# 3. Tests TypeScript con Bun
bun test tests
```

Se pueden ejecutar las suites por separado mediante Makefile:

```bash
make test-python
make test-ts
make test-kernel
```

La nomenclatura `.test.ts` permite que `bun test tests` descubra los tests TypeScript automáticamente. `make test-kernel` es un target focalizado para depurar el Kernel en aislamiento.

## Categorías

Los tests Python nuevos están etiquetados para poder aislarlos durante el diagnóstico:

```bash
python3 -m pytest -m concurrency
python3 -m pytest -m mcp
python3 -m pytest -m "not concurrency"
```

La categoría `concurrency` utiliza procesos separados, una barrera de arranque y el helper transaccional `update_orchestrator`. Verifica que las actualizaciones concurrentes no se pierdan, que los estados corruptos vuelvan a un estado fresco explícito, que un `.tmp` huérfano no reemplace el estado válido y que una escritura interrumpida conserve el archivo anterior.

La categoría `mcp` verifica el contrato JSON-RPC del servidor: parse errors, requests inválidos, `initialize`, `tools/list`, `tools/call`, tools desconocidas, excepciones de handlers, métodos desconocidos, notificaciones y `ping`.

## Cobertura

La cobertura Python se genera con `coverage` y tiene un umbral inicial de 40%:

```bash
make coverage-python
```

El reporte se escribe en `coverage.xml`. La cobertura TypeScript se genera con la versión fijada de Bun y queda en formato LCOV:

```bash
make coverage-ts
```

El archivo se escribe en `coverage-bun/lcov.info`. Ambos artefactos se publican desde CI en el job de Python 3.12.

El umbral es deliberadamente moderado. Su función inicial es detectar módulos no ejercitados y evitar regresiones silenciosas; debe incrementarse cuando se incorporen pruebas para los servidores MCP, paths de error y servicios externos.

## Tests del plugin judgment-memory

`tests/judgment_memory_hooks.test.ts` contiene 24 escenarios y importa el plugin real para ejecutar:

```ts
const hooks = await JudgmentMemory(ctx)
await hooks["chat.message"](input, output)
await hooks["tool.execute.after"](input, output)
await hooks["experimental.chat.system.transform"](input, output)
```

El test usa SQLite temporal y un servidor HTTP local compatible con los endpoints de Ollama y Qdrant. De ese modo comprueba filas persistidas, upserts, embeddings, búsqueda semántica, inyección consumible del recall, thresholds, filtros de tools, formatos alternativos del parser, outputs estructurados de `Task`, transformación del prompt y degradación cuando falla el indexado.

El plugin también expone `createJudgmentMemory(ctx, overrides)` para pruebas que necesiten reemplazar dependencias concretas sin mocks globales. El entrypoint de producción continúa siendo `JudgmentMemory(ctx)`.

## Bundles materializados de prompts

La documentación técnica completa está en `ARCHITECTURE.md`. Acá se resumen los puntos relevantes para testing:

- `phase-manifest.json` es la fuente única de composición por fase.
- `tools/prompt-bundler.ts` expande includes y skills en build-time; `tools/build-prompts.ts` es la CLI.
- Los bundles se escriben en `prompts/generated/phases/<phase>.md` y el orquestador en `prompts/generated/tony-orchestrator.md`.
- `prompt-manifest.json` y `prompt-snapshot.json` registran SHA-256 y tamaño para detectar drift.

### Checks recomendados

```bash
make build-prompts       # genera el bundle raíz y los 18 bundles de fase
make check-prompts       # falla si falta un bundle, hay drift o quedan tokens sin resolver
bun test tests/prompt_bundler.test.ts
bun run tools/validate-config.ts
```

`make test` incluye `make check-prompts`, por lo que modificar un include o skill sin regenerar los bundles bloquea la suite local y CI. El pre-commit hook ejecuta `make check-prompts` antes de cada commit.

### Errores comunes

- `{file:...}` pendiente en `prompts/agents/tony-orchestrator.md`, `dynamic-launcher.md` o `phase-launcher.md`: migrar a `{{include:...}}` o marcar como documentación plana.
- Agentes en `opencode.json` sin bundle en `prompt-manifest.json`: ejecutar `make build-prompts` o `make generate-agents`.
- Drift después de editar `skills/_shared/*.md`: ejecutar `make build-prompts` y verificar con `make check-prompts`.

### CI
CI fija Bun `1.3.14` y prueba Python 3.10, 3.11 y 3.12. Cada versión ejecuta `make test`; Python 3.12 genera además los reportes de cobertura. La build Docker continúa en un job separado.
Elorden recomendado es:

```bash
make check-prompts
make test-all
make coverage
```

`check-prompts` es barato y detecta desvíos antes de correr la suite completa. Los reportes deben publicar `prompt-manifest.json` y `prompt-snapshot.json` como artifacts.

## Smoke tests externos

Los tests que requieren servicios reales quedan separados de la suite local:

```bash
make verify-qdrant
make health
```

Estos comandos necesitan los servicios configurados por el proyecto. Un fallo de conectividad, modelo o contenedor debe clasificarse como fallo de infraestructura y no como fallo de la suite unitaria.
