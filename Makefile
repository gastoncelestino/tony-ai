# Makefile para Tony-AI
# Wrappers de conveniencia sobre tests locales y smoke tests externos.
#
# La suite local usa descubrimiento automático: pytest descubre todos los .py y
# Bun descubre todos los *.test.ts. Los smoke tests externos quedan separados.

.PHONY: test test-all check-test-deps check-test-discovery check-coverage-deps test-python test-ts test-kernel coverage coverage-python coverage-ts verify-qdrant verify-sdd-flow docker-up docker-down clean bootstrap health validate-config

# Este target es la suite completa. El Kernel está incluido vía
# descubrimiento automático en test-python (test_kernel_*.py) y test-ts
# (tony_kernel_*.test.ts), por lo que no se invoca test-kernel aquí para
# evitar duplicar ejecución.
test: check-test-deps check-test-discovery test-python test-ts validate-config

# Target explícito que ejecuta TODO, incluyendo el Kernel de forma focalizada.
test-all: test test-kernel

check-test-deps:
	@python3 -c 'import pytest; print("pytest", pytest.__version__)' || \
		(echo "ERROR: falta pytest. Ejecutá: python3 -m pip install -r requirements-dev.txt"; exit 1)
	@command -v bun >/dev/null 2>&1 || \
		(echo "ERROR: falta Bun. Instalá Bun antes de ejecutar los tests TypeScript."; exit 1)
	@echo "✓ Test dependencies available"

# Evita que un archivo nuevo quede fuera de pytest o Bun por una convención de
# nombres incorrecta. La ejecución de test-ts valida además el descubrimiento real.
check-test-discovery:
	@set -eu; \
	invalid_ts=$$(find tests -maxdepth 1 -type f -name '*.ts' ! -name '*.test.ts' -print); \
	invalid_py=$$(find tests -maxdepth 1 -type f -name '*.py' ! -name 'test_*.py' ! -name '*_test.py' ! -name '__init__.py' -print); \
	if [ -n "$$invalid_ts" ]; then echo "ERROR: TypeScript tests no descubribles:"; echo "$$invalid_ts"; exit 1; fi; \
	if [ -n "$$invalid_py" ]; then echo "ERROR: Python tests no descubribles:"; echo "$$invalid_py"; exit 1; fi; \
	test -n "$$(find tests -maxdepth 1 -type f -name '*.test.ts' -print -quit)" || { echo "ERROR: no hay tests TypeScript descubribles"; exit 1; }; \
	echo "✓ Test naming/discovery conventions valid"

# Descubre todos los tests Python, incluidos los tests de persistencia,
# concurrencia y contrato MCP.
test-python: check-test-deps check-test-discovery
	@echo "▶ Running all Python tests..."
	@python3 -m pytest tests -q
	@echo "✓ Python tests passed"

# Target explícito para depurar únicamente el Kernel, sin duplicarlo en `make test`.
test-kernel: check-test-deps check-test-discovery
	@echo "▶ Running focused Kernel tests..."
	@python3 -m pytest tests/test_kernel_*.py tests/test_sdd_flow_e2e.py -v
	@bun test tests/tony_kernel_hooks.test.ts
	@bun test tests/tony_kernel_integration.test.ts
	@bun test tests/tony_kernel_e2e.test.ts
	@echo "✓ Focused Kernel tests passed"

# Bun descubre los archivos *.test.ts por convención.
test-ts: check-test-deps check-test-discovery
	@echo "▶ Running all TypeScript tests..."
	@bun test tests
	@echo "✓ TypeScript tests passed"

check-coverage-deps: check-test-deps
	@python3 -c 'import coverage; print("coverage", coverage.__version__)' || \
		(echo "ERROR: falta coverage. Ejecutá: python3 -m pip install -r requirements-dev.txt"; exit 1)
	@echo "✓ Coverage dependencies available"

# Coverage local y artefactos XML/LCOV básicos. El umbral inicial es deliberadamente
# moderado: sirve para detectar módulos no ejercitados sin bloquear mejoras futuras.
coverage: check-coverage-deps coverage-python coverage-ts

coverage-python: check-coverage-deps
	@echo "▶ Running Python coverage..."
	@coverage run --source=kernel,code-index,judgment-memory,local-memory -m pytest tests -q
	@coverage report -m --fail-under=40
	@coverage xml -o coverage.xml
	@echo "✓ Python coverage threshold passed"

coverage-ts: check-test-deps check-test-discovery
	@echo "▶ Running TypeScript coverage..."
	@rm -rf coverage-bun
	@bun test --coverage --coverage-reporter=lcov --coverage-dir=coverage-bun tests
	@test -s coverage-bun/lcov.info
	@echo "✓ TypeScript coverage report written to coverage-bun/lcov.info"

verify-qdrant:
	@echo "▶ Running Qdrant smoke test (requires Ollama + Qdrant running)..."
	@cd judgment-memory && bun run scripts/verify-qdrant.ts
	@echo "✓ Qdrant smoke test passed"

verify-sdd-flow:
	@echo "▶ Running full SDD flow (explore→archive) adversarial verification..."
	@python3 tests/test_sdd_flow_e2e.py
	@echo "✓ SDD flow verification passed"

bootstrap:
	@bash scripts/setup.sh

health:
	@bash scripts/health.sh

docker-up:
	@cd docker && docker compose up -d
	@cd docker && docker compose logs -f ollama-pull

docker-down:
	@cd docker && docker compose down

clean:
	@rm -f local-memory/memory.db code-index/.codeindex/manifest.db judgment-memory/judgment-memory.db coverage.xml
	@rm -rf coverage-bun
	@echo "✓ Cleaned local databases"

validate-config:
	@echo "▶ Validating configuration..."
	@bun run tools/validate-config.ts
	@echo "✓ Configuration valid"
