#!/usr/bin/env bash
#
# llamacpp-vram-tune.sh
# ---------------------------------------------------------
# Calcula --n-gpu-layers (modelos densos) o --n-cpu-moe
# (modelos MoE) según la VRAM libre real, y levanta el
# modelo con llama-cli para pruebas/calibración manual.
# Pensado para una GPU de 10GB en Debian server headless.
#
# Uso:
#   ./llamacpp-vram-tune.sh <alias-modelo> [prompt opcional]
#
# Ejemplos:
#   ./llamacpp-vram-tune.sh qwen3-coder-30b
#   ./llamacpp-vram-tune.sh deepseek-r1-14b "explicame este error"
#
# Qué hace:
#   1. Lee la VRAM libre real vía nvidia-smi
#   2. Busca el perfil del modelo (ruta, arquitectura, capas, MB/capa)
#   3. Si es denso: calcula --n-gpu-layers
#      Si es MoE:   calcula --n-cpu-moe (deja la atención en GPU siempre)
#   4. Levanta llama-cli con los flags calculados
#
# Nota: este script es para pruebas/calibración manuales por fuera
# de llama-swap. Tu servicio de producción sigue usando los valores
# fijos en config.yaml (ya calibrados a mano); usá esto si cambiás
# de GPU, sumás un modelo nuevo, o querés reverificar los números.
# ---------------------------------------------------------

set -euo pipefail

MODEL="${1:-}"
PROMPT="${2:-}"

if [[ -z "$MODEL" ]]; then
  echo "Uso: $0 <alias-modelo> [prompt]"
  echo "Modelos configurados: qwen3-coder-30b, deepseek-r1-14b, omnicoder-9b"
  exit 1
fi

LLAMA_CLI_BIN="${LLAMA_CLI_BIN:-${HOME}/llama.cpp/build/bin/llama-cli}"

# -----------------------------------------------------------------
# 1. Perfiles por modelo
#    - path:         ruta al GGUF
#    - arch:          dense | moe
#    - layers:        capas totales del modelo
#    - mb_per_layer:  dense -> VRAM/capa completa (atención + FFN).
#                     moe   -> VRAM/capa SOLO de los expertos
#                              (lo que --n-cpu-moe mueve a RAM).
#    - kv_quant:      1 = agregar --cache-type-k/v q8_0 (igual que
#                     ese modelo en config.yaml)
#    OJO: valores de referencia iniciales, hay que calibrarlos
#    (ver sección final "Cómo calibrar").
# -----------------------------------------------------------------
declare -A MODEL_PATH=(
  ["qwen3-coder-30b"]="/home/tony/.tony-ai/models/qwen3-coder-30B.q4_k_m.gguf"
  ["deepseek-r1-14b"]="/home/tony/.tony-ai/models/deepseek-r1-14b.q4_k_m.gguf"
  ["omnicoder-9b"]="/home/tony/.tony-ai/models/omnicoder-2-9b.q5_k_m.gguf"
)

declare -A MODEL_ARCH=(
  ["qwen3-coder-30b"]="moe"
  ["deepseek-r1-14b"]="dense"
  ["omnicoder-9b"]="dense"
)

declare -A TOTAL_LAYERS=(
  ["qwen3-coder-30b"]=48
  ["deepseek-r1-14b"]=48
  ["omnicoder-9b"]=36
)

declare -A MB_PER_LAYER=(
  ["qwen3-coder-30b"]=140   # solo expertos por capa (lo que mueve --n-cpu-moe)
  ["deepseek-r1-14b"]=310
  ["omnicoder-9b"]=190
)

declare -A KV_QUANT=(
  ["qwen3-coder-30b"]=0
  ["deepseek-r1-14b"]=1
  ["omnicoder-9b"]=0
)

# Margen de seguridad para KV cache + overhead del contexto (MB)
KV_CACHE_RESERVE_MB=1500

if [[ -z "${MODEL_PATH[$MODEL]+x}" ]]; then
  echo "⚠️  Modelo '$MODEL' no tiene perfil configurado."
  echo "    Agregalo a MODEL_PATH / MODEL_ARCH / TOTAL_LAYERS / MB_PER_LAYER."
  exit 1
fi

if [[ ! -f "${MODEL_PATH[$MODEL]}" ]]; then
  echo "❌ No se encontró el GGUF en ${MODEL_PATH[$MODEL]}"
  exit 1
fi

if ! command -v nvidia-smi &>/dev/null; then
  echo "❌ nvidia-smi no encontrado. ¿Están los drivers NVIDIA instalados?"
  exit 1
fi

# -----------------------------------------------------------------
# 2. VRAM libre real (MB) vía nvidia-smi
# -----------------------------------------------------------------
FREE_VRAM_MB=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -n1)
echo "🎮 VRAM libre detectada: ${FREE_VRAM_MB} MB"

USABLE_VRAM_MB=$(( FREE_VRAM_MB - KV_CACHE_RESERVE_MB ))
if (( USABLE_VRAM_MB < 0 )); then
  USABLE_VRAM_MB=0
fi

# -----------------------------------------------------------------
# 3. Calcular offload según arquitectura
# -----------------------------------------------------------------
ARCH=${MODEL_ARCH[$MODEL]}
LAYERS=${TOTAL_LAYERS[$MODEL]}
PER_LAYER=${MB_PER_LAYER[$MODEL]}

FLAGS=(-m "${MODEL_PATH[$MODEL]}" --flash-attn on)

if [[ "$ARCH" == "dense" ]]; then
  NUM_GPU_LAYERS=$(( USABLE_VRAM_MB / PER_LAYER ))
  (( NUM_GPU_LAYERS > LAYERS )) && NUM_GPU_LAYERS=$LAYERS
  (( NUM_GPU_LAYERS < 0 )) && NUM_GPU_LAYERS=0

  echo "📦 Modelo: $MODEL (denso)"
  echo "   Capas totales: $LAYERS | VRAM/capa estimada: ${PER_LAYER}MB"
  echo "   -> --n-gpu-layers calculado: $NUM_GPU_LAYERS / $LAYERS"

  if (( NUM_GPU_LAYERS == 0 )); then
    echo "⚠️  VRAM insuficiente incluso para 1 capa. El modelo correrá 100% en CPU/RAM."
  fi

  FLAGS+=(--n-gpu-layers "$NUM_GPU_LAYERS")
else
  # MoE: la atención se queda siempre en GPU (-ngl 99); lo que varía
  # con la VRAM disponible es cuántas capas de EXPERTOS entran en GPU.
  # --n-cpu-moe = cantidad de capas cuyos expertos se mandan a CPU.
  LAYERS_ON_GPU=$(( USABLE_VRAM_MB / PER_LAYER ))
  (( LAYERS_ON_GPU > LAYERS )) && LAYERS_ON_GPU=$LAYERS
  (( LAYERS_ON_GPU < 0 )) && LAYERS_ON_GPU=0
  N_CPU_MOE=$(( LAYERS - LAYERS_ON_GPU ))

  echo "📦 Modelo: $MODEL (MoE)"
  echo "   Capas totales: $LAYERS | VRAM/capa (expertos) estimada: ${PER_LAYER}MB"
  echo "   -> capas de expertos que entran en GPU: $LAYERS_ON_GPU / $LAYERS"
  echo "   -> --n-cpu-moe calculado: $N_CPU_MOE"

  FLAGS+=(--n-gpu-layers 99 --n-cpu-moe "$N_CPU_MOE")
fi

if [[ "${KV_QUANT[$MODEL]}" -eq 1 ]]; then
  FLAGS+=(--cache-type-k q8_0 --cache-type-v q8_0)
  echo "   -> KV cache cuantizada: q8_0"
fi

# -----------------------------------------------------------------
# 4. Levantar llama-cli con los flags calculados
# -----------------------------------------------------------------
echo ""
echo "🚀 Levantando $MODEL con: ${FLAGS[*]}"
echo ""

if [[ -n "$PROMPT" ]]; then
  "$LLAMA_CLI_BIN" "${FLAGS[@]}" -p "$PROMPT"
else
  "$LLAMA_CLI_BIN" "${FLAGS[@]}" -cnv
fi

# -----------------------------------------------------------------
# Cómo calibrar MB_PER_LAYER (recomendado antes de confiar en esto):
#
#   1. Corré el modelo forzando full offload (--n-gpu-layers 99 en
#      dense, o --n-cpu-moe 0 en MoE) y con `nvidia-smi -l 1` en otra
#      terminal mirá el pico de VRAM apenas carga el modelo, antes
#      de generar texto.
#   2. Dense:  VRAM_usada_MB / TOTAL_LAYERS = MB_PER_LAYER real
#      MoE:    VRAM_usada_MB_full_offload menos la VRAM que usa con
#              --n-cpu-moe al máximo, dividido las capas offloadeadas
#              = MB_PER_LAYER real de expertos
#   3. Reemplazá el valor en el array de arriba.
#
# Para confirmar cuántas capas (n_layer / block count) tiene el GGUF:
#   ${LLAMA_CLI_BIN} -m <modelo.gguf> --n-gpu-layers 0 2>&1 | grep -i "n_layer\|block count"
# -----------------------------------------------------------------
