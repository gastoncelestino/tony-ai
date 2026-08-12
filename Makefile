# Makefile para Tony-AI
# Wrappers de conveniencia sobre tests locales y smoke tests externos.
#
# La suite local usa descubrimiento automático: pytest descubre todos los .py y
# Bun descubre todos los *.test.ts. Los smoke tests externos quedan separados.

.PHONY: test test-all build-prompts check-prompts check-test-deps check-test-discovery check-coverage-deps test-python test-ts test-kernel coverage coverage-python coverage-ts verify-qdrant verify-sdd-flow docker-up docker-down clean bootstrap health validate-config generate-agents

# Este target es la suite completa. test-kernel es un target focalizado y no se
# invoca aquí para evitar ejecutar dos veces los mismos tests del Kernel.
test: check-test-deps check-test-discovery check-prompts test-python test-ts validate-config

build-prompts: check-test-deps
	@echo "▶ Building prompt bundles..."
	@mkdir -p prompts/generated/phases
	@bun run tools/build-prompts.ts
	@echo "✓ Prompt bundles built"

check-prompts:
	@echo "▶ Checking prompt bundles..."
	@bun run tools/build-prompts.ts --check
	@echo "✓ Prompt bundles are up to date"

# Target explícito que ejecuta TODO, incluyendo el Kernel de forma focalizada.
test-all: test test-kernel

check-test-deps:
	@if python3 -c 'import pytest; print("pytest", pytest.__version__)' 2>/dev/null; then \
		echo "✓ pytest disponible"; \
	else \
		echo "⚠ pytest no disponible; usando test runners standalone"; \
		echo "  Para instalarlo: python3 -m pip install -r requirements-dev.txt"; \
	fi
	@command -v bun >/dev/null 2>&1 || \
		(echo "ERROR: falta Bun. Instalá Bun antes de ejecutar los tests TypeScript."; exit 1)
	@echo "✓ Test dependencies available (o fallback activo)"

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
	@if python3 -c 'import pytest' 2>/dev/null; then \
		python3 -m pytest tests -q; \
	else \
		echo "⚠ Ejecutando tests standalone (sin pytest)..."; \
		for f in tests/test_*.py; do \
			echo "  . $$f"; \
			python3 "$$f" || exit 1; \
		done; \
	fi
	@echo "✓ Python tests passed"

# Target explícito para depurar únicamente el Kernel, sin duplicarlo en `make test`.
test-kernel: check-test-deps check-test-discovery
	@echo "▶ Running focused Kernel tests..."
	@if python3 -c 'import pytest' 2>/dev/null; then \
		python3 -m pytest tests/test_kernel_*.py tests/test_sdd_flow_e2e.py -v; \
	else \
		echo "⚠ Ejecutando kernel tests standalone (sin pytest)..."; \
		for f in tests/test_kernel_*.py tests/test_sdd_flow_e2e.py; do \
			echo "  . $$f"; \
			python3 "$$f" || exit 1; \
		done; \
	fi
	@bun test tests/tony_kernel_*.test.ts
	@echo "✓ Focused Kernel tests passed"

# Bun descubre los archivos *.test.ts por convención.
test-ts: check-test-deps check-test-discovery
	@echo "▶ Running all TypeScript tests..."
	@bun test tests
	@echo "✓ TypeScript tests passed"

check-coverage-deps: check-test-deps
	@if python3 -c 'import coverage; print("coverage", coverage.__version__)' 2>/dev/null; then \
		echo "✓ coverage disponible"; \
	else \
		echo "⚠ coverage no disponible; ejecutá: python3 -m pip install -r requirements-dev.txt"; \
	fi
	@echo "✓ Coverage dependencies available (o fallback activo)"

# Coverage local y artefactos XML/LCOV básicos. El umbral inicial es deliberadamente
# moderado: sirve para detectar módulos no ejercitados sin bloquear mejoras futuras.
coverage: check-coverage-deps coverage-python coverage-ts

coverage-python: check-coverage-deps
	@echo "▶ Running Python coverage..."
	@if python3 -c 'import coverage' 2>/dev/null; then \
		coverage run --source=kernel,code-index,judgment-memory,local-memory -m pytest tests -q; \
		coverage report -m --fail-under=40; \
		coverage xml -o coverage.xml; \
	else \
		echo "⚠ coverage no disponible; ejecutando tests sin coverage"; \
		for f in tests/test_*.py; do python3 "$$f" || exit 1; done; \
	fi
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

build-prompts: check-test-deps
	@echo "▶ Building prompt bundles..."
	@mkdir -p prompts/generated/phases
	@bun run tools/build-prompts.ts
	@echo "✓ Prompt bundles built"

check-prompts:
	@echo "▶ Checking prompt bundles..."
	@bun run tools/build-prompts.ts --check
	@echo "✓ Prompt bundles are up to date"

generate-agents:
	@echo "▶ Generating opencode.json agents from phase-manifest.json..."
	@bun run scripts/generate-opencode-agents.ts
	@echo "✓ opencode.json agents synchronized"

validate-config:
	@echo "▶ Validating configuration..."
	@bun run tools/validate-config.ts
	@echo "✓ Configuration valid"
