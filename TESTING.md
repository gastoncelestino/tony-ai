# Tony-AI — Testing

## Estrategia general

```text
                    Tony-AI Testing
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
    Python tests      TypeScript tests   Configuración
    (deterministas)   (deterministas)    (estructura)
        │                 │                   │
     pytest          Bun + tree-sitter   validate-config
     + runner        + real plugins       + opencode.json
     standalone
        │
    Sin Pytest
    (solo stdlib)
        │
        └─── Fallback para CI aislada
        
        ┌──────────────────────────────┐
        │   Smoke tests (separados)    │
        │   Ollama + Qdrant (opcional) │
        │   make verify-qdrant         │
        │   make health                │
        └──────────────────────────────┘
```

## 0. Quick Start

**Solo necesitas verificar que tu cambio no rompió nada:**

```bash
make test
```
Ejecuta la suite local estándar (Python + TypeScript + validación de config) sin Ollama, Qdrant ni Docker.

**Cambios críticos (Kernel, MCP, config, infraestructura):**

```bash
make test-all
make health
```

Eso es el 95% de lo que necesitas.

---

## 1. Qué necesito

### Requisitos mínimos

- **Python 3.10+** (CI testea 3.10, 3.11, 3.12)
- **Bun 1.3.14** (o compatible en local)
- **sqlite3** (para bases persistentes)
- **make** (Makefile)

### Instalación

**Opción 1: Setup completo**

```bash
./scripts/setup.sh
```

**Opción 2: Manual**

```bash
python3 -m pip install -r requirements-dev.txt
bun install  # si no está instalado
```

### Verificar instalación

```bash
python3 --version        # 3.10+
bun --version            # 1.3.14+
python3 -m pytest --version
make --version
```

### Nota sobre pytest

Pytest es recomendado pero NO obligatorio. Si no está disponible, el Makefile usa automáticamente `tools/run-python-tests.py` (runner standalone basado en stdlib).

```bash
# Ver si pytest está disponible
make check-test-deps
```

---

## 2. Qué comando usar según mi cambio

| Mi cambio | Ejecutar | Nota |
|-----------|----------|------|
| Feature/bugfix normal | `make test` | Sin infraestructura |
| Kernel, MCP, config | `make test-all` | Incluye tests SDD E2E |
| Kernel + infraestructura | `make test-all` + `make health` | Requiere Ollama, Qdrant |
| Code Indexer | `make test-all` | tree-sitter es obligatorio |
| Judgment Memory | `make test-all` | Incluye hooks con mocks |
| Solo Python | `make test-python` | No necesita Bun |
| Solo TypeScript | `make test-ts` | Necesita Bun |
| Verificar SDD E2E | `make verify-sdd-flow` | Solo Python, local |
| Antes de hacer push | `make test` + `bun run tools/validate-config.ts` + `git diff --check` | Check pre-commit |

---

## 3. Cómo ejecutar tests

### Todas las suites (recomendado)

```bash
make test
```

**Qué hace internamente:**
1. Verifica dependencias mínimas (`check-test-deps`)
2. Valida convenciones de naming (`check-test-discovery`)
3. Ejecuta tests Python (`test-python`)
4. Ejecuta tests TypeScript (`test-ts`)
5. Valida configuración (`validate-config`)

**Necesita:** Bun (para TypeScript)
**No necesita:** Ollama, Qdrant, Docker

### Suites individuales

```bash
make test-python      # Solo tests Python
make test-ts          # Solo tests TypeScript (necesita Bun)
make test-kernel      # Tests Kernel + SDD flow (necesita Bun)
make test-all         # make test + test-kernel
```

**Referencia:**
- `test-python`: Ejecuta pytest o runner standalone (fallback)
- `test-ts`: Ejecuta con Bun
- `test-kernel`: Python (`test_kernel_*.py`, `test_sdd_flow_e2e.py`) + TypeScript (`tony_kernel_*.test.ts`)
  - Con Pytest: ejecuta la suite Kernel completa.
  - Sin Pytest/fallback: ejecuta el subconjunto compatible con el runner standalone.
### Ejecutar directamente (diagnóstico)

```bash
# Python con pytest
python3 -m pytest tests -v
```
```bash
# Python con runner standalone (sin pytest)
python3 tools/run-python-tests.py tests
```
El runner standalone usa solo stdlib. Si pytest pasó pero standalone no, significa el test depende de algo no instalable sin pip. Usar pytest en ese caso.
```bash
# TypeScript
bun test tests
```
```bash
# Validación de config
bun run tools/validate-config.ts
```
Validación de `opencode.json`, prompts, agentes, MCP y referencias de archivos.

**Comprueba:**
- Sintaxis y estructura
- Agentes configurados
- Prompts fuente válidos
- Referencias `{file:...}` correctas
- MCP servers registrados
- Convenciones de naming

### Errores frecuentes en config

| Error | Solución |
|-------|----------|
| `{file:...}` apunta a archivo inexistente | Corregir referencia |
| Agente sin prompt fuente válido | Agregar/corregir archivo de prompt |
| Referencia a bundle eliminado | Usar prompt fuente actual |
| Test con nombre no descubrible | Respetar convenciones de `tests/` |

---

### Tests específicos

**Python:**
```bash
python3 -m pytest tests/test_kernel_state_machine.py -v
python3 -m pytest tests/test_sdd_flow_e2e.py -v
python3 -m pytest tests/test_code_index_core.py -v
```

**TypeScript:**
```bash
bun test tests/tony_kernel_hooks.test.ts
bun test tests/judgment_memory_hooks.test.ts
```

### Tests por categoría (markers)

```bash
python3 -m pytest -m concurrency    # Escenarios de concurrencia
python3 -m pytest -m mcp            # Contrato MCP JSON-RPC
python3 -m pytest -m "not concurrency"
```

---

## 4. Qué se prueba

### Tony Kernel (el corazón)

Máquina de estados, gates, checksums, ledgers, integración TypeScript ↔ Python.

**Cubre:**
- 8 fases SDD (explore → archive)
- Phase Gate, Artifact Gate, Scope Guard
- Retry budget
- Phase checksums
- Evidence ledger, task ledger
- Comportamiento fail-closed (regresiones detectadas inmediatamente)

**Tests principales:**
```
tests/test_kernel_state_machine.py
tests/test_kernel_integration.py
tests/test_kernel_cli.py
tests/test_kernel_hardening.py
tests/test_kernel_enforcement.py
tests/test_sdd_flow_e2e.py
```

**Ejecutar:**
```bash
make test-kernel
make verify-sdd-flow  # E2E local sin Ollama/Qdrant
```

### MCP servers (contrato JSON-RPC)

Cuatro servidores con interfaz estable:
- `local-memory/server.py` — memoria persistente
- `code-index/server.py` — indexación semántica
- `judgment-memory/server.py` — ledger de juicios
- `kernel/mcp_server.py` — orquestador

**Probado:**
- `initialize`, `tools/list`, `tools/call`
- Errores y edge cases (requests inválidos, tools desconocidas)
- Notificaciones y protocolo
- Consistencia en `opencode.json`

**Marker:** `pytest -m mcp`

### Judgment Memory

Plugin real con SQLite temporal + servidor HTTP mock (sin Qdrant real).

**Cubre:**
- Persistencia del ledger
- Normalización de juicios
- Embeddings y upserts en Qdrant (simulados)
- Recuperación semántica
- Thresholds y filtros
- Degradación si indexado falla

Cuando se activa **Judgment Day**, el sistema recupera juicios anteriores similares antes de evaluar. 
**Test:** `tests/judgment_memory_hooks.test.ts`

### Code Indexer

Indexación semántica con `tree-sitter` obligatoriamente (no regex).

**Cubre:**
- Chunking estructural
- Indexación incremental
- Búsqueda semántica
- Cambios de archivos

**Test:** `tests/test_code_index_core.py`

**Importante:** Cambiar `TONY_INDEX_CHUNKER` a `regex` no es soportado.

### Configuración y prompts

Validación de `opencode.json`, agentes, prompts, MCP y referencias de archivos.

```bash
bun run tools/validate-config.ts
```

**Comprueba:**
- Sintaxis y estructura de `opencode.json`
- Agentes y prompts fuente válidos
- Referencias `{file:...}` correctas
- MCP servers registrados
- Convenciones de naming

**Errores frecuentes:**
| Error | Solución |
|-------|----------|
| `{file:...}` inexistente | Corregir referencia |
| Agente sin prompt fuente | Agregar/corregir archivo de prompt |
| Referencia a bundle eliminado | Usar prompt fuente actual |
| Test no descubrible | Respetar convenciones de `tests/` |

---

## 5. Discovery conventions

Tests deben seguir estas convenciones o `make check-test-discovery` las rechazará.

### Python

**Patrón:** `tests/test_*.py` o `tests/*_test.py`

Ejemplos válidos:
```
tests/test_kernel_state_machine.py  ✓
tests/test_sdd_flow_e2e.py          ✓
tests/judgment_memory_ledger.py     ✗ (no "test_" prefix)
tests/my_tests.py                   ✗ (no "test_" prefix)
```

**Función/clase dentro:**
- Test funciones: `test_<description>`
- Test clases: `Test<Component>`

### TypeScript

**Patrón:** `tests/*.test.ts` (obligatorio)

Ejemplos válidos:
```
tests/tony_kernel_hooks.test.ts     ✓
tests/judgment_memory_hooks.test.ts ✓
tests/kernel.spec.ts                ✗ (debe ser .test.ts)
tests/kernel.tests.ts               ✗ (debe ser .test.ts)
```

### Validación

```bash
make check-test-discovery
```

Falla si algún archivo no sigue las convenciones o si hay tests TypeScript pero ninguno descubrible.

---

## 6. Coverage

### Python coverage

```bash
make coverage-python
```

**Genera:** `coverage.xml`, `coverage-contexts.json`

**Umbral:** 40% inicial (deliberadamente bajo para detectar regresiones sin ser artificial). Aumenta junto con tests reales.

**Mide:** Branches de `kernel/`, `code-index/`, `judgment-memory/`, `local-memory/`

### TypeScript coverage

```bash
make coverage-ts
```

**Genera:** `coverage-bun/lcov.info`

### Cobertura completa

```bash
make coverage
```

Ejecuta ambas.

---

## 7. Smoke tests e infraestructura externa

Están **completamente separados** de `make test`. Solo ejecutar si tienes Ollama y Qdrant.

### Verificar Qdrant (indexación real)

```bash
make verify-qdrant
```

Roundtrip real: Ollama → embeddings → Qdrant → búsqueda.

### Health check completo

```bash
make health
```

Verifica:
- `opencode.json` y portabilidad de rutas
- Cuatro MCP servers via `initialize`
- Ollama y modelos de embeddings
- Qdrant (`/readyz`, `/collections`)
- Directorios locales escribibles
- Roundtrip de embeddings

**Interpretación:**
- `make test` pasó pero `make health` falló → problema de infraestructura, no de código
- Ambas fallaron → revisar código + infraestructura

### Levantar/bajar infraestructura

```bash
make docker-up    # Ollama + Qdrant en local
make docker-down
```

---

## 8. Troubleshooting

### "Test X falla y no sé por qué"

```bash
# Paso 1: Aislar el test
python3 -m pytest tests/test_<module>.py::test_<name> -v

# Paso 2: Ver logs completos
python3 -m pytest tests/test_<module>.py::test_<name> -vv -s

# -s muestra prints y logs en tiempo real
```

### "Tests pasan localmente pero fallan en CI"

CI ejecuta Python 3.10, 3.11, 3.12. Generalmente:

```bash
# Verificar tu versión local
python3 --version

# Testear con versión exacta (si es 3.11 en local, CI puede fallar en 3.10)
pyenv install 3.10   # o usar Docker
pyenv local 3.10
make test

# Verificar Bun
bun --version  # CI usa 1.3.14
```

### "make test necesita Bun pero no lo tengo"

```bash
# Opción 1: Instalar Bun
curl -fsSL https://bun.sh/install | bash

# Opción 2: Solo tests Python (sin TypeScript)
make test-python
```

### "make health falla pero make test pasó"

Infraestructura no disponible (esperado):

```bash
# Verificar Qdrant
curl http://localhost:6333/readyz || echo "Qdrant not running"

# Verificar Ollama
curl http://localhost:11434/api/tags || echo "Ollama not running"

# Si no están corriendo, `make health` falla por diseño
make docker-up  # Levanta servicios
```

### "Runner standalone falla pero pytest pasó"

Runner standalone usa solo stdlib. Si pytest pasó pero standalone no:

```bash
# El test probablemente depende de external packages
python3 tools/run-python-tests.py tests

# Si falla, es porque usa algo no en stdlib (como pytest)
# Usar pytest en ese caso
```

### "Cambié configuración y validate-config falla"

```bash
# Ver error exacto
bun run tools/validate-config.ts

# Errors comunes:
# - {file:...} apunta a archivo que no existe
# - MCP server en opencode.json no está configurado
# - Prompt fuente no existe o está mal referenciado
```

---

## 9. CI (Continuous Integration)

### Cuándo se ejecuta

**Push** a `main` o `dev`
**Pull request** contra `main` o `dev`

### Qué se ejecuta por versión de Python

Matriz: Python 3.10, 3.11, 3.12 (con Bun 1.3.14)

Para cada versión:
1. `make check-test-discovery` — valida naming
2. `make test` — suite local completa
3. Si Python 3.12: `make coverage` — cobertura completa

### Artifacts (Python 3.12 solamente)

Se publican:
- `coverage.xml` — cobertura Python (XML para SonarQube/etc)
- `coverage-contexts.json` — contexto por test (auditoría de redundancia)
- `coverage-bun/lcov.info` — cobertura TypeScript (LCOV format)

### Job separado: Docker build

Se compila la imagen Docker (timeout: 10 minutos).

### Nota importante

CI **no necesita Ollama ni Qdrant** para la suite local. Solo para smoke tests (que son manuales).

---

## 10. Makefile reference

| Comando | Qué hace | Necesita |
|---------|----------|----------|
| `make test` | Python + TypeScript + config | Bun |
| `make test-python` | Solo tests Python | — |
| `make test-ts` | Solo tests TypeScript | Bun |
| `make test-kernel` | Kernel + SDD + TypeScript kernel | Bun |
| `make test-all` | `test` + `test-kernel` | Bun |
| `make check-test-discovery` | Valida naming conventions | — |
| `make check-test-deps` | Verifica pytest + Bun | — |
| `make verify-sdd-flow` | Flujo E2E SDD local | — |
| `make coverage-python` | Coverage Python (40% threshold) | — |
| `make coverage-ts` | Coverage TypeScript | Bun |
| `make coverage` | Ambas coberturas | Bun |
| `make verify-qdrant` | Indexación real Ollama + Qdrant | Ollama, Qdrant |
| `make health` | Health check infraestructura | Ollama, Qdrant |
| `make docker-up` | Levanta Ollama + Qdrant | Docker |
| `make docker-down` | Para Ollama + Qdrant | Docker |
| `make validate-config` | Valida opencode.json | — |
| `make clean` | Elimina bases + reportes | — |
| `make bootstrap` | Setup completo del proyecto | — |

**Nota:** `make test` ejecuta internamente: `check-test-deps` → `check-test-discovery` → `test-python` → `test-ts` → `validate-config`

---

## 11. Flujo operacional: Qué ejecutar cuándo

### Antes de hacer `commit`

```bash
make test
```

Verifica que tu código NO rompió nada en la suite local (Python + TypeScript + config).

**Si `make test` falla, NO hagas commit. Arreglá el problema primero.**

### Antes de hacer `push` a rama local

Lo mismo que antes de commit:

```bash
make test
```

Si trabajás en una rama que NO es `main` ni `dev`, `make test` es suficiente.

### Antes de hacer `push` a `main` o `dev`

Además de `make test`:

```bash
bun run tools/validate-config.ts
git diff --check
```

**Qué verifican:**
- `make test` — suite local completa
- `bun run tools/validate-config.ts` — `opencode.json`, agentes, prompts, MCP válidos
- `git diff --check` — sin espacios, líneas sin newline, etc

### ¿Qué es un PR crítico?

Un PR es **crítico** si toca CUALQUIERA de estos:

- **Kernel** — lógica de máquina de estados, gates, enforcement
- **MCP servers** — cambios en contrato JSON-RPC
- **Configuración** — `opencode.json`, prompts, agentes
- **Infraestructura** — Docker, scripts de setup, dependencias
- **Testing** — cambios en tests, Makefile, discovery conventions

### Antes de hacer PR crítico

```bash
make test-all
make health
```

**Por qué:**
- `make test-all` = `make test` + tests específicos de Kernel + SDD E2E
- `make health` = verifica infraestructura (Ollama, Qdrant, MCP servers)

**Si `make health` falla pero `make test-all` pasó:** problema de infraestructura, no de código. Documentá en el PR.

### Cambios específicos: qué ejecutar adicional

| Si cambias... | Además de `make test`, ejecutar |
|---|---|
| Code Indexer (`code-index/`) | `make test-all` + `make verify-qdrant` |
| Judgment Memory (`judgment-memory/`) | `make test-all` |
| MCP servers | `make test-all` + `make health` |
| Configuración (`opencode.json`) | `bun run tools/validate-config.ts` |
| Makefile | `make check-test-discovery` |
| Docker | `cd docker && docker compose build` |
| Scripts de setup | `./scripts/setup.sh` (en clean environment) |

### Resumen rápido

**90% de los cambios:**
```bash
make test
```

**Cambios de Kernel/MCP/Config:**
```bash
make test-all
make health
```

**Antes de push a main/dev:**
```bash
make test
bun run tools/validate-config.ts
git diff --check
```

## Documentación
[INSTALL.md](INSTALL.md) — instalación y configuración detallada.  
[ARCHITECTURE.md](ARCHITECTURE.md) — arquitectura interna y componentes.  
[AGENTS.md](AGENTS.md) — define las reglas de comportamiento y desarrollo que deben seguir los agentes.  
[TESTING.md](TESTING.md) — es la guía oficial de estrategia y ejecución de pruebas.  