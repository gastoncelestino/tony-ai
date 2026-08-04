#!/usr/bin/env bash
# scripts/setup.sh — bootstrap idempotente para tony-ai.
# Valida Python/Bun/Ollama/Qdrant, baja modelos de embedding y regenera
# opencode.json con rutas relativas via {env:TONY_REPO_ROOT}.
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

# 3. Docker (warning, no error)
hdr "Docker"
if command -v docker >/dev/null 2>&1; then
  ok "docker $(docker --version | awk '{print $3}' | sed 's/,//')"
else
  printf "  \033[33mwarn\033[0m docker no encontrado - asume Ollama/Qdrant nativos\n"
fi

# 4. Ollama + pull de modelos
hdr "Ollama (${OLLAMA_URL})"
if curl -sf -m 5 "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
  ok "Ollama respondiendo en ${OLLAMA_URL}"
  if command -v ollama >/dev/null 2>&1; then
    for m in "${JUDGMENT_EMBED_MODEL}" "${CODE_EMBED_MODEL}"; do
      printf "  . ollama pull %s ...\n" "${m}"
      if ollama pull "${m}" >/dev/null 2>&1; then
        ok "modelo ${m} listo"
      else
        bad "ollama pull ${m} fallo"
      fi
    done
  else
    for m in "${JUDGMENT_EMBED_MODEL}" "${CODE_EMBED_MODEL}"; do
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

# 5. Qdrant
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

# 6. Regenerar opencode.json idempotentemente
hdr "opencode.json (TONY_REPO_ROOT)"
OPENCODE_JSON="${REPO_ROOT}/opencode.json"
if [[ -f "${OPENCODE_JSON}" ]]; then
  # Backup unico por maquina
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
    # Normalizar command a ["python3", "{env:TONY_REPO_ROOT}/<subpath>"]
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

# 7. .env.example
hdr ".env"
cat > "${REPO_ROOT}/.env.example" <<'ENVEOF'
# Tony-AI bootstrap env. Copia a .env o exporta en tu shell.

# Requerida por todos los MCP servers - apunta a la raiz del repo clonado.
TONY_REPO_ROOT=/abs/path/to/tony-ai

# Endpoints de servicios (coinciden con docker/docker-compose.yml).
TONY_OLLAMA_URL=http://localhost:11434
TONY_QDRANT_URL=http://localhost:6333

# Modelos de embedding (deben matchear opencode.json).
JUDGMENT_EMBED_MODEL=nomic-embed-text
CODE_EMBED_MODEL=bge-m3

# Chunker de code-index: "regex" (default, sin deps extra) o "tree-sitter"
# (mas robusto en archivos densos; requiere
#   pip install tree-sitter tree-sitter-languages).
TONY_INDEX_CHUNKER=regex
ENVEOF
ok ".env.example escrito - copia a .env y ajusta TONY_REPO_ROOT"

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
echo "  export TONY_REPO_ROOT=\"${REPO_ROOT}\""
echo "  make test     # test_core.py + test_ledger.py + test_hooks.ts"
echo "  make health   # OpenCode/MCP/Ollama/Qdrant/embeddings check unificado"
