#!/usr/bin/env bash
# scripts/setup.sh — bootstrap idempotente para tony-ai.
# Requisitos obligatorios: Python 3.10+, Bun, OpenCode CLI, Ollama,
# Docker, GGA y tree-sitter.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  printf 'ERROR: .env no existe en %s\n' "${ENV_FILE}" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10
JUDGMENT_EMBED_MODEL="${JUDGMENT_EMBED_MODEL:-nomic-embed-text}"
CODE_EMBED_MODEL="${CODE_EMBED_MODEL:-bge-m3}"
IMPLEMENTATION_MODEL="${TONY_IMPLEMENTATION_MODEL:-carstenuhlig/omnicoder-2-9b:q4_k_m}"
OLLAMA_URL="${TONY_OLLAMA_URL:-http://localhost:11434}"
QDRANT_URL="${TONY_QDRANT_URL:-http://localhost:6333}"
TONY_INDEX_CHUNKER="${TONY_INDEX_CHUNKER:-tree-sitter}"
PASS=0; FAIL=0
ok() { printf "  \033[32mok\033[0m   %s\n" "$1"; PASS=$((PASS+1)); }
bad() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }
hdr() { printf "\n\033[1m-- %s --\033[0m\n" "$1"; }

# User-local executables installed by pip and GGA live here.
export PATH="${HOME}/.local/bin:${PATH}"

# Pytest cache lives outside /mnt/c checkouts to avoid WSL/DrvFS permission
# errors when pytest creates its temporary cache directories.
PYTEST_CACHE_DIR="/tmp/tony-ai-pytest"
hdr "Pytest cache"
if mkdir -p "${PYTEST_CACHE_DIR}" && [[ -w "${PYTEST_CACHE_DIR}" ]]; then
  ok "cache de pytest en ${PYTEST_CACHE_DIR}"
else
  bad "no se pudo preparar el cache de pytest en ${PYTEST_CACHE_DIR}"
fi

hdr "Python"
if command -v python3 >/dev/null 2>&1; then
  PY_VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  if python3 -c "import sys; sys.exit(0 if sys.version_info >= (${PYTHON_MIN_MAJOR}, ${PYTHON_MIN_MINOR}) else 1)"; then ok "python3 ${PY_VER} >= ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}"; else bad "python3 ${PY_VER} < ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR} requerido"; fi
else bad "python3 no esta en PATH"; fi

hdr "Bun"
if command -v bun >/dev/null 2>&1; then ok "bun $(bun --version)"; else bad "bun no esta instalado (https://bun.sh)"; fi

hdr "OpenCode CLI"
if command -v opencode >/dev/null 2>&1; then ok "opencode $(opencode --version 2>/dev/null || echo instalado)"; else bad "opencode CLI no esta en PATH (https://opencode.ai)"; fi

hdr "Docker"
DOCKER_AVAILABLE=0
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then ok "docker $(docker --version | awk '{print $3}' | sed 's/,//') y daemon disponible"; DOCKER_AVAILABLE=1; else bad "docker esta instalado pero el daemon no responde"; fi
else bad "docker no esta instalado"; fi

hdr "Ollama CLI"
if command -v ollama >/dev/null 2>&1; then ok "ollama $(ollama --version 2>/dev/null | head -1 || echo instalado)"; else bad "ollama no esta instalado"; fi

hdr "GGA"
if command -v gga >/dev/null 2>&1; then
  ok "$(gga --version 2>/dev/null | head -1)"
else
  GGA_DIR="${TMPDIR:-/tmp}/gentleman-guardian-angel"
  if ! command -v git >/dev/null 2>&1; then
    bad "gga no esta en PATH y git no esta instalado; no se puede instalar GGA"
  else
    if [[ -d "${GGA_DIR}/.git" ]]; then
      ok "repositorio GGA clonado"
    elif [[ -e "${GGA_DIR}" ]]; then
      bad "${GGA_DIR} existe pero no es un repositorio GGA"
    elif git clone https://github.com/Gentleman-Programming/gentleman-guardian-angel.git "${GGA_DIR}" >/dev/null 2>&1; then
      ok "repositorio GGA clonado"
    else
      bad "gga no esta en PATH y no se pudo clonar GGA"
    fi
    if [[ -d "${GGA_DIR}/.git" ]]; then
      printf "  . ejecutando ./install.sh ...\n"
      if (cd "${GGA_DIR}" && ./install.sh >/dev/null 2>&1); then
        export PATH="${HOME}/.local/bin:${PATH}"
        if command -v gga >/dev/null 2>&1; then
          ok "$(gga --version 2>/dev/null | head -1)"
        else
          bad "gga no esta en PATH despues de la instalacion; revisa ~/.local/bin"
        fi
      else
        bad "gga no esta en PATH y la instalacion de GGA fallo"
      fi
    fi
  fi
fi

hdr "Servicios de soporte (Ollama + Qdrant)"
OLLAMA_UP=0; QDRANT_UP=0
if command -v curl >/dev/null 2>&1; then
  curl -sf -m 5 "${OLLAMA_URL}/api/tags" >/dev/null 2>&1 && OLLAMA_UP=1
  curl -sf -m 5 "${QDRANT_URL}/readyz" >/dev/null 2>&1 && QDRANT_UP=1
else
  bad "curl no esta instalado; se necesita para verificar Ollama/Qdrant"
fi
[[ "${OLLAMA_UP}" -eq 1 ]] && ok "Ollama ya responde en ${OLLAMA_URL} - no se levanta container Ollama"
[[ "${QDRANT_UP}" -eq 1 ]] && ok "Qdrant ya responde en ${QDRANT_URL} - no se levanta container Qdrant"
SERVICES_TO_START=()
[[ "${OLLAMA_UP}" -eq 0 ]] && SERVICES_TO_START+=(ollama)
[[ "${QDRANT_UP}" -eq 0 ]] && SERVICES_TO_START+=(qdrant)
if [[ "${#SERVICES_TO_START[@]}" -gt 0 ]]; then
  if [[ "${DOCKER_AVAILABLE}" -eq 1 ]]; then
    if [[ -f "${REPO_ROOT}/docker/docker-compose.yml" ]]; then
      printf "  . docker compose up -d %s ...\n" "${SERVICES_TO_START[*]}"
      COMPOSE_ERR="$(mktemp)"
      if docker compose -f "${REPO_ROOT}/docker/docker-compose.yml" up -d "${SERVICES_TO_START[@]}" 2>"${COMPOSE_ERR}"; then
        rm -f "${COMPOSE_ERR}"
        wait_for() { local url="$1" timeout="${2:-60}" elapsed=0; while [[ "${elapsed}" -lt "${timeout}" ]]; do curl -sf -m 3 "${url}" >/dev/null 2>&1 && return 0; sleep 3; elapsed=$((elapsed+3)); done; return 1; }
        if [[ "${OLLAMA_UP}" -eq 0 ]]; then printf "  . esperando Ollama (hasta 60s) ...\n"; if wait_for "${OLLAMA_URL}/api/tags" 60; then OLLAMA_UP=1; ok "Ollama arriba via Docker"; else bad "Ollama no respondio tras 60s"; fi; fi
        if [[ "${QDRANT_UP}" -eq 0 ]]; then printf "  . esperando Qdrant (hasta 60s) ...\n"; if wait_for "${QDRANT_URL}/readyz" 60; then QDRANT_UP=1; ok "Qdrant arriba via Docker"; else bad "Qdrant no respondio tras 60s"; fi; fi
      else printf "  \033[31merror\033[0m docker compose: %s\n" "$(cat "${COMPOSE_ERR}")"; rm -f "${COMPOSE_ERR}"; bad "docker compose up fallo"; fi
    else bad "no se encontro docker/docker-compose.yml"; fi
  else bad "faltan servicios y Docker no esta disponible"; fi
fi

hdr "Ollama (${OLLAMA_URL})"
if curl -sf -m 5 "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
  ok "Ollama respondiendo en ${OLLAMA_URL}"
  for m in "${JUDGMENT_EMBED_MODEL}" "${CODE_EMBED_MODEL}" qwen3-coder:30b "${IMPLEMENTATION_MODEL}" deepseek-r1:14b ornith:9b; do
    printf "  . ollama pull %s ...\n" "${m}"
    if ollama pull "${m}" >/dev/null 2>&1; then ok "modelo ${m} listo"; else bad "ollama pull ${m} fallo"; fi
  done
else bad "Ollama no responde en ${OLLAMA_URL}"; fi

hdr "Qdrant (${QDRANT_URL})"
if curl -sf -m 5 "${QDRANT_URL}/readyz" >/dev/null 2>&1; then
  ok "Qdrant /readyz = 200"
  if curl -sf -m 5 "${QDRANT_URL}/collections" >/dev/null 2>&1; then ok "Qdrant REST /collections OK"; else bad "Qdrant /collections falla"; fi
else bad "Qdrant no responde en ${QDRANT_URL}"; fi

hdr "Python dev/test dependencies"
printf "  . pip install -r requirements-dev.txt ...\n"
if python3 -m pip install -r "${REPO_ROOT}/requirements-dev.txt" --break-system-packages; then
  if python3 -c 'import tree_sitter, tree_sitter_language_pack' >/dev/null 2>&1; then ok "pytest + tree-sitter + language pack instalados"; else bad "requirements-dev.txt termino pero tree-sitter no puede importarse"; fi
else bad "pip install -r requirements-dev.txt fallo"; fi

hdr ".env"
ok ".env cargado y no modificado"
if [[ -z "${TONY_RUNTIME_DIR:-}" ]]; then bad "TONY_RUNTIME_DIR falta o esta vacio en .env"; fi
if [[ -z "${PYTHONPYCACHEPREFIX:-}" ]]; then bad "PYTHONPYCACHEPREFIX falta o esta vacio en .env"; fi
if [[ "${PYTHONPYCACHEPREFIX:-}" == *"${REPO_ROOT}"* ]]; then bad "PYTHONPYCACHEPREFIX no puede apuntar al checkout"; fi

hdr "Resumen"
echo "  Pasados: ${PASS}"
echo "  Fallos:  ${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then echo "Algunos chequeos fallaron. Corrige los requisitos y vuelve a ejecutar ./scripts/setup.sh"; exit 1; fi
echo ""; echo "Tony-AI bootstrap completo."; echo "  make test"; echo "  make health"
