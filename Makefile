# Makefile para Tony-AI
# Wrappers de conveniencia sobre docker/ + los tests

.PHONY: test test-python test-ts verify-qdrant docker-up docker-down clean bootstrap health validate-config

test: test-python test-ts test-kernel

test-python:
	@echo "▶ Running Python tests..."
	@cd local-memory && python3 test_server.py
	@cd code-index && python3 test_core.py
	@cd judgment-memory && python3 test_ledger.py
	@echo "✓ Python tests passed"

test-kernel:
	@echo "▶ Running Kernel tests..."
	@python3 -m kernel.test_state_machine
	@echo "✓ Kernel tests passed"

test-ts:
	@echo "▶ Running TypeScript tests..."
	@cd judgment-memory && bun test ./test_hooks.ts
	@echo "✓ TypeScript tests passed"

verify-qdrant:
	@echo "▶ Running Qdrant smoke test (requires Ollama + Qdrant running)..."
	@cd judgment-memory && bun run scripts/verify-qdrant.ts
	@echo "✓ Qdrant smoke test passed"

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
	@rm -f local-memory/memory.db code-index/.codeindex/manifest.db judgment-memory/judgment-memory.db
	@echo "✓ Cleaned local databases"

validate-config:
	@echo "▶ Validating configuration..."
	@bun run scripts/validate-config.ts
	@echo "✓ Configuration valid"
