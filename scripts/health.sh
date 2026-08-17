#!/usr/bin/env bash
# scripts/health.sh - verificacion unificada end-to-end.
# Imprime OK/FAIL por componente y sale con codigo !=0 si algo critico falla.
#
# Componentes:
#   OpenCode     opencode.json existe, parsea y no tiene rutas absolutas.
#   MCP          los 4 servers arrancan y responden 'initialize' JSON-RPC.
#   Ollama       /api/tags responde y los modelos de embedding estan pull-eados.
#   Qdrant       /readyz 200 y /collections responde.
#   Disk         directorios .tonymem/ existen y son escribibles.
#   embeddings   judgment_qdrant.verify.ts pasa (roundtrip embed+upsert+search).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${TONY_REPO_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
export TONY_REPO_ROOT

OLLAMA_URL="${TONY_OLLAMA_URL:-http://localhost:11434}"
QDRANT_URL="${TONY_QDRANT_URL:-http://localhost:6333}"
EMBED_MODEL="${JUDGMENT_EMBED_MODEL:-nomic-embed-text}"
CODE_EMBED_MODEL="${CODE_EMBED_MODEL:-bge-m3}"

declare -A STATUS=([OpenCode]=0 [MCP]=0 [Ollama]=0 [Qdrant]=0 [Disk]=0 [embeddings]=0)
declare -a MSGS=()

emit() {
  local name="$1" ok="$2" msg="$3"
  STATUS["$name"]="$ok"
  if [[ "$ok" -eq 1 ]]; then
    MSGS+=("$(printf '  \033[32mOK\033[0m       %s: %s' "$name" "$msg")")
  else
    MSGS+=("$(printf '  \033[31mFAIL\033[0m     %s: %s' "$name" "$msg")")
  fi
}

# 1. OpenCode config
OC="${REPO_ROOT}/opencode.json"
if [[ -f "${OC}" ]] && python3 -c "import json; json.load(open('${OC}'))"; then
  if grep -qE '/home/[a-zA-Z0-9_]+/' "${OC}" 2>/dev/null; then
    emit OpenCode 0 "rutas absolutas residuales; corre make bootstrap"
  else
    emit OpenCode 1 "opencode.json valido y portable"
  fi
else
  emit OpenCode 0 "opencode.json ausente o invalido"
fi

# 2. MCP servers: enviar 'initialize' JSON-RPC por stdin
mcp_probe() {
  local script="$1"
  echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}' \
    | timeout 10 python3 "${REPO_ROOT}/${script}" 2>/dev/null \
    | grep -q '"serverInfo"'
}
MCP_OK=1
mcp_probe "local-memory/server.py"     || MCP_OK=0
mcp_probe "code-index/server.py"       || MCP_OK=0
mcp_probe "judgment-memory/server.py"  || MCP_OK=0
mcp_probe "kernel/mcp_server.py"       || MCP_OK=0
emit MCP "${MCP_OK}" \
  "$([[ $MCP_OK -eq 1 ]] && echo 'los 4 servers arrancan' || echo 'al menos un server MCP fallo al initialize')"

# 3. Ollama
if curl -sf -m 5 "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
  TAGS="$(curl -sf -m 5 "${OLLAMA_URL}/api/tags")"
  HAS_ALL="$(EMBED_MODEL="${EMBED_MODEL}" CODE_EMBED_MODEL="${CODE_EMBED_MODEL}" \
             python3 - <<PY
import json, os
tags = json.loads('''${TAGS}''').get('models', [])
need = [os.environ['EMBED_MODEL'], os.environ['CODE_EMBED_MODEL']]
print('yes' if all(any(m.get('name','').startswith(n) for m in tags) for n in need) else 'no')
PY
  )"
  if [[ "${HAS_ALL}" == "yes" ]]; then
    emit Ollama 1 "tags OK y modelos ${EMBED_MODEL}, ${CODE_EMBED_MODEL} presentes"
  else
    emit Ollama 0 "tags OK pero falta alguno de ${EMBED_MODEL} / ${CODE_EMBED_MODEL}"
  fi
else
  emit Ollama 0 "no responde en ${OLLAMA_URL}"
fi

# 4. Qdrant
if curl -sf -m 5 "${QDRANT_URL}/readyz" >/dev/null 2>&1 \
   && curl -sf -m 5 "${QDRANT_URL}/collections" >/dev/null 2>&1; then
  emit Qdrant 1 "/readyz 200 + /collections OK"
else
  emit Qdrant 0 "no responde en ${QDRANT_URL}"
fi

# 5. Disk: directorios locales existen y son escribibles
DISK_OK=1
DISK_MSG="todos los directorios .tonymem/ son escribibles"
# Usar TONY_REPO_ROOT (igual que PWD en OpenCode) para consistencia
for d in "${REPO_ROOT}/.tonymem" \
         "${REPO_ROOT}/code-index/.codeindex"; do
  if [[ ! -d "$d" ]]; then
    if ! mkdir -p "$d" 2>/dev/null; then
      DISK_OK=0; DISK_MSG="no pude crear $d"; break
    fi
  fi
  if [[ ! -w "$d" ]]; then
    DISK_OK=0; DISK_MSG="$d no es escribible"; break
  fi
done
emit Disk "${DISK_OK}" "${DISK_MSG}"

# 6. embeddings: subshell reusando judgment_qdrant.verify.ts (sin duplicar logica)
EMB_OK=1
EMB_MSG="judgment_qdrant.verify.ts paso"
if [[ "${STATUS[Ollama]}" -eq 1 && "${STATUS[Qdrant]}" -eq 1 ]]; then
  if ! command -v bun >/dev/null 2>&1; then
    EMB_OK=0; EMB_MSG="bun no instalado - no puedo correr judgment_qdrant.verify.ts"
  elif ! (cd "${REPO_ROOT}" \
           && timeout 90 bun run tests/judgment_qdrant.verify.ts) >/tmp/verify.log 2>&1; then
    EMB_OK=0; EMB_MSG="judgment_qdrant.verify.ts fallo - tail: $(tail -3 /tmp/verify.log | tr '\n' ' ')"
  fi
else
  EMB_OK=0; EMB_MSG="skipped - Ollama o Qdrant estan abajo"
fi
emit embeddings "${EMB_OK}" "${EMB_MSG}"

# Output
printf "\n\033[1m=== tony-ai health ===\033[0m\n"
for m in "${MSGS[@]}"; do echo -e "$m"; done
echo ""

CRIT=0
for k in OpenCode MCP Ollama Qdrant Disk embeddings; do
  [[ "${STATUS[$k]}" -eq 0 ]] && CRIT=1
done
exit "${CRIT}"