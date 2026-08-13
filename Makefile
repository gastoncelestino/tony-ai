# Makefile para Tony-AI
# Wrappers de conveniencia sobre tests locales y smoke tests externos.

.PHONY: test test-all check-test-deps check-test-discovery check-prompts check-phase-context check-launcher test-python test-ts test-kernel check-coverage-deps coverage coverage-python coverage-ts verify-qdrant verify-sdd-flow docker-up docker-down clean bootstrap health validate-config

# Ejecuta la suite normal: validaciones de prompts/configuración + Python + TypeScript.
test: check-test-deps check-test-discovery check-prompts check-phase-context check-launcher test-python test-ts validate-config

# test-all agrega las pruebas específicas del kernel y del flujo SDD end-to-end.
test-all: test test-kernel

check-test-deps:
	@if python3 -c 'import pytest; print("pytest", pytest.__version__)' 2>/dev/null; then echo "✓ pytest disponible"; else echo "⚠ pytest no disponible; usando test runners standalone"; fi
	@command -v bun >/dev/null 2>&1 || (echo "ERROR: falta Bun."; exit 1)

# Mantiene las convenciones de descubrimiento: TypeScript *.test.ts y Python test_*.py/*_test.py.
check-test-discovery:
	@set -eu; invalid_ts=$$(find tests -maxdepth 1 -type f -name '*.ts' ! -name '*.test.ts' -print); invalid_py=$$(find tests -maxdepth 1 -type f -name '*.py' ! -name 'test_*.py' ! -name '*_test.py' ! -name '__init__.py' -print); if [ -n "$$invalid_ts" ]; then echo "ERROR: TypeScript tests no descubribles:"; echo "$$invalid_ts"; exit 1; fi; if [ -n "$$invalid_py" ]; then echo "ERROR: Python tests no descubribles:"; echo "$$invalid_py"; exit 1; fi; test -n "$$(find tests -maxdepth 1 -type f -name '*.test.ts' -print -quit)" || { echo "ERROR: no hay tests TypeScript descubribles"; exit 1; }; echo "✓ Test naming/discovery conventions valid"

# Verifica que dev no vuelva a depender del sistema de prompts generados.
check-prompts:
	@set -eu; 	test ! -d prompts/generated || { echo "ERROR: prompts/generated no debe existir en dev"; exit 1; }; 	test ! -f prompts/agents/includes/phase-manifest.json || { echo "ERROR: phase-manifest.json no debe existir en dev"; exit 1; }; 	grep -q '"prompt": "./prompts/agents/tony-orchestrator.md"' opencode.json || { echo "ERROR: orchestrator debe usar el prompt fuente"; exit 1; }; 	for phase in sdd-init sdd-onboard sdd-explore sdd-propose sdd-spec sdd-design sdd-tasks sdd-apply sdd-verify sdd-archive; do 		grep -q ""prompt": "./prompts/sdd/$$phase.md"" opencode.json || { echo "ERROR: $$phase no apunta a su prompt fuente"; exit 1; }; 	done; 	echo "✓ Phase prompts are plain, source-controlled, and non-generated"

# Verifica que los contratos de infraestructura/review no se inyecten directamente
# en los phase prompts y que éstos no vuelvan a usar el mecanismo de includes dinámicos.
check-phase-context:
	@set -eu; 	for forbidden in persistence-contract.md sdd-status-contract.md skill-resolver.md review-ledger-contract.md; do 		if grep -R -n --include='sdd-*.md' "$$forbidden" prompts/sdd 2>/dev/null; then 			echo "ERROR: $$forbidden no debe formar parte del contexto directo de los SDD phase prompts"; 			exit 1; 		fi; 	done; 	if grep -R -n --include='sdd-*.md' 'phase-manifest.json\|prompts/generated\|{{include:' prompts/sdd 2>/dev/null; then 		echo "ERROR: un phase prompt todavía referencia el mecanismo de prompts generado/dinámico"; 		exit 1; 	fi; 	echo "✓ SDD phase prompts keep infrastructure/review contracts out of direct context"

# El launcher sólo enruta/delega: no debe construir prompts ni resolver manifests/includes.
check-launcher:
	@set -eu; 	test -f prompts/agents/includes/phase-launcher.md || { echo "ERROR: falta phase-launcher.md"; exit 1; }; 	if grep -n 'phase-manifest.json\|prompts/generated\|{{include:' prompts/agents/includes/phase-launcher.md 2>/dev/null; then 		echo "ERROR: phase-launcher.md todavía referencia el sistema de composición eliminado"; 		exit 1; 	fi; 	echo "✓ Phase launcher uses routing/delegation only"

# Python usa pytest cuando está disponible y conserva el runner standalone como fallback.
test-python: check-test-deps check-test-discovery
	@python3 -m pytest tests -q 2>/dev/null || python3 tools/run-python-tests.py tests

# Kernel y SDD flow se mantienen separados para poder diagnosticar fallos específicos.
test-kernel: check-test-deps check-test-discovery
	@python3 -m pytest tests/test_kernel_*.py tests/test_sdd_flow_e2e.py -v 2>/dev/null || python3 tools/run-python-tests.py tests/test_kernel_cli.py tests/test_kernel_enforcement.py tests/test_sdd_flow_e2e.py
	@bun test tests/tony_kernel_*.test.ts

# TypeScript se ejecuta con Bun.
test-ts: check-test-deps check-test-discovery
	@bun test tests

check-coverage-deps: check-test-deps
	@python3 -c 'import coverage; print("coverage", coverage.__version__)'

coverage: check-coverage-deps coverage-python coverage-ts

# Coverage Python cubre los módulos principales del runtime.
coverage-python: check-coverage-deps
	@coverage run --source=kernel,code-index,judgment-memory,local-memory -m pytest tests -q || coverage run --source=kernel,code-index,judgment-memory,local-memory tools/run-python-tests.py tests
	@coverage report -m --fail-under=40
	@coverage xml -o coverage.xml

# Coverage TypeScript usa el reporte LCOV de Bun.
coverage-ts: check-test-deps check-test-discovery
	@rm -rf coverage-bun
	@bun test --coverage --coverage-reporter=lcov --coverage-dir=coverage-bun tests
	@test -s coverage-bun/lcov.info

# Smoke test de conexión/configuración de Qdrant.
verify-qdrant:
	@cd judgment-memory && bun run scripts/verify-qdrant.ts

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

# Detiene los servicios Docker.
docker-down:
	@cd docker && docker compose down

# Limpieza de bases locales y artefactos de coverage.
clean:
	@rm -f local-memory/memory.db code-index/.codeindex/manifest.db judgment-memory/judgment-memory.db coverage.xml
	@rm -rf coverage-bun

# Valida la configuración de OpenCode/proyecto.
validate-config:
	@bun run tools/validate-config.ts
