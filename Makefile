# Makefile para Tony-AI
# Wrappers de conveniencia sobre tests locales y smoke tests externos.

TONY_RUNTIME_DIR ?= $(HOME)/.tony-ai/tony-ai
export TONY_RUNTIME_DIR
export PYTHONPYCACHEPREFIX := $(TONY_RUNTIME_DIR)/pycache

.PHONY: test test-all check-test-deps check-test-discovery test-python test-ts test-kernel check-coverage-deps coverage coverage-python coverage-ts verify-qdrant verify-sdd-flow docker-up docker-down clean bootstrap health validate-config

# Ejecuta la suite normal: tests Python + TypeScript + validación de configuración.
test: check-test-deps check-test-discovery test-python test-ts validate-config

# test-all agrega las pruebas específicas del kernel y del flujo SDD end-to-end.
test-all: test test-kernel

check-test-deps:
	@if python3 -c 'import pytest; print("pytest", pytest.__version__)' 2>/dev/null; then echo "✓ pytest disponible"; else echo "⚠ pytest no disponible; usando test runners standalone"; fi
	@command -v bun >/dev/null 2>&1 || (echo "ERROR: falta Bun."; exit 1)

# Mantiene las convenciones de descubrimiento: TypeScript *.test.ts, verificaciones *.verify.ts y Python test_*.py/*_test.py.
check-test-discovery:
	@set -eu; invalid_ts=$$(find tests -maxdepth 1 -type f -name '*.ts' ! -name '*.test.ts' ! -name '*.verify.ts' -print); invalid_py=$$(find tests -maxdepth 1 -type f -name '*.py' ! -name 'test_*.py' ! -name '*_test.py' ! -name '__init__.py' -print); if [ -n "$$invalid_ts" ]; then echo "ERROR: TypeScript tests no descubribles:"; echo "$$invalid_ts"; exit 1; fi; if [ -n "$$invalid_py" ]; then echo "ERROR: Python tests no descubribles:"; echo "$$invalid_py"; exit 1; fi; test -n "$$(find tests -maxdepth 1 -type f -name '*.test.ts' -print -quit)" || { echo "ERROR: no hay tests TypeScript descubribles"; exit 1; }; echo "✓ Test naming/discovery conventions valid"

# Python usa pytest cuando está disponible y conserva el runner standalone como fallback.
test-python: check-test-deps check-test-discovery
	@python3 -m pytest tests -q 2>/dev/null || python3 tests/python_verify.py tests

# Kernel y SDD flow se mantienen separados para poder diagnosticar fallos específicos.
test-kernel: check-test-deps check-test-discovery
	@python3 -m pytest tests/test_kernel_*.py tests/test_sdd_flow_e2e.py -v 2>/dev/null || python3 tests/python_verify.py tests/test_kernel_cli.py tests/test_kernel_enforcement.py tests/test_sdd_flow_e2e.py
	@bun test tests/tony_kernel_*.test.ts

# TypeScript se ejecuta con Bun.
test-ts: check-test-deps check-test-discovery
	@bun test tests

check-coverage-deps: check-test-deps
	@python3 -c 'import coverage; print("coverage", coverage.__version__)'
	@python3 -c 'import pytest_cov; print("pytest-cov", pytest_cov.__version__)'

coverage: check-coverage-deps coverage-python coverage-ts

# Coverage Python mide branches y conserva contexto por test para auditorías de redundancia.
coverage-python: check-coverage-deps
	@python3 -m pytest tests -q --cov=kernel --cov=code-index --cov=judgment-memory --cov=local-memory --cov-branch --cov-context=test --cov-report=term-missing --cov-report=xml:coverage.xml || (rm -f .coverage && coverage run --branch --source=kernel,code-index,judgment-memory,local-memory tests/python_verify.py tests)
	@coverage report -m --fail-under=40
	@coverage xml -o coverage.xml
	@coverage json --show-contexts -o coverage-contexts.json

# Coverage TypeScript usa el reporte LCOV de Bun.
coverage-ts: check-test-deps check-test-discovery
	@rm -rf coverage-bun
	@bun test --coverage --coverage-reporter=lcov --coverage-dir=coverage-bun tests
	@test -s coverage-bun/lcov.info

# Smoke test de conexión/configuración de Qdrant.
verify-qdrant:
	@bun run tests/judgment_qdrant.verify.ts

# Smoke test end-to-end del flujo SDD.
verify-sdd-flow:
	@python3 tests/test_sdd_flow_e2e.py

# Bootstrap inicial del entorno local.
bootstrap:
	@bash scripts/setup.sh

# Health check del proyecto.
health:
	@bash scripts/health.sh

# Levanta los servicios Docker y muestra el proceso de pull de Ollama.
docker-up:
	@cd docker && docker compose up -d && docker compose logs -f ollama-pull

docker-down:
	@cd docker && docker compose down

# Limpieza de bases locales y artefactos de coverage.
clean:
	@rm -f local-memory/memory.db code-index/.codeindex/manifest.db judgment-memory/judgment-memory.db coverage.xml coverage-contexts.json
	@rm -rf coverage-bun

# Valida la configuración de OpenCode/proyecto.
validate-config:
	@bun run tests/validate_config.verify.ts
