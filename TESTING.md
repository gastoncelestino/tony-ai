# Tony-AI — Testing

## Estrategia general

La suite está organizada por dominio funcional, infraestructura de tests y verificaciones:

```text
tests/
├── functional/
│   ├── code_index/
│   ├── judgment_memory/
│   ├── local_memory/
│   ├── orchestrator/
│   ├── runtime/
│   └── sdd/
├── infrastructure/
├── kernel/
│   ├── python/
│   └── ts/
├── verification/
└── test_setup.py
```

El runner standalone está en `tests/verification/python_verify.py` y se usa como fallback cuando pytest no está disponible.

## 1. Requisitos

- Python 3.10+
- Bun 1.3.14+
- sqlite3
- make

Instalación completa:

```bash
./scripts/setup.sh
```

Instalación manual:

```bash
python3 -m pip install -r requirements-dev.txt
```

## 2. Comandos principales

| Objetivo | Comando |
|---|---|
| Suite normal | `make test` |
| Suite completa | `make test-all` |
| Solo Python | `make test-python` |
| Solo TypeScript | `make test-ts` |
| Kernel + SDD E2E | `make test-kernel` |
| SDD E2E aislado | `make verify-sdd-flow` |
| Qdrant real | `make verify-qdrant` |
| Validación de configuración | `make validate-config` |
| Coverage completa | `make coverage` |

## 3. Descubrimiento

`make check-test-discovery` valida recursivamente las convenciones:

- Python: `test_*.py` o `*_test.py`
- TypeScript: `*.test.ts`
- Verificaciones: `*.verify.ts`
- `python_verify.py` es una excepción permitida por nombre.

Pytest usa `tests/` como `testpaths` en `pytest.ini`.

## 4. Estructura de tests

### Kernel

Los tests Python del Kernel están consolidados en siete suites:

```text
tests/kernel/python/
├── test_kernel_cli.py
├── test_kernel_concurrency.py
├── test_kernel_enforcement.py
├── test_kernel_hardening.py
├── test_kernel_integration.py
├── test_kernel_mcp_contract.py
└── test_kernel_state_machine.py
```

Los tests TypeScript del Kernel están en:

```text
tests/kernel/ts/
├── tony_kernel_e2e.test.ts
├── tony_kernel_hooks.test.ts
└── tony_kernel_integration.test.ts
```

### Funcionalidad

```text
tests/functional/
├── code_index/test_code_index_core.py
├── judgment_memory/
│   ├── test_judgment_memory_ledger.py
│   ├── judgment_memory_hooks.test.ts
│   └── judgment_memory_qdrant.verify.ts
├── local_memory/test_local_memory_server.py
├── orchestrator/test_orchestrator_scope.py
├── runtime/
│   ├── test_retry_budget.py
│   └── test_runtime_paths.py
└── sdd/test_sdd_flow_e2e.py
```

### Infraestructura y verificación

```text
tests/infrastructure/test_python_test_runner.py
tests/verification/python_verify.py
tests/verification/validate_config.verify.ts
```

`test_python_test_runner.py` valida el runner fallback. `python_verify.py` no es un test de producto: es la infraestructura de ejecución cuando pytest no está disponible.

## 5. Ejecución directa

Python:

```bash
python3 -m pytest tests -v
python3 tests/verification/python_verify.py tests
```

Kernel Python:

```bash
python3 -m pytest tests/kernel/python -v
```

SDD E2E:

```bash
python3 -m pytest tests/functional/sdd/test_sdd_flow_e2e.py -v
```

TypeScript:

```bash
bun test tests
```

Verificación de configuración:

```bash
bun run tests/verification/validate_config.verify.ts
```

Qdrant:

```bash
bun run tests/functional/judgment_memory/judgment_memory_qdrant.verify.ts
```

## 6. Coverage

Python coverage mide `kernel/`, `code-index/`, `judgment-memory/` y `local-memory/`.

```bash
make coverage-python
make coverage-ts
make coverage
```

La suite Python usa branches y contextos por test. El reporte se genera en `coverage.xml` y `coverage-contexts.json`. Bun genera `coverage-bun/lcov.info`.

## 7. Smoke tests e infraestructura externa

Los smoke tests de infraestructura externa están separados de `make test`:

```bash
make verify-qdrant
make health
```

`make health` valida configuración, servidores MCP, Ollama, Qdrant y directorios persistentes.

## 8. CI

El workflow de GitHub Actions ejecuta:

1. Validación de descubrimiento.
2. Suite completa con Python 3.10, 3.11 y 3.12.
3. Coverage en Python 3.12.
4. Build de Docker.

La referencia de CI es `.github/workflows/ci.yml`.
