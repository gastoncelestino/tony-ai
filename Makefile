# Makefile para Tony-AI
# Wrappers de conveniencia sobre tests locales y smoke tests externos.

.PHONY: test: check-test-deps check-test-discovery check-prompts check-phase-context check-launcher test-python test-ts validate-config

test: check-test-deps check-test-discovery check-prompts test-python test-ts validate-config
test-all: test test-kernel

check-test-deps:
	@if python3 -c 'import pytest; print("pytest", pytest.__version__)' 2>/dev/null; then echo "✓ pytest disponible"; else echo "⚠ pytest no disponible; usando test runners standalone"; fi
	@command -v bun >/dev/null 2>&1 || (echo "ERROR: falta Bun."; exit 1)

check-test-discovery:
	@set -eu; invalid_ts=$$(find tests -maxdepth 1 -type f -name '*.ts' ! -name '*.test.ts' -print); invalid_py=$$(find tests -maxdepth 1 -type f -name '*.py' ! -name 'test_*.py' ! -name '*_test.py' ! -name '__init__.py' -print); if [ -n "$$invalid_ts" ]; then echo "ERROR: TypeScript tests no descubribles:"; echo "$$invalid_ts"; exit 1; fi; if [ -n "$$invalid_py" ]; then echo "ERROR: Python tests no descubribles:"; echo "$$invalid_py"; exit 1; fi; test -n "$$(find tests -maxdepth 1 -type f -name '*.test.ts' -print -quit)" || { echo "ERROR: no hay tests TypeScript descubribles"; exit 1; }; echo "✓ Test naming/discovery conventions valid"

check-prompts:
	@set -eu; \
	test ! -d prompts/generated || { echo "ERROR: prompts/generated no debe existir en dev"; exit 1; }; \
	test ! -f prompts/agents/includes/phase-manifest.json || { echo "ERROR: phase-manifest.json no debe existir en dev"; exit 1; }; \
	grep -q '"prompt": "./prompts/agents/tony-orchestrator.md"' opencode.json || { echo "ERROR: orchestrator debe usar el prompt fuente"; exit 1; }; \
	for phase in sdd-init sdd-onboard sdd-explore sdd-propose sdd-spec sdd-design sdd-tasks sdd-apply sdd-verify sdd-archive; do \
		grep -q "\"prompt\": \"./prompts/sdd/$$phase.md\"" opencode.json || { echo "ERROR: $$phase no apunta a su prompt fuente"; exit 1; }; \
	done; \
	echo "✓ Phase prompts are plain, source-controlled, and non-generated"

check-phase-context:
	@set -eu; \
	for forbidden in persistence-contract.md sdd-status-contract.md skill-resolver.md review-ledger-contract.md; do \
		if grep -R -n --include='sdd-*.md' "$$forbidden" prompts/sdd 2>/dev/null; then \
			echo "ERROR: $$forbidden no debe formar parte del contexto directo de los SDD phase prompts"; \
			exit 1; \
		fi; \
	done; \
	if grep -R -n --include='sdd-*.md' 'phase-manifest.json\|prompts/generated\|{{include:' prompts/sdd 2>/dev/null; then \
		echo "ERROR: un phase prompt todavía referencia el mecanismo de prompts generado/dinámico"; \
		exit 1; \
	fi; \
	echo "✓ SDD phase prompts keep infrastructure/review contracts out of direct context"

check-launcher:
	@set -eu; \
	test -f prompts/agents/includes/phase-launcher.md || { echo "ERROR: falta phase-launcher.md"; exit 1; }; \
	if grep -n 'phase-manifest.json\|prompts/generated\|{{include:' prompts/agents/includes/phase-launcher.md 2>/dev/null; then \
		echo "ERROR: phase-launcher.md todavía referencia el sistema de composición eliminado"; \
		exit 1; \
	fi; \
	echo "✓ Phase launcher uses routing/delegation only"

test-python: check-test-deps check-test-discovery
	@python3 -m pytest tests -q 2>/dev/null || python3 tools/run-python-tests.py tests

test-kernel: check-test-deps check-test-discovery
	@python3 -m pytest tests/test_kernel_*.py tests/test_sdd_flow_e2e.py -v 2>/dev/null || python3 tools/run-python-tests.py tests/test_kernel_cli.py tests/test_kernel_enforcement.py tests/test_sdd_flow_e2e.py
	@bun test tests/tony_kernel_*.test.ts

test-ts: check-test-deps check-test-discovery
	@bun test tests

check-coverage-deps: check-test-deps
	@python3 -c 'import coverage; print("coverage", coverage.__version__)'

coverage: check-coverage-deps coverage-python coverage-ts

coverage-python: check-coverage-deps
	@coverage run --source=kernel,code-index,judgment-memory,local-memory -m pytest tests -q || coverage run --source=kernel,code-index,judgment-memory,local-memory tools/run-python-tests.py tests
	@coverage report -m --fail-under=40
	@coverage xml -o coverage.xml

coverage-ts: check-test-deps check-test-discovery
	@rm -rf coverage-bun
	@bun test --coverage --coverage-reporter=lcov --coverage-dir=coverage-bun tests
	@test -s coverage-bun/lcov.info

verify-qdrant:
	@cd judgment-memory && bun run scripts/verify-qdrant.ts

verify-sdd-flow:
	@python3 tests/test_sdd_flow_e2e.py

bootstrap:
	@bash scripts/setup.sh

health:
	@bash scripts/shealth.sh

docker-up:
	@cd docker && docker compose up -d && docker compose logs -f ollama-pull

docker-down:
	@cd docker && docker compose down

clean:
	@rm -f local-memory/memory.db code-index/.codeindex/manifest.db judgment-memory/judgment-memory.db coverage.xml
	@rm -rf coverage-bun

validate-config:
	@bun run tools/validate-config.ts
