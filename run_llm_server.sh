#!/usr/bin/env bash
# ==================================================================
#  EduMentor Voice - llama.cpp Server Launcher (Linux / macOS)
#
#  Run this FIRST, before starting the FastAPI backend.
#  Requires llama-server to be on your PATH.
#
#  GPU offload: -ngl 9999 offloads all layers to GPU.
#  Reduce -ngl if you get out-of-memory errors.
#
#  KV cache / prompt caching flags:
#  -c 16384         Context window — must hold system prompt + history + new turn.
#  --cache-reuse 256  Min token overlap for llama.cpp to reuse a cached prefix
#                   segment instead of requiring a full-prefix match.
#  --slots          Exposes /slots endpoint for cache verification:
#                     curl http://localhost:8080/slots
#                   Confirm n_past grows turn-over-turn (not resetting to ~0).
#  -np 4            Four parallel KV slots — one per concurrent student session.
#                   IMPORTANT: without -np > 1, every new connection competes for
#                   the same single slot. A second student's request evicts the
#                   first student's cached system prompt prefix, even though both
#                   share the identical static system prompt. This is the most
#                   common reason prompt caching silently fails in multi-user
#                   deployments. Size -np to peak concurrent sessions, not total
#                   user count (most students are idle between turns).
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
  -c 16384 \
  -ngl 20 \
  --host 0.0.0.0 \
  --port 8080 \
  --temp 0.6 \
  --top-p 0.9 \
  --repeat-penalty 1.08 \
  --cache-reuse 256 \
  --slots \
  -np 4 \
  --log-disable
