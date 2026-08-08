#!/usr/bin/env bash
# scripts/setup.sh — bootstrap idempotente para tony-ai.
# Valida Python/Bun/OpenCode/Docker, levanta Ollama+Qdrant via Docker si no
# hay nada corriendo (respeta instalacion nativa), baja TODOS los modelos,
# y regenera opencode.json con rutas relativas via {env:TONY_REPO_ROOT}.
#
# Uso:  ./scripts/setup.sh        (o `make bootstrap`)
# Re-correr es seguro: ollama pull es idempotente y opencode.json solo
# se reescribe si encuentra una ruta absoluta residual (/home/<user>/.../server.py).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10

JUDGMENT_EMBED_MODEL="${JUDGMENT_EMBED_MODEL:-nomic-embed-text}"
CODE_EMBED_MODEL="${CODE_EMBED_MODEL:-bge-m3}"
OLLAMA_URL="${TONY_OLLAMA_URL:-http://localhost:11434}"
QDRANT_URL="${TONY_QDRANT_URL:-http://localhost:6333}"

PASS=0; FAIL=0
ok()   { printf "  \033[32mok\033[0m   %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  \033[31mFAIL\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }
hdr()  { printf "\n\033[1m-- %s --\033[0m\n" "$1"; }

# 1. Python
hdr "Python"
if command -v python3 >/dev/null 2>&1; then
  PY_VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  if python3 -c "import sys; sys.exit(0 if sys.version_info >= (${PYTHON_MIN_MAJOR}, ${PYTHON_MIN_MINOR}) else 1)"; then
    ok "python3 ${PY_VER} >= ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}"
  else
    bad "python3 ${PY_VER} < ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR} requerido"
  fi
else
  bad "python3 no esta en PATH"
fi

# 2. Bun
hdr "Bun"
if command -v bun >/dev/null 2>&1; then
  ok "bun $(bun --version)"
else
  bad "bun no esta instalado (https://bun.sh)"
fi

# 3. OpenCode CLI
hdr "OpenCode CLI"
if command -v opencode >/dev/null 2>&1; then
  ok "opencode $(opencode --version 2>/dev/null || echo 'instalado')"
else
  bad "opencode CLI no esta en PATH (https://opencode.ai)"
fi

# 4. Docker (warning, no error)
hdr "Docker"
DOCKER_AVAILABLE=0
if command -v docker >/dev/null 2>&1; then
  ok "docker $(docker --version | awk '{print $3}' | sed 's/,//')"
  DOCKER_AVAILABLE=1
else
  printf "  \033[33mwarn\033[0m docker no encontrado - asume Ollama/Qdrant nativos\n"
fi

# 4b. Servicios de soporte: auto-levantar Docker solo si no hay nada corriendo
#     (respeta a quien ya tiene Ollama/Qdrant nativos o levantados a mano).
hdr "Servicios de soporte (Ollama + Qdrant)"
OLLAMA_UP=0; QDRANT_UP=0
curl -sf -m 5 "${OLLAMA_URL}/api/tags" >/dev/null 2>&1 && OLLAMA_UP=1
curl -sf -m 5 "${QDRANT_URL}/readyz" >/dev/null 2>&1 && QDRANT_UP=1

if [[ "${OLLAMA_UP}" -eq 1 && "${QDRANT_UP}" -eq 1 ]]; then
  ok "Ollama y Qdrant ya responden - no se levanta nada (modo nativo/ya activo)"
elif [[ "${DOCKER_AVAILABLE}" -eq 1 ]]; then
  if [[ -f "${REPO_ROOT}/docker/docker-compose.yml" ]]; then
    printf "  . docker compose up -d ollama qdrant ...\n"
    if docker compose -f "${REPO_ROOT}/docker/docker-compose.yml" up -d ollama qdrant >/dev/null 2>&1; then
      wait_for() {
        local url="$1" name="$2" timeout="${3:-60}" elapsed=0
        while [[ "${elapsed}" -lt "${timeout}" ]]; do
          curl -sf -m 3 "${url}" >/dev/null 2>&1 && return 0
          sleep 3; elapsed=$((elapsed+3))
        done
        return 1
      }
      printf "  . esperando que Ollama/Qdrant arranquen (hasta 60s) ...\n"
      wait_for "${OLLAMA_URL}/api/tags" "Ollama" 60 && ok "Ollama arriba via Docker" || bad "Ollama no respondio tras 60s"
      wait_for "${QDRANT_URL}/readyz"   "Qdrant" 60 && ok "Qdrant arriba via Docker" || bad "Qdrant no respondio tras 60s"
    else
      bad "docker compose up fallo - revisa docker/README.md o correlo manual: cd docker && docker compose up -d"
    fi
  else
    bad "no se encontro docker/docker-compose.yml - no se pueden levantar los servicios"
  fi
else
  bad "Ollama/Qdrant no responden y Docker no esta disponible - levantalos nativamente (ollama serve + docker run qdrant/qdrant) o instala Docker"
fi

# 5. Ollama + pull de modelos
hdr "Ollama (${OLLAMA_URL})"
if curl -sf -m 5 "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
  ok "Ollama respondiendo en ${OLLAMA_URL}"
  if command -v ollama >/dev/null 2>&1; then
    for m in "${JUDGMENT_EMBED_MODEL}" "${CODE_EMBED_MODEL}" \
             qwen3-coder:30b omnicoder:9b deepseek-r1:14b ornith:9b; do
      printf "  . ollama pull %s ...\n" "${m}"
      if ollama pull "${m}" >/dev/null 2>&1; then
        ok "modelo ${m} listo"
      else
        bad "ollama pull ${m} fallo"
      fi
    done
  else
    for m in "${JUDGMENT_EMBED_MODEL}" "${CODE_EMBED_MODEL}" \
             qwen3-coder:30b omnicoder:9b deepseek-r1:14b ornith:9b; do
      if curl -sf -m 30 "${OLLAMA_URL}/api/show" \
           -H "Content-Type: application/json" \
           -d "{\"name\":\"${m}\"}" >/dev/null 2>&1; then
        ok "modelo ${m} presente (probe /api/show)"
      else
        printf "  \033[33mwarn\033[0m modelo %s no detectado - bajalo manualmente\n" "${m}"
      fi
    done
  fi
else
  bad "Ollama no responde en ${OLLAMA_URL}"
fi

# 6. Qdrant
hdr "Qdrant (${QDRANT_URL})"
if curl -sf -m 5 "${QDRANT_URL}/readyz" >/dev/null 2>&1; then
  ok "Qdrant /readyz = 200"
  if curl -sf -m 5 "${QDRANT_URL}/collections" >/dev/null 2>&1; then
    ok "Qdrant REST /collections OK"
  else
    bad "Qdrant /readyz OK pero /collections falla"
  fi
else
  bad "Qdrant no responde en ${QDRANT_URL} (docker run -p 6333:6333 qdrant/qdrant)"
fi

# 7. tree-sitter (opcional, solo si TONY_INDEX_CHUNKER=tree-sitter)
hdr "tree-sitter (opcional)"
if [[ "${TONY_INDEX_CHUNKER:-regex}" == "tree-sitter" ]]; then
  printf "  . pip install -r requirements-optional.txt ...\n"
  if python3 -m pip install -r "${REPO_ROOT}/requirements-optional.txt" --quiet 2>/dev/null; then
    ok "tree-sitter instalado"
  else
    bad "pip install tree-sitter fallo"
  fi
else
  printf "  \033[33minfo\033[0m  tree-sitter no requerido (TONY_INDEX_CHUNKER=regex)\n"
fi

# 8. Regenerar opencode.json idempotentemente
hdr "opencode.json (TONY_REPO_ROOT)"
OPENCODE_JSON="${REPO_ROOT}/opencode.json"
if [[ -f "${OPENCODE_JSON}" ]]; then
  [[ -f "${OPENCODE_JSON}.bak" ]] || cp "${OPENCODE_JSON}" "${OPENCODE_JSON}.bak"

python3 - "${OPENCODE_JSON}" "${REPO_ROOT}" <<'PY'
import json, sys, os
path, root = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)

subpath = {
    "tonymem":         "local-memory/server.py",
    "code-index":      "code-index/server.py",
    "judgment-memory": "judgment-memory/server.py",
}

mcp = data.get("mcp", {})
for name, sp in subpath.items():
    if name not in mcp:
        continue
    entry = mcp[name]
    if entry.get("type") != "local":
        continue
    entry["command"] = ["python3", "{env:TONY_REPO_ROOT}/" + sp]
    env = entry.setdefault("environment", {})
    env.setdefault("TONY_REPO_ROOT", "{env:TONY_REPO_ROOT}")
    if name == "code-index":
        env.setdefault("TONY_INDEX_CHUNKER", "regex")
    mcp[name] = entry

data["mcp"] = mcp
with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

  if python3 -c "import json; json.load(open('${OPENCODE_JSON}'))"; then
    if grep -qE '/home/[a-zA-Z0-9_]+/[A-Za-z0-9_./-]+/server\.py' "${OPENCODE_JSON}"; then
      bad "opencode.json aun tiene rutas absolutas residuales"
    else
      ok "opencode.json regenerado y portable"
    fi
  else
    bad "opencode.json quedo invalido - restaura ${OPENCODE_JSON}.bak"
  fi
else
  bad "no se encontro ${OPENCODE_JSON}"
fi

# 9. .env.example
hdr ".env"
cat > "${REPO_ROOT}/.env.example" <<ENVEOF
# Tony-AI bootstrap env. Copia a .env o exporta en tu shell.

# Requerida por todos los MCP servers - apunta a la raiz del repo clonado.
TONY_REPO_ROOT=${REPO_ROOT}

# Endpoints de servicios (coinciden con docker/docker-compose.yml).
TONY_OLLAMA_URL=http://localhost:11434
TONY_QDRANT_URL=http://localhost:6333

# Modelos de embedding (deben matchear opencode.json).
JUDGMENT_EMBED_MODEL=nomic-embed-text
CODE_EMBED_MODEL=bge-m3

# Modelos principales (descargados por setup.sh).
# Qwen3-Coder 30B: planificacion y proposicion
# OmniCoder 9B: implementacion
# DeepSeek-R1 14B: revision y Judgment Day juez A
# Ornith 9B: archive y jd-fix-agent

# Chunker de code-index: "regex" (default, stdlib-only) o "tree-sitter"
# (opt-in, requiere pip install tree-sitter tree-sitter-languages).
TONY_INDEX_CHUNKER=regex
ENVEOF
ok ".env.example escrito con TONY_REPO_ROOT=${REPO_ROOT} - copia a .env"

# 10. Resumen y post-install
hdr "Resumen"
echo "  Pasados: ${PASS}"
echo "  Fallos:  ${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
  echo ""
  echo "Algunos chequeos fallaron. Re-ejecuta 'make bootstrap' cuando los corrijas,"
  echo "y 'make health' para verificar todo end-to-end."
  exit 1
fi

echo ""
echo "Tony-AI bootstrap completo."

SHELL_NAME="$(basename "${SHELL:-}")"
case "${SHELL_NAME}" in
  bash|zsh|fish)
    echo "  Agregá esto a tu ~/.${SHELL_NAME}rc si no lo tenés:"
    echo "    export TONY_REPO_ROOT=\"${REPO_ROOT}\""
    ;;
  *)
    echo "  export TONY_REPO_ROOT=\"${REPO_ROOT}\""
    ;;
esac

echo "  make test     # test_core.py + test_ledger.py + test_hooks.ts"
echo "  make health   # OpenCode/MCP/Ollama/Qdrant/embeddings check unificado"
