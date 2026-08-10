#!/usr/bin/env bash
# scripts/calibrate-ctx.sh
#
# Fija el num_ctx REAL de cada modelo de Ollama via Modelfile (fuente de
# verdad del lado de Ollama), para que coincida con el limit.context que
# opencode.json declara y que DCP usa para calcular sus porcentajes.
#
# Regla: num_ctx de Ollama >= modelMaxLimits (75%/70%) del limit.context.
# Si la memoria no alcanza, baje el num_ctx a la mitad en AMBOS lados
# (este script y opencode.json) y verifique con: ollama ps / nvidia-smi.
#
# Uso: ./scripts/calibrate-ctx.sh   (idempotente, se puede re-ejecutar)

set -euo pipefail

# Modelo -> num_ctx. Debe coincidir con provider.ollama.models en opencode.json.
declare -A CONTEXTS=(
  [qwen3-coder:30b]="32768"
  [omnicoder:9b]="16384"
  [deepseek-r1:14b]="16384"
  [ornith:9b]="16384"
)

MODELFILES_DIR="${TONY_MODELFILES_DIR:-$HOME/.tony-ai/modelfiles}"
mkdir -p "$MODELFILES_DIR"

if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: ollama no esta en el PATH. Instalalo desde https://ollama.com/download"
  exit 1
fi

for model in "${!CONTEXTS[@]}"; do
  ctx="${CONTEXTS[$model]}"
  modelfile="$MODELFILES_DIR/Modelfile.${model//:/-}"
  printf 'FROM %s\nPARAMETER num_ctx %s\n' "$model" "$ctx" > "$modelfile"
  echo "==> Aplicando num_ctx=${ctx} a ${model}"
  ollama create "$model" -f "$modelfile"
done

echo
echo "Verificacion (esperado: 32768 para qwen3-coder:30b, 16384 para el resto):"
for model in "${!CONTEXTS[@]}"; do
  echo "--- ${model} ---"
  ollama show "$model" | grep -i "context length" || ollama show "$model"
done
