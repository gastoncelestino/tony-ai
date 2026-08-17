# Makefile para Tony-AI
# Test targets are derived from the current tests/ tree.

TONY_RUNTIME_DIR ?= $(HOME)/.tony-ai/tony-ai
export TONY_RUNTIME_DIR
export PYTHONPYCACHEPREFIX := $(TONY_RUNTIME_DIR)/pycache
export PYTHONPATH := $(CURDIR):$(CURDIR)/code-index:$(CURDIR)/judgment-memory:$(CURDIR)/local-memory:$(PYTHONPATH)

PLUGIN_LINKS := tests/kernel/plugins tests/functional/plugins tests/functional/judgment_memory/plugins

.PHONY: \
	test test-all test-python test-ts test-functional test-kernel \
	test-verification verify-python-runner verify-qdrant verify-sdd-flow \
	check-test-deps check-test-discovery \
	check-coverage-deps coverage coverage-python coverage-ts \
	validate-config bootstrap health docker-up docker-down clean

# Main CI/local suite: all Python tests, all Bun *.test.ts suites, and config verification.
test: check-test-deps check-test-discovery test-python test-ts validate-config

# Compatibility alias: `test` already covers every regular test suite.
test-all: test

check-test-deps:
	@python3 -c 'import pytest; print("pytest", pytest.__version__)' >/dev/null 2>&1 || { echo "ERROR: pytest is required. Run make bootstrap or pip install -r requirements-dev.txt"; exit 1; }
	@command -v bun >/dev/null 2>&1 || { echo "ERROR: Bun is required."; exit 1; }

# Discovery conventions are recursive so domain subdirectories are allowed.
check-test-discovery:
	@set -eu; \
	invalid_ts=$$(find tests -type f -name '*.ts' ! -name '*.test.ts' ! -name '*.verify.ts' -print); \
	invalid_py=$$(find tests -type f -name '*.py' ! -name 'test_*.py' ! -name '*_test.py' ! -name '__init__.py' ! -name 'python_verify.py' -print); \
	if [ -n "$$invalid_ts" ]; then echo "ERROR: TypeScript test files with invalid discovery names:"; echo "$$invalid_ts"; exit 1; fi; \
	if [ -n "$$invalid_py" ]; then echo "ERROR: Python test files with invalid discovery names:"; echo "$$invalid_py"; exit 1; fi; \
	test -n "$$(find tests -type f -name '*.test.ts' -print -quit)" || { echo "ERROR: no Bun *.test.ts files found"; exit 1; }; \
	echo "✓ Test naming/discovery conventions valid"

# Python: one pytest invocation from repository root. No silent fallback on test failure.
test-python: check-test-deps check-test-discovery
	@python3 -m pytest tests -q

# Functional Python tests only.
test-functional: check-test-deps check-test-discovery
	@python3 -m pytest tests/functional -q

# Kernel-focused diagnostic target: Python Kernel + SDD E2E + TypeScript Kernel contracts.
test-kernel: check-test-deps check-test-discovery
	@python3 -m pytest tests/kernel/python tests/functional/sdd/test_sdd_flow_e2e.py -q
	@set -eu; \
	trap 'rm -f tests/kernel/plugins tests/kernel/.test-e2e-tmp' EXIT; \
	ln -sfn ../../../plugins tests/kernel/plugins; \
	ln -sfn .test-e2e-tmp tests/kernel/.test-e2e-tmp; \
	bun test tests/kernel/ts

# Bun runs every discovered *.test.ts file recursively. The temporary links
# preserve the relative plugin layout expected by tests in their domain directories.
test-ts: check-test-deps check-test-discovery
	@set -eu; \
	trap 'rm -f tests/kernel/plugins tests/functional/plugins tests/functional/judgment_memory/plugins' EXIT; \
	ln -sfn ../../../plugins tests/kernel/plugins; \
	ln -sfn ../../plugins tests/functional/plugins; \
	ln -sfn ../../../plugins tests/functional/judgment_memory/plugins; \
	bun test tests

# Explicit verification targets that are intentionally separate from `test`.
verify-python-runner:
	@python3 tests/verification/python_verify.py tests/infrastructure/test_python_test_runner.py

verify-qdrant:
	@bun run tests/functional/judgment_memory/judgment_memory_qdrant.verify.ts

verify-sdd-flow:
	@python3 tests/functional/sdd/test_sdd_flow_e2e.py

# Non-external configuration verification.
validate-config:
	@bun run tests/verification/validate_config.verify.ts

check-coverage-deps: check-test-deps
	@python3 -c 'import coverage; print("coverage", coverage.__version__)' >/dev/null 2>&1 || { echo "ERROR: coverage is required"; exit 1; }
	@python3 -c 'import pytest_cov; print("pytest-cov", pytest_cov.__version__)' >/dev/null 2>&1 || { echo "ERROR: pytest-cov is required"; exit 1; }

coverage: check-coverage-deps coverage-python coverage-ts

coverage-python: check-coverage-deps
	@python3 -m pytest tests -q \
		--cov=kernel \
		--cov=code-index \
		--cov=judgment-memory \
		--cov=local-memory \
		--cov-branch \
		--cov-context=test \
		--cov-report=term-missing \
		--cov-report=xml:coverage.xml
	@coverage report -m --fail-under=40
	@coverage xml -o coverage.xml
	@coverage json --show-contexts -o coverage-contexts.json

coverage-ts: check-test-deps check-test-discovery
	@set -eu; \
	trap 'rm -f tests/kernel/plugins tests/functional/plugins tests/functional/judgment_memory/plugins' EXIT; \
	ln -sfn ../../../plugins tests/kernel/plugins; \
	ln -sfn ../../plugins tests/functional/plugins; \
	ln -sfn ../../../plugins tests/functional/judgment_memory/plugins; \
	rm -rf coverage-bun; \
	bun test --coverage --coverage-reporter=lcov --coverage-dir=coverage-bun tests; \
	test -s coverage-bun/lcov.info

bootstrap:
	@bash scripts/setup.sh

health:
	@bash scripts/health.sh

docker-up:
	@cd docker && docker compose up -d

docker-down:
	@cd docker && docker compose down

clean:
	@rm -f local-memory/memory.db code-index/.codeindex/manifest.db judgment-memory/judgment-memory.db coverage.xml coverage-contexts.json
	@rm -rf coverage-bun
