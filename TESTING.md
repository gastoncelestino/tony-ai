# Tony-AI — Testing

## 1. Objetivo

Tony-AI separa las pruebas deterministas del código de los smoke tests que requieren infraestructura externa.

La estrategia tiene cuatro capas:

```text
                         Tony-AI Testing
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
       Python             TypeScript          Configuración
        tests                tests              / OpenCode
          │                   │                   │
       pytest              Bun             validate-config
          │
          └── runner standalone
              sin Pytest

                     ┌───────────────────┐
                     │ Smoke / Health    │
                     │ Ollama + Qdrant   │
                     └───────────────────┘
```

La suite local está diseñada para ejecutarse sin Ollama, Qdrant ni Docker. Los servicios externos se validan por separado con `make verify-qdrant` y `make health`.

## 2. Prerrequisitos de la suite

Para ejecutar la suite completa se necesita:

- Python 3.10+.
- Bun 1.3.14 en CI; versiones compatibles de Bun pueden usarse localmente.
- Dependencias de `requirements-dev.txt` para pytest y cobertura.

Instalación:

```bash
python3 -m pip install -r requirements-dev.txt
```

O, para una instalación completa del proyecto:

```bash
./scripts/setup.sh
```

La suite Python tiene además un runner standalone basado únicamente en la librería estándar.

## 3. Comando recomendado

El comando principal es:

```bash
make test
```

`make test` realiza, en este orden general:

1. verifica las dependencias mínimas para la suite;
2. verifica las convenciones de descubrimiento de tests;
3. ejecuta los tests Python;
4. ejecuta los tests TypeScript con Bun;
5. valida `opencode.json`, prompts, agentes, MCP y referencias `{file:...}`.

**Importante:** `make test` necesita Bun porque incluye la suite TypeScript. No necesita Ollama, Qdrant ni Docker.

Para diagnóstico detallado, se recomienda ejecutar las suites directamente en lugar de depender del fallback del Makefile:

```bash
python3 -m pytest tests -v
bun test tests
bun run tools/validate-config.ts
```

## 4. Tests Python

### Pytest

Para desarrollo y CI:

```bash
python3 -m pytest tests -v
```

### Runner standalone

Permite ejecutar la suite Python sin instalar Pytest:

```bash
python3 tools/run-python-tests.py tests
```

El runner está pensado para conservar una vía de validación mínima basada solo en stdlib.

### Tests focalizados

Ejemplos:

```bash
python3 -m pytest tests/test_kernel_state_machine.py -v
python3 -m pytest tests/test_kernel_integration.py -v
python3 -m pytest tests/test_code_index_core.py -v
python3 -m pytest tests/test_judgment_memory_ledger.py -v
python3 -m pytest tests/test_sdd_flow_e2e.py -v
```

## 5. Tests TypeScript

Los tests TypeScript usan Bun y el patrón de descubrimiento `*.test.ts`:

```bash
bun test tests
```

Tests focalizados:

```bash
bun test tests/tony_kernel_hooks.test.ts
bun test tests/tony_kernel_integration.test.ts
bun test tests/tony_kernel_e2e.test.ts
bun test tests/judgment_memory_hooks.test.ts
```

`make check-test-discovery` rechaza archivos TypeScript que no sigan la convención de descubrimiento y también valida los nombres de los tests Python.

## 6. Makefile

Targets principales:

```bash
make test
make test-python
make test-ts
make test-kernel
make test-all
```

### `make test`

Suite normal: Python + TypeScript + validación de configuración.

### `make test-python`

Ejecuta la suite Python, usando pytest cuando está disponible y el runner standalone como fallback.

### `make test-ts`

Ejecuta todos los tests TypeScript con Bun.

### `make test-kernel`

Foco en Kernel y flujo SDD, incluyendo tests Python y TypeScript relacionados.

### `make test-all`

Ejecuta `make test` y agrega `make test-kernel`.

## 7. Cobertura

La cobertura Python usa `coverage` y tiene un umbral inicial de **40%**:

```bash
make coverage-python
```

El reporte se genera en:

```text
coverage.xml
```

La cobertura TypeScript usa el soporte de cobertura de Bun:

```bash
make coverage-ts
```

El reporte se genera en:

```text
coverage-bun/lcov.info
```

La cobertura completa se ejecuta con:

```bash
make coverage
```

El umbral de 40% es deliberadamente inicial: sirve para detectar regresiones y módulos sin cobertura sin convertir la cobertura en un objetivo artificial. Debe aumentarse a medida que se incorporen pruebas adicionales sobre paths de error, MCP y servicios externos.

## 8. Categorías de tests

Algunos tests Python utilizan markers para aislar problemas específicos:

```bash
python3 -m pytest -m concurrency
python3 -m pytest -m mcp
python3 -m pytest -m "not concurrency"
```

### `concurrency`

Comprueba escenarios de concurrencia del estado persistente del Kernel: procesos concurrentes, actualizaciones que no deben perderse, recuperación ante estado corrupto, archivos temporales huérfanos y escrituras interrumpidas.

### `mcp`

Comprueba el contrato JSON-RPC de los MCP servers: `initialize`, `tools/list`, `tools/call`, requests inválidos, tools desconocidas, excepciones de handlers, métodos desconocidos, notificaciones y `ping`.

## 9. Tony Kernel y enforcement

El Kernel tiene pruebas específicas porque no es solo una librería de estado: aplica reglas del workflow SDD.

La cobertura relevante incluye:

- máquina de estados de las 8 fases SDD;
- Phase Gate;
- Artifact Gate;
- Scope Guard;
- retry budget;
- checksums de fase;
- evidencia y task ledger;
- integración plugin TypeScript ↔ Kernel Python;
- comportamiento fail-closed;
- flujo E2E `explore → archive`.

Tests principales:

```text
tests/test_kernel_state_machine.py
tests/test_kernel_integration.py
tests/test_kernel_cli.py
tests/test_kernel_hardening.py
tests/test_kernel_enforcement.py
tests/test_sdd_flow_e2e.py
```

El flujo SDD E2E se puede ejecutar directamente con:

```bash
make verify-sdd-flow
```

Este test es local y no debe confundirse con los smoke tests que requieren Ollama o Qdrant.

## 10. MCP servers

Los cuatro MCP servers deben mantener un contrato JSON-RPC estable:

```text
local-memory/server.py
code-index/server.py
judgment-memory/server.py
kernel/mcp_server.py
```

El health check los prueba enviando `initialize`, mientras que los tests unitarios/integración cubren casos de protocolo y herramientas.

La validación de configuración también comprueba que los MCP registrados en `opencode.json` y sus referencias sean consistentes.

## 11. Judgment Memory

`tests/judgment_memory_hooks.test.ts` importa el plugin real y prueba sus hooks con SQLite temporal y un servidor HTTP local compatible con Ollama/Qdrant.

El harness cubre, entre otros:

- persistencia del ledger;
- normalización de juicios;
- embeddings;
- upserts en Qdrant;
- recuperación semántica;
- thresholds y filtros;
- inyección del recall en contexto;
- captura de resultados estructurados;
- transformación del prompt;
- degradación cuando el indexado externo falla.

Esto permite probar el comportamiento del plugin sin depender de una instancia real de Ollama o Qdrant.

## 12. Code Indexer

El Code Indexer usa `tree-sitter` obligatoriamente para chunking estructural.

El test principal es:

```bash
python3 -m pytest tests/test_code_index_core.py -v
```

La suite utiliza HTTP local/mocks para probar embeddings, indexación incremental y comportamiento frente a cambios sin necesitar un Qdrant real.

No se considera válido solucionar un fallo del indexador cambiando `TONY_INDEX_CHUNKER` a `regex`: ese modo no forma parte del contrato soportado del proyecto.

## 13. Configuración y prompts SDD

La configuración se valida directamente; no existe una etapa de generación o materialización de bundles de prompts.

Ejecutar:

```bash
bun run tools/validate-config.ts
```

La validación comprueba, entre otras cosas:

- sintaxis y estructura de `opencode.json`;
- agentes configurados;
- prompts fuente;
- referencias `{file:...}`;
- recursos compartidos;
- servidores MCP;
- convenciones de discovery.

### Errores frecuentes

- `{file:...}` apunta a un archivo inexistente → corregir la referencia.
- Agente sin prompt fuente válido → agregar/corregir el archivo.
- Referencia a un bundle o manifest eliminado → usar el prompt fuente actual.
- Test con nombre no descubrible → respetar las convenciones de `tests/`.

## 14. CI

La CI ejecuta la suite en:

```text
Python 3.10
Python 3.11
Python 3.12
Bun 1.3.14
```

Cada versión ejecuta:

```bash
make test
```

Python 3.12 ejecuta además la cobertura y publica:

```text
coverage.xml
coverage-bun/lcov.info
```

Existe un job separado que comprueba el build de Docker.

La CI no necesita Ollama ni Qdrant para la suite local.

## 15. Smoke tests e infraestructura externa

Los checks que necesitan infraestructura real están separados de `make test`.

### Qdrant

```bash
make verify-qdrant
```

Comprueba el roundtrip real de embeddings/indexación/búsqueda contra Ollama y Qdrant.

### Health check completo

```bash
make health
```

`health.sh` verifica:

- `opencode.json` y portabilidad de rutas;
- los cuatro MCP servers mediante `initialize`;
- Ollama y los modelos de embeddings;
- Qdrant (`/readyz` y `/collections`);
- directorios locales escribibles;
- roundtrip de embeddings mediante `verify-qdrant.ts`.

Un fallo de `make health` puede ser un problema de infraestructura aunque `make test` pase correctamente.

## 16. Limpieza

Para eliminar bases locales y reportes de cobertura generados por las pruebas:

```bash
make clean
```

`make clean` no debe utilizarse como mecanismo de recuperación general del proyecto: elimina estado local deliberadamente.

## 17. Flujo recomendado antes de un commit

Para un cambio normal:

```bash
make test
bun run tools/validate-config.ts
git diff --check
```

Si el cambio afecta Kernel, MCP, configuración o infraestructura:

```bash
make test-all
make health
```

Antes de commit debe ejecutarse además GGA según las convenciones del proyecto.

## 18. Principios de la estrategia

1. **Local-first:** la mayor parte de la suite debe poder ejecutarse sin servicios externos.
2. **Deterministic-first:** los contratos del Kernel, MCP, configuración y artifacts se prueban de forma reproducible.
3. **Infrastructure-separated:** Ollama, Qdrant y Docker se validan mediante smoke tests específicos.
4. **Real-plugin coverage:** los plugins críticos se prueban utilizando sus entrypoints reales, no solamente mocks de alto nivel.
5. **Fail-closed:** los tests del Kernel deben detectar cualquier regresión que permita avanzar cuando faltan condiciones obligatorias.
6. **Incremental coverage:** el umbral de cobertura aumenta junto con la cobertura real de paths de error y componentes externos.
