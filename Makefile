# Makefile para Tony-AI
# Wrappers de conveniencia sobre docker/ + los tests
#
# Todos los tests viven en tests/. Los de Python se corren con pytest
# (unifica los que ya eran unittest.TestCase con los que eran asserts
# sueltos, sin tocarles la lógica). Los de TypeScript se corren con bun.

.PHONY: test test-python test-ts test-kernel verify-qdrant verify-sdd-flow docker-up docker-down clean bootstrap health validate-config

test: test-python test-ts test-kernel

test-python:
	@echo "▶ Running Python tests..."
	@python3 -m pytest tests/test_local_memory_server.py tests/test_code_index_core.py tests/test_judgment_memory_ledger.py -v
	@echo "✓ Python tests passed"

test-kernel:
	@echo "▶ Running Kernel tests..."
	@python3 -m pytest tests/test_kernel_state_machine.py tests/test_kernel_integration.py tests/test_kernel_cli.py tests/test_kernel_hardening.py tests/test_kernel_enforcement.py tests/test_sdd_flow_e2e.py -v
	@bun test ./tests/test_tony_kernel_hooks.ts
	@bun test ./tests/test_tony_kernel_integration.ts
	@bun test ./tests/test_tony_kernel_e2e.ts
	@echo "✓ Kernel tests passed"

test-ts:
	@echo "▶ Running TypeScript tests..."
	@bun test ./tests/test_judgment_memory_hooks.ts
	@echo "✓ TypeScript tests passed"

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
	@rm -f local-memory/memory.db code-index/.codeindex/manifest.db judgment-memory/judgment-memory.db
	@echo "✓ Cleaned local databases"

validate-config:
	@echo "▶ Validating configuration..."
	@bun run tools/validate-config.ts
	@echo "✓ Configuration valid"
