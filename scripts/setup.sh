#!/usr/bin/env bash
# scripts/setup.sh — bootstrap idempotente para tony-ai.
# Requisitos obligatorios: Python 3.10+, Bun, OpenCode CLI, llama.cpp
# (llama-server) + llama-swap, Qdrant, GGA y tree-sitter. Sin Docker: todo
# corre nativo (llama-server/llama-swap sirven tanto chat como embeddings).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10
JUDGMENT_EMBED_MODEL="${JUDGMENT_EMBED_MODEL:-nomic-embed-text}"
CODE_EMBED_MODEL="${CODE_EMBED_MODEL:-bge-m3}"
# Estos IDs deben coincidir con las claves/aliases definidos en el
PLANNING_MODEL="${TONY_PLANNING_MODEL:-qwen3-coder:30b}"
IMPLEMENTATION_MODEL="${TONY_IMPLEMENTATION_MODEL:-omnicoder:9b}"
REVIEW_MODEL="${TONY_REVIEW_MODEL:-deepseek-r1-8b}"
LLAMASWAP_URL="${TONY_LLAMASWAP_URL:-http://localhost:8080}"
# llama-swap lee el config.yaml directamente desde el repo
LLAMASWAP_CONFIG="${TONY_LLAMASWAP_CONFIG:-${REPO_ROOT}/config.yaml}"
LLAMA_SERVER_BIN="${TONY_LLAMA_SERVER_BIN:-${HOME}/llama.cpp/build/bin/llama-server}"
# Si un modelo nunca se cargo antes, la primera request tarda en levantar
# el proceso de llama-server y leer el GGUF. Este timeout es solo para el
# "warm-up" que hace este script, no un limite de tony-ai en produccion.
MODEL_WARMUP_TIMEOUT="${TONY_MODEL_WARMUP_TIMEOUT:-120}"
QDRANT_URL="${TONY_QDRANT_URL:-http://localhost:6333}"
# Nombre historico de la variable (la lee code-index/, judgment-memory/ y
# plugins/qdrant.ts) pero se sirven via llama-swap: nomic-embed-text y bge-m3
# estan declarados en config.yaml y los sirve el mismo llama-swap que los
# modelos de chat, via /v1/embeddings compatible con OpenAI.
EMBEDDINGS_URL="${TONY_EMBEDDINGS_URL:-http://localhost:8080}"
# Opcional: binario nativo de Qdrant para autoarrancarlo si no esta
# corriendo (sin Docker). Dejalo vacio si preferis levantarlo vos mismo
# (systemd, manualmente, etc.) - el script solo lo va a chequear.
QDRANT_BIN="${TONY_QDRANT_BIN:-}"
QDRANT_STORAGE_DIR="${TONY_QDRANT_STORAGE_DIR:-${HOME}/.tony-ai/qdrant/storage}"
PYTHON_CACHE_DIR="${PYTHON_CACHE_DIR:-${HOME}/.tony-ai/pycache}"
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${PYTHON_CACHE_DIR}}"
PYTEST_CACHE_DIR="${PYTEST_CACHE_DIR:-${PYTHON_CACHE_DIR}/pytest}"
export PYTHON_CACHE_DIR PYTHONPYCACHEPREFIX PYTEST_CACHE_DIR
TONY_INDEX_CHUNKER=tree-sitter
PASS=0; FAIL=0
ok() { printf "  \033[32mok\033[0m   %s\n" "$1"; PASS=$((PASS+1)); }
bad() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }
hdr() { printf "\n\033[1m-- %s --\033[0m\n" "$1"; }

# User-local executables installed by pip and GGA live here.
export PATH="${HOME}/.local/bin:${PATH}"

# Pytest cache follows the canonical environment configuration from .env.
# Do not hardcode a checkout-local cache or a second cache location here.
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

hdr "llama.cpp (llama-server)"
if [[ -x "${LLAMA_SERVER_BIN}" ]]; then
  ok "llama-server encontrado en ${LLAMA_SERVER_BIN}"
else
  bad "no se encontro un binario ejecutable de llama-server en ${LLAMA_SERVER_BIN} (compilalo con cmake -DGGML_CUDA=ON o ajusta TONY_LLAMA_SERVER_BIN en .env)"
fi

hdr "llama-swap CLI"
if command -v llama-swap >/dev/null 2>&1; then
  ok "llama-swap $(llama-swap --version 2>/dev/null | head -1 || echo instalado)"
else
  bad "llama-swap no esta en PATH (brew tap mostlygeek/llama-swap && brew install llama-swap, o bajar el binario de github.com/mostlygeek/llama-swap/releases)"
fi

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

hdr "Config de llama-swap"
if [[ -f "${LLAMASWAP_CONFIG}" ]]; then
  ok "config.yaml encontrado en ${LLAMASWAP_CONFIG}"
else
  bad "no se encontro ${LLAMASWAP_CONFIG} (ajusta TONY_LLAMASWAP_CONFIG en .env o crea config.yaml en la raiz del repo)"
fi

hdr "Servicios de soporte (llama-swap + Qdrant)"
# Ambos corren nativos, sin Docker: llama-swap ya lo maneja el bloque de
# abajo; Qdrant, si no responde y hay un binario declarado en
# TONY_QDRANT_BIN, lo autoarrancamos aca del mismo modo.
LLAMASWAP_UP=0; QDRANT_UP=0
if command -v curl >/dev/null 2>&1; then
  curl -sf -m 5 "${LLAMASWAP_URL}/health" >/dev/null 2>&1 && LLAMASWAP_UP=1
  curl -sf -m 5 "${QDRANT_URL}/readyz" >/dev/null 2>&1 && QDRANT_UP=1
else
  bad "curl no esta instalado; se necesita para verificar llama-swap/Qdrant"
fi

if [[ "${QDRANT_UP}" -eq 1 ]]; then
  ok "Qdrant ya responde en ${QDRANT_URL}"
elif [[ -n "${QDRANT_BIN}" ]] && command -v "${QDRANT_BIN}" >/dev/null 2>&1; then
  printf "  . levantando Qdrant en background (storage: %s) ...\n" "${QDRANT_STORAGE_DIR}"
  mkdir -p "${QDRANT_STORAGE_DIR}"
  QDRANT_LOG="${PYTHON_CACHE_DIR}/qdrant.log"
  QDRANT__STORAGE__STORAGE_PATH="${QDRANT_STORAGE_DIR}" nohup "${QDRANT_BIN}" >"${QDRANT_LOG}" 2>&1 &
  disown
  elapsed=0
  while [[ "${elapsed}" -lt 30 ]]; do
    curl -sf -m 3 "${QDRANT_URL}/readyz" >/dev/null 2>&1 && { QDRANT_UP=1; break; }
    sleep 2; elapsed=$((elapsed+2))
  done
  if [[ "${QDRANT_UP}" -eq 1 ]]; then ok "Qdrant arriba en ${QDRANT_URL} (log: ${QDRANT_LOG})"; else bad "Qdrant no respondio tras 30s (revisa ${QDRANT_LOG})"; fi
else
  bad "Qdrant no responde en ${QDRANT_URL} y no se pudo autoarrancar (instalalo nativo y seteá TONY_QDRANT_BIN, o levantalo vos mismo antes de correr este script)"
fi

if [[ "${LLAMASWAP_UP}" -eq 0 ]]; then
  if command -v llama-swap >/dev/null 2>&1 && [[ -f "${LLAMASWAP_CONFIG}" ]]; then
    printf "  . levantando llama-swap en background (config: %s) ...\n" "${LLAMASWAP_CONFIG}"
    LLAMASWAP_LOG="${PYTHON_CACHE_DIR}/llama-swap.log"
    nohup llama-swap --config "${LLAMASWAP_CONFIG}" --listen "$(echo "${LLAMASWAP_URL}" | sed -E 's#^https?://##')" >"${LLAMASWAP_LOG}" 2>&1 &
    disown
    elapsed=0
    while [[ "${elapsed}" -lt 30 ]]; do
      curl -sf -m 3 "${LLAMASWAP_URL}/health" >/dev/null 2>&1 && { LLAMASWAP_UP=1; break; }
      sleep 2; elapsed=$((elapsed+2))
    done
    if [[ "${LLAMASWAP_UP}" -eq 1 ]]; then ok "llama-swap arriba en ${LLAMASWAP_URL} (log: ${LLAMASWAP_LOG})"; else bad "llama-swap no respondio tras 30s (revisa ${LLAMASWAP_LOG})"; fi
  else
    bad "llama-swap no responde en ${LLAMASWAP_URL} y no se pudo autoarrancar (falta el binario o ${LLAMASWAP_CONFIG})"
  fi
else
  ok "llama-swap ya responde en ${LLAMASWAP_URL}"
fi

hdr "llama-swap (${LLAMASWAP_URL})"
if curl -sf -m 5 "${LLAMASWAP_URL}/health" >/dev/null 2>&1; then
  ok "llama-swap respondiendo en ${LLAMASWAP_URL}"

  # llama-swap no "descarga" modelos: los toma de
  # rutas locales de GGUF definidas en config.yaml. Ac\u00e1 verificamos que
  # cada modelo requerido este declarado (via /v1/models) y, si
  # TONY_WARM_MODELS=1 (default), forzamos una carga real con una request
  # minima para detectar problemas de ruta/VRAM antes de que los pegue
  # tony-ai en produccion.
  MODELS_JSON="$(curl -sf -m 5 "${LLAMASWAP_URL}/v1/models" 2>/dev/null || echo '')"
  WARM_MODELS="${TONY_WARM_MODELS:-1}"

  for m in "${PLANNING_MODEL}" "${IMPLEMENTATION_MODEL}" "${REVIEW_MODEL}"; do
    if ! grep -q "\"${m}\"" <<<"${MODELS_JSON}"; then
      bad "modelo ${m} no aparece en ${LLAMASWAP_URL}/v1/models (revisa aliases en ${LLAMASWAP_CONFIG})"
      continue
    fi
    if [[ "${WARM_MODELS}" -eq 1 ]]; then
      printf "  . cargando %s (timeout %ss) ...\n" "${m}" "${MODEL_WARMUP_TIMEOUT}"
      if curl -sf -m "${MODEL_WARMUP_TIMEOUT}" "${LLAMASWAP_URL}/v1/chat/completions" \
          -H "Content-Type: application/json" \
          -d "{\"model\":\"${m}\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":1}" \
          >/dev/null 2>&1; then
        ok "modelo ${m} carga y responde"
      else
        bad "modelo ${m} esta declarado pero no respondio dentro de ${MODEL_WARMUP_TIMEOUT}s (VRAM insuficiente, ruta de GGUF invalida, o --n-gpu-layers mal ajustado)"
      fi
    else
      ok "modelo ${m} declarado en llama-swap (warm-up salteado, TONY_WARM_MODELS=0)"
    fi
  done

  # nomic-embed-text y bge-m3 estan declarados en config.yaml y los sirve
  # el mismo llama-swap que los modelos de chat (un unico servidor para todo),
  # asi que los verificamos igual que a los modelos de chat: que esten
  # declarados y, si TONY_WARM_MODELS=1, que efectivamente respondan.
  for m in "${JUDGMENT_EMBED_MODEL}" "${CODE_EMBED_MODEL}"; do
    if ! grep -q "\"${m}\"" <<<"${MODELS_JSON}"; then
      bad "modelo de embeddings ${m} no aparece en ${LLAMASWAP_URL}/v1/models (revisa aliases en ${LLAMASWAP_CONFIG})"
      continue
    fi
    if [[ "${WARM_MODELS}" -eq 1 ]]; then
      printf "  . cargando %s (embeddings, timeout %ss) ...\n" "${m}" "${MODEL_WARMUP_TIMEOUT}"
      if curl -sf -m "${MODEL_WARMUP_TIMEOUT}" "${EMBEDDINGS_URL}/v1/embeddings" \
          -H "Content-Type: application/json" \
          -d "{\"model\":\"${m}\",\"input\":[\"ping\"]}" \
          >/dev/null 2>&1; then
        ok "modelo de embeddings ${m} carga y responde"
      else
        bad "modelo de embeddings ${m} esta declarado pero no respondio dentro de ${MODEL_WARMUP_TIMEOUT}s"
      fi
    else
      ok "modelo de embeddings ${m} declarado en llama-swap (warm-up salteado, TONY_WARM_MODELS=0)"
    fi
  done
else
  bad "llama-swap no responde en ${LLAMASWAP_URL}"
fi

hdr "Qdrant (${QDRANT_URL})"
if curl -sf -m 5 "${QDRANT_URL}/readyz" >/dev/null 2>&1; then
  ok "Qdrant /readyz = 200"
  if curl -sf -m 5 "${QDRANT_URL}/collections" >/dev/null 2>&1; then ok "Qdrant REST /collections OK"; else bad "Qdrant /collections falla"; fi
else bad "Qdrant no responde en ${QDRANT_URL}"; fi

hdr "Python dev/test dependencies"
printf "  . pip install -r requirements-dev.txt ...\n\n"
if python3 -m pip install -r "${REPO_ROOT}/requirements-dev.txt" --break-system-packages; then
  if python3 -c 'import tree_sitter, tree_sitter_language_pack' >/dev/null 2>&1; then ok "pytest + tree-sitter + language pack instalados"; else bad "requirements-dev.txt termino pero tree-sitter no puede importarse"; fi
else bad "pip install -r requirements-dev.txt fallo"; fi

hdr ".env"
if [[ ! -f "${ENV_FILE}" ]]; then
  bad ".env no existe en ${ENV_FILE}"
else
  ok ".env encontrado (no modificado)"
  set +u
  ENV_VALID=0
  REQUIRED_VARS=("TONY_RUNTIME_DIR" "PYTHONPYCACHEPREFIX" "TONY_LLAMASWAP_URL" "TONY_LLAMASWAP_CONFIG" "TONY_QDRANT_URL" "TONY_EMBEDDINGS_URL" "JUDGMENT_EMBED_MODEL" "CODE_EMBED_MODEL" "TONY_IMPLEMENTATION_MODEL" "TONY_INDEX_CHUNKER")

  if ENV_CHECK=$(bash -c "set -a; source '${ENV_FILE}'; set +a; for var in ${REQUIRED_VARS[*]}; do echo \"\${!var}\"; done"); then
    mapfile -t ENV_VALUES < <(echo "$ENV_CHECK")
    MISSING=0
    for i in "${!REQUIRED_VARS[@]}"; do
      if [[ -z "${ENV_VALUES[$i]}" ]]; then
        bad "variable requerida ${REQUIRED_VARS[$i]} falta o vacía en .env"
        MISSING=$((MISSING+1))
      fi
    done

    if [[ "${MISSING}" -eq 0 ]]; then
      # Reusamos las variables ya cargadas por el `source "${ENV_FILE}"`
      # del inicio del script (bash ya expandio ahi cualquier ${VAR}
      # anidada). Releer el .env "a mano" con grep/cut como antes NO
      # expande nada y rompe casos como TONY_LLAMASWAP_CONFIG=${TONY_RUNTIME_DIR}/...

      if [[ ! "${TONY_LLAMASWAP_URL}" =~ ^https?:// ]]; then
        bad "TONY_LLAMASWAP_URL debe ser http(s)://"
      elif curl -sf -m 5 "${TONY_LLAMASWAP_URL}/health" >/dev/null 2>&1; then
        ok "TONY_LLAMASWAP_URL=${TONY_LLAMASWAP_URL} accesible"
      else
        bad "TONY_LLAMASWAP_URL=${TONY_LLAMASWAP_URL} no es accesible"
      fi

      if [[ -f "${TONY_LLAMASWAP_CONFIG}" ]]; then
        ok "TONY_LLAMASWAP_CONFIG=${TONY_LLAMASWAP_CONFIG} existe"
      else
        bad "TONY_LLAMASWAP_CONFIG=${TONY_LLAMASWAP_CONFIG} no existe"
      fi

      if [[ ! "${TONY_QDRANT_URL}" =~ ^https?:// ]]; then
        bad "TONY_QDRANT_URL debe ser http(s)://"
      elif curl -sf -m 5 "${TONY_QDRANT_URL}/readyz" >/dev/null 2>&1; then
        ok "TONY_QDRANT_URL=${TONY_QDRANT_URL} accesible"
      else
        bad "TONY_QDRANT_URL=${TONY_QDRANT_URL} no es accesible"
      fi

      if [[ ! "${TONY_EMBEDDINGS_URL}" =~ ^https?:// ]]; then
        bad "TONY_EMBEDDINGS_URL debe ser http(s)://"
      elif curl -sf -m 5 "${TONY_EMBEDDINGS_URL}/health" >/dev/null 2>&1; then
        ok "TONY_EMBEDDINGS_URL=${TONY_EMBEDDINGS_URL} accesible (embeddings via llama-swap)"
      else
        bad "TONY_EMBEDDINGS_URL=${TONY_EMBEDDINGS_URL} no es accesible"
      fi
    else
      bad ".env tiene ${MISSING} variable(s) faltante(s) o vacía(s)"
    fi
  else
    bad "no se pudo parsear .env"
  fi
  set -u
fi

hdr "Resumen"
echo "  Pasados: ${PASS}"
echo "  Fallos:  ${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then echo "Algunos chequeos fallaron. Corrige los requisitos y vuelve a ejecutar ./scripts/setup.sh"; exit 1; fi
echo ""; echo "Tony-AI setup completo."; echo "  make test"; echo "  make health"
