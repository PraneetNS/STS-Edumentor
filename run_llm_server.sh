#!/usr/bin/env bash
# ==================================================================
#  EduMentor Voice - llama.cpp Server Launcher (Linux / macOS)
#
#  Run this FIRST, before starting the FastAPI backend.
#  Requires llama-server to be on your PATH.
#
#  GPU offload: -ngl 9999 offloads all layers to GPU.
#  Reduce -ngl if you get out-of-memory errors.
# ==================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_PATH="${SCRIPT_DIR}/backend/models/EduMentor-Qwen3-Q6_K.gguf"

if [ ! -f "${MODEL_PATH}" ]; then
  echo "ERROR: Model not found at ${MODEL_PATH}"
  echo "Place your EduMentor-Qwen3-Q6_K.gguf file in backend/models/ and retry."
  exit 1
fi

echo "[EduMentor] Starting llama.cpp server..."
echo "Model: ${MODEL_PATH}"
echo "Port:  8080"
echo ""

llama-server \
  -m "${MODEL_PATH}" \
  -c 4096 \
  -ngl 20 \
  --host 0.0.0.0 \
  --port 8080 \
  --temp 0.6 \
  --top-p 0.9 \
  --repeat-penalty 1.08 \
  --log-disable
