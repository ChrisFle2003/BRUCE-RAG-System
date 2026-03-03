#!/usr/bin/env bash
# Startet einen llama.cpp Server für ein Calc-Model
# Verwendung: ./run_calc_server.sh <PORT> <GPU_DEVICE> <MODEL_PATH>
#
# Beispiele:
#   ./run_calc_server.sh 8001 0 /models/granite4-350m-h-q8_0.gguf   # RTX 3080
#   ./run_calc_server.sh 8002 0 /models/granite4-350m-h-q8_0.gguf   # RTX 3080
#   ./run_calc_server.sh 8003 1 /models/granite4-350m-h-q8_0.gguf   # RTX 4060 Ti

set -euo pipefail

PORT="${1:-8001}"
GPU_ID="${2:-0}"
MODEL="${3:-/models/granite4-350m-h-q8_0.gguf}"
LLAMA_SERVER="${HOME}/llama.cpp/build/bin/llama-server"

# Granite 350M Q8 Speicher-Budget:
#   Weights: ~370MB
#   KV-Cache (ctx=2048): ~100MB
#   Total: ~470MB pro Instanz
#   RTX 3080 (10GB): Platz für ~15 Instanzen theoretisch!
#   Praktisch sinnvoll: 4-5 Instanzen pro GPU (Wärme, Parallelität)

CUDA_VISIBLE_DEVICES="${GPU_ID}" \
"${LLAMA_SERVER}" \
    --model "${MODEL}" \
    --port "${PORT}" \
    --host 0.0.0.0 \
    --ctx-size 2048 \
    --n-gpu-layers 999 \
    --threads 4 \
    --parallel 4 \
    --batch-size 512 \
    --ubatch-size 512 \
    --flash-attn on \
    --no-mmap \
    --seed 42 \
    --log-disable \
    2>&1 | sed "s/^/[calc-${PORT}] /"
