# Testing de Tony-AI

## Suite local

La suite local no necesita Ollama, Qdrant ni Docker. Los tests de Python usan pytest y los tests TypeScript usan Bun. La ejecución recomendada es:

```bash
python3 -m pip install -r requirements-dev.txt
make test
```

`make test` comienza con un preflight que verifica que `pytest` y Bun estén instalados y que todos los archivos de test cumplan las convenciones de descubrimiento. Luego descubre todos los archivos Python bajo `tests/`, ejecuta todos los archivos TypeScript con sufijo `.test.ts` y valida las referencias de `opencode.json`, prompts, skills y servidores MCP.

Si falta una dependencia, el comando muestra cómo instalarla en lugar de fallar con un `ModuleNotFoundError` poco descriptivo:

```bash
python3 -m pip install -r requirements-dev.txt
make check-test-deps
make check-test-discovery
```

También se pueden ejecutar las suites por separado:

```bash
make test-python
make test-ts
make test-kernel
```

La nomenclatura `.test.ts` es intencional. Permite que `bun test tests` descubra la suite automáticamente y evita que el Makefile y CI mantengan listas manuales divergentes. `make test-kernel` es un target focalizado para depurar solo el Kernel; no se invoca desde `make test` porque sus casos ya están incluidos en el descubrimiento global y duplicarlos haría más lenta la suite.

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

Los includes internos de `prompts/agents/tony-orchestrator.md` usan la sintaxis propia `{{include:...}}` y se expanden antes de que OpenCode cargue la configuración. OpenCode recibe solamente `prompts/generated/tony-orchestrator.md`; los agentes de fase reciben `prompts/generated/phases/<phase>.md`.

El manifiesto `prompts/agents/includes/phase-manifest.json` es la fuente única de composición por fase. Los prompts inline de review y Judgment Day están externalizados en `prompts/agents/phase-prompts/` para evitar duplicación dentro de `opencode.json`.

```bash
make build-prompts       # genera el bundle raíz y los 18 bundles de fase
make check-prompts       # falla si falta un bundle, hay drift o quedan tokens sin resolver
bun test tests/prompt_bundler.test.ts
```

El resolver resuelve rutas relativas al archivo que contiene el include, registra hashes SHA-256, deduplica dependencias, rechaza ciclos, path traversal, nombres dinámicos y profundidad excesiva, y produce salida byte-identical para el mismo árbol de fuentes. `make test` incluye `make check-prompts`, por lo que modificar un prompt sin regenerar los bundles bloquea CI.

## Smoke tests externos

Los tests que requieren servicios reales quedan separados de la suite local:

```bash
make verify-qdrant
make health
```

Estos comandos necesitan los servicios configurados por el proyecto. Un fallo de conectividad, modelo o contenedor debe clasificarse como fallo de infraestructura y no como fallo de la suite unitaria.

## CI

CI fija Bun `1.3.14` y prueba Python 3.10, 3.11 y 3.12. Cada versión ejecuta `make test`; Python 3.12 genera además los reportes de cobertura. La build Docker continúa en un job separado.
