# Makefile para Tony-AI
# Wrappers de conveniencia sobre tests locales y smoke tests externos.

ENV_FILE := .env
TONY_RUNTIME_DIR ?= $(shell set -a; . ./$(ENV_FILE); printf '%s' "$$TONY_RUNTIME_DIR")
PYTHON_CACHE_DIR ?= $(shell set -a; . ./$(ENV_FILE); printf '%s' "$$PYTHON_CACHE_DIR")
PYTHONPYCACHEPREFIX ?= $(PYTHON_CACHE_DIR)
PYTEST_CACHE_DIR ?= $(PYTHON_CACHE_DIR)/pytest
export TONY_RUNTIME_DIR
export PYTHON_CACHE_DIR
export PYTHONPYCACHEPREFIX
export PYTEST_CACHE_DIR

.PHONY: test test-all check-test-deps check-test-discovery check-test-cache test-python test-ts test-kernel check-coverage-deps coverage coverage-python coverage-ts verify-qdrant verify-sdd-flow docker-up docker-down clean bootstrap health validate-config

test: check-test-deps check-test-discovery test-python test-ts validate-config

test-all: test test-kernel health check-test-cache

check-test-deps:
	@mkdir -p "$(PYTHON_CACHE_DIR)" "$(PYTEST_CACHE_DIR)"
	@if python3 -c 'import pytest; print("pytest", pytest.__version__)' 2>/dev/null; then echo "✓ pytest disponible (PYTEST_CACHE_DIR=$(PYTEST_CACHE_DIR))"; else echo "⚠ pytest no disponible; usando test runners standalone"; fi
	@command -v bun >/dev/null 2>&1 || (echo "ERROR: falta Bun."; exit 1)

check-test-discovery:
	@set -eu; invalid_ts=$$(find tests -maxdepth 1 -type f -name '*.ts' ! -name '*.test.ts' ! -name '*.verify.ts' -print); invalid_py=$$(find tests -maxdepth 1 -type f -name '*.py' ! -name 'test_*.py' ! -name '*_test.py' ! -name '__init__.py' ! -name 'python_verify.py' -print); if [ -n "$$invalid_ts" ]; then echo "ERROR: TypeScript tests no descubribles:"; echo "$$invalid_ts"; exit 1; fi; if [ -n "$$invalid_py" ]; then echo "ERROR: Python tests no descubribles:"; echo "$$invalid_py"; exit 1; fi; test -n "$$(find tests -maxdepth 1 -type f -name '*.test.ts' -print -quit)" || { echo "ERROR: no hay tests TypeScript descubribles"; exit 1; }; echo "✓ Test naming/discovery conventions valid"

# La suite Python trata warnings como errores para mantener el contrato de 0 warnings.
test-python: check-test-deps check-test-discovery
	@PYTHONWARNINGS=error python3 -m pytest tests -v || python3 tests/python_verify.py tests

test-kernel: check-test-deps check-test-discovery
	@PYTHONWARNINGS=error python3 -m pytest tests/test_kernel_*.py tests/test_sdd_flow_e2e.py -v || python3 tests/python_verify.py tests/test_kernel_cli.py tests/test_kernel_enforcement.py tests/test_sdd_flow_e2e.py
	@bun test tests/tony_kernel_*.test.ts

# Verifica explícitamente que pytest no haya creado estado dentro del checkout y
# que su configuración efectiva use exactamente PYTEST_CACHE_DIR.
check-test-cache:
	@if [ -d .pytest_cache ]; then echo "ERROR: .pytest_cache fue creado dentro del checkout; PYTEST_CACHE_DIR=$(PYTEST_CACHE_DIR)"; exit 1; fi
	@actual="$$(PYTEST_CACHE_DIR="$(PYTEST_CACHE_DIR)" python3 -c 'from _pytest.config import get_config; c=get_config(); c.parse(["-c", "pytest.ini"]); print(c.getini("cache_dir"))')"; if [ "$$actual" != "$(PYTEST_CACHE_DIR)" ]; then echo "ERROR: pytest cache_dir=$$actual; esperado $(PYTEST_CACHE_DIR)"; exit 1; fi
	@echo "✓ pytest cache fuera del checkout (cache_dir=$(PYTEST_CACHE_DIR))"

test-ts: check-test-deps check-test-discovery
	@bun test tests

check-coverage-deps: check-test-deps
	@python3 -c 'import coverage; print("coverage", coverage.__version__)'
	@python3 -c 'import pytest_cov; print("pytest-cov", pytest_cov.__version__)'

coverage: check-coverage-deps coverage-python coverage-ts

coverage-python: check-coverage-deps
	@mkdir -p "$(PYTHON_CACHE_DIR)/coverage"; export COVERAGE_FILE="$(PYTHON_CACHE_DIR)/coverage/.coverage"; PYTHONWARNINGS=error python3 -m pytest tests -q --cov=kernel --cov=code-index --cov=judgment-memory --cov=local-memory --cov-branch --cov-context=test --cov-report=term-missing || (rm -f "$$COVERAGE_FILE"; coverage run --branch --source=kernel,code-index,judgment-memory,local-memory tests/python_verify.py tests); coverage report -m --fail-under=40

coverage-ts: check-test-deps check-test-discovery
	@tmpdir=$$(mktemp -d); trap 'rm -rf "$$tmpdir"' EXIT; bun test --coverage --coverage-reporter=text --coverage-dir="$$tmpdir" tests

verify-qdrant:
	@bun run tests/judgment_qdrant.verify.ts

verify-sdd-flow:
	@python3 tests/test_sdd_flow_e2e.py

bootstrap:
	@bash scripts/setup.sh

health:
	@bash scripts/health.sh

docker-up:
	@cd docker && docker compose up -d && docker compose logs -f ollama-pull

docker-down:
	@cd docker && docker compose down

clean:
	@rm -f local-memory/memory.db code-index/.codeindex/manifest.db judgment-memory/judgment-memory.db coverage.xml coverage-contexts.json
	@rm -rf coverage-bun

validate-config:
	@bun run tests/validate_config.verify.ts
