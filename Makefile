# Wrappers de conveniencia sobre los tests. Todo corre nativo

ENV_FILE := .env
TONY_RUNTIME_DIR ?= $(shell set -a; . ./$(ENV_FILE); printf '%s' "$$TONY_RUNTIME_DIR")
PYTHON_CACHE_DIR ?= $(shell set -a; . ./$(ENV_FILE); printf '%s' "$$PYTHON_CACHE_DIR")
PYTHONPYCACHEPREFIX ?= $(PYTHON_CACHE_DIR)
PYTEST_CACHE_DIR ?= $(PYTHON_CACHE_DIR)/pytest
export TONY_RUNTIME_DIR
export PYTHON_CACHE_DIR
export PYTHONPYCACHEPREFIX
export PYTEST_CACHE_DIR

.PHONY: setup health test-all test-ts check-test-deps check-test-discovery check-test-cache \
        check-coverage-deps test-python coverage coverage-python coverage-ts \
		clean-test-caches reset-memory

# Setup inicial del entorno local.
setup:
	@bash scripts/setup.sh

# Health check del proyecto.
health:
	@bash scripts/health.sh
	
# Tests Python
test-all: check-test-deps check-test-discovery test-python

# Tests TypeScripts
# `bun test <arg>` matchea <arg> como substring de la ruta completa, no como
# directorio literal - "tests" sin anclar tambien matchea "tests_backups".
# Por eso usamos ./tests explicito. Sale en 0 (no error) si todavia no hay
# ningun *.test.ts, porque este target esta listo para cuando los agregues,
# no forma parte de la cadena default de `test-all`.
test-ts: check-test-deps
	@mkdir -p "$(PYTHON_CACHE_DIR)"; \
	trap '$(MAKE) --no-print-directory clean-test-caches' EXIT; \
	if ! find tests -maxdepth 1 -type f -name '*.test.ts' -print -quit 2>/dev/null | grep -q .; then \
		echo "⚠ no hay ningun tests/*.test.ts todavia - nada que correr"; \
		exit 0; \
	fi; \
	bun test ./tests

check-test-deps:
	@if python3 -c 'import pytest; print("pytest", pytest.__version__)' 2>/dev/null; then \
		echo "✓ pytest disponible (PYTEST_CACHE_DIR=$(PYTEST_CACHE_DIR))"; \
	else \
		echo "⚠ pytest no disponible; usando unittest standalone"; \
	fi
	@if command -v bun >/dev/null 2>&1; then \
		echo "✓ bun disponible"; \
	else \
		echo "⚠ bun no disponible (solo necesario si agregas tests *.test.ts)"; \
	fi

# Mantiene las convenciones de descubrimiento: Python test_*.py/*_test.py, TypeScript *.test.ts/*.verify.ts.
# No exige un minimo de archivos por lenguaje — hoy tests/ solo tiene Python.
check-test-discovery:
	@set -eu; invalid_ts=$$(find tests -maxdepth 1 -type f -name '*.ts' ! -name '*.test.ts' ! -name '*.verify.ts' -print); invalid_py=$$(find tests -maxdepth 1 -type f -name '*.py' ! -name 'test_*.py' ! -name '*_test.py' ! -name '__init__.py' -print); if [ -n "$$invalid_ts" ]; then echo "ERROR: TypeScript tests no descubribles:"; echo "$$invalid_ts"; exit 1; fi; if [ -n "$$invalid_py" ]; then echo "ERROR: Python tests no descubribles:"; echo "$$invalid_py"; exit 1; fi; echo "✓ Test naming/discovery conventions valid"

# Verifica que pytest no haya creado estado dentro del checkout.
check-test-cache:
	@if [ -d .pytest_cache ]; then echo "ERROR: .pytest_cache fue creado dentro del checkout; usa make test"; exit 1; fi
	@if find kernel tests -type d -name '__pycache__' -print -quit | grep -q .; then echo "ERROR: __pycache__ fue creado dentro del checkout"; exit 1; fi
	@echo "✓ pytest cache fuera del checkout (PYTEST_CACHE_DIR=$(PYTEST_CACHE_DIR))"

check-coverage-deps: check-test-deps
	@python3 -c 'import coverage; print("coverage", coverage.__version__)'
	@python3 -c 'import pytest_cov; print("pytest-cov", pytest_cov.__version__)'

# La suite Python trata warnings como errores para mantener el contrato de 0 warnings.
# pytest recibe explícitamente el directorio de caché porque PYTEST_CACHE_DIR no es
# una variable reconocida automáticamente por pytest.
test-python: check-test-deps check-test-discovery
	@mkdir -p "$(PYTHON_CACHE_DIR)" "$(PYTEST_CACHE_DIR)"; \
	trap '$(MAKE) --no-print-directory clean-test-caches' EXIT; \
	PYTHONWARNINGS=error python3 -m pytest tests -v -o cache_dir="$(PYTEST_CACHE_DIR)" || \
	PYTHONWARNINGS=error python3 -m unittest discover -s tests -v

coverage: coverage-python coverage-ts

# Solo mide kernel/ porque es el unico modulo con tests activos hoy
# (code-index/judgment-memory/local-memory quedaron sin tests en tests_backups/).
coverage-python: check-coverage-deps
	@mkdir -p "$(PYTHON_CACHE_DIR)/coverage" "$(PYTEST_CACHE_DIR)"; \
	trap '$(MAKE) --no-print-directory clean-test-caches' EXIT; \
	export COVERAGE_FILE="$(PYTHON_CACHE_DIR)/coverage/.coverage"; \
	PYTHONWARNINGS=error python3 -m pytest tests -q \
	-o cache_dir="$(PYTEST_CACHE_DIR)" \
	--cov=kernel \
	--cov-branch \
	--cov-context=test \
	--cov-report=term-missing

# Standalone, misma logica que test-ts: listo para cuando haya tests *.test.ts.
coverage-ts: check-test-deps
	@mkdir -p "$(PYTHON_CACHE_DIR)/bun"; \
	trap '$(MAKE) --no-print-directory clean-test-caches' EXIT; \
	if ! find tests -maxdepth 1 -type f -name '*.test.ts' -print -quit 2>/dev/null | grep -q .; then \
		echo "⚠ no hay ningun tests/*.test.ts todavia - nada que medir"; \
		exit 0; \
	fi; \
	tmpdir=$$(mktemp -d "$(PYTHON_CACHE_DIR)/bun/coverage.XXXXXX"); \
	bun test --coverage --coverage-reporter=text --coverage-dir="$$tmpdir" ./tests

# Limpia SOLO lo que pudo haber quedado suelto dentro del checkout
# (.pytest_cache, __pycache__). NO toca $(PYTHON_CACHE_DIR) - ese vive
# afuera del checkout a proposito (PYTHONPYCACHEPREFIX) y debe persistir
# entre corridas; borrarlo entero despues de cada test anulaba el sentido
# de tenerlo afuera.
clean-test-caches:
	@removed=0; \
	if [ -d .pytest_cache ]; then rm -rf -- .pytest_cache; removed=1; fi; \
	if find kernel tests -type d -name '__pycache__' -print -quit 2>/dev/null | grep -q .; then \
		find kernel tests -type d -name '__pycache__' -prune -exec rm -rf -- {} + 2>/dev/null; \
		removed=1; \
	fi; \
	if [ "$$removed" -eq 1 ]; then echo "✓ cache local del checkout limpiado (.pytest_cache, __pycache__)"; \
	else echo "✓ nada que limpiar en el checkout"; fi

# Destructivo e irreversible: borra la memoria de decisiones (TonyMem) y el
# historial de Judgment Day. Separado de `clean` a proposito para que no se
# pueda borrar por accidente.
reset-memory:
	@echo "⚠  Esto borra local-memory/memory.db y judgment-memory.db (irrecuperables)."
	@printf "Confirmar? [y/N] "; read ans; [ "$$ans" = "y" ] || [ "$$ans" = "Y" ] || (echo "Cancelado."; exit 1)
	@rm -f local-memory/memory.db judgment-memory/judgment-memory.db
	@echo "✓ Memoria reseteada."