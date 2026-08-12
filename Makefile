# Makefile para Tony-AI
# Wrappers de conveniencia sobre docker/ + tests locales y smoke tests externos.
#
# La suite local usa descubrimiento automático: pytest descubre todos los .py y
# Bun descubre todos los *.test.ts. Los smoke tests externos quedan separados.

.PHONY: test test-python test-ts test-kernel coverage coverage-python coverage-ts verify-qdrant verify-sdd-flow docker-up docker-down clean bootstrap health validate-config

test: test-python test-ts validate-config

# Descubre todos los tests Python, incluidos los nuevos tests de persistencia,
# concurrencia y contrato MCP.
test-python:
	@echo "▶ Running all Python tests..."
	@python3 -m pytest tests -q
	@echo "✓ Python tests passed"

# Target explícito para depurar únicamente el Kernel, sin duplicar esta etapa
# dentro de `make test`.
test-kernel:
	@echo "▶ Running Kernel tests..."
	@python3 -m pytest tests/test_kernel_*.py tests/test_sdd_flow_e2e.py -v
	@bun test tests/tony_kernel_hooks.test.ts
	@bun test tests/tony_kernel_integration.test.ts
	@bun test tests/tony_kernel_e2e.test.ts
	@echo "✓ Kernel tests passed"

# Bun descubre los archivos *.test.ts por convención.
test-ts:
	@echo "▶ Running all TypeScript tests..."
	@bun test tests
	@echo "✓ TypeScript tests passed"

# Coverage local y artefactos XML/LCOV básicos. El umbral inicial es deliberadamente
# moderado: sirve para detectar módulos no ejercitados sin bloquear mejoras futuras.
coverage: coverage-python coverage-ts

coverage-python:
	@echo "▶ Running Python coverage..."
	@coverage run --source=kernel,code-index,judgment-memory,local-memory -m pytest tests -q
	@coverage report -m --fail-under=40
	@coverage xml -o coverage.xml
	@echo "✓ Python coverage threshold passed"

coverage-ts:
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
