@echo off
REM ==================================================================
REM  EduMentor Voice - llama.cpp Server Launcher (Windows)
REM
REM  Run this FIRST, before starting the FastAPI backend.
REM  Requires llama-server.exe to be on your PATH or at the path below.
REM
REM  GPU offload: -ngl 9999 offloads all layers to GPU (NVIDIA).
REM  Reduce -ngl if you see CUDA out-of-memory errors.
REM
REM  KV cache / prompt caching flags:
REM  -c 4096          Context window — must hold system prompt + history + new turn.
REM                  4096 comfortably covers 2,700+ token requests for EduMentor:
REM                  system prompt (~850t) + history (~1500t) + response (~350t)
REM                  = ~2700t per turn, leaving ~1300t of headroom.
REM                  Keeping it at 4096 (vs 8192) reduces KV cache VRAM usage
REM                  per slot, leaving more headroom for model weights and
REM                  improving latency.
REM  --cache-reuse 256  Min token overlap required for llama.cpp to reuse a cached
REM                   prefix segment. Without this, only a full-prefix match reuses
REM                   the KV cache; 256 allows partial-prefix hits as history grows.
REM  --slots          Exposes /slots endpoint so you can verify cache hits via:
REM                     curl http://localhost:8080/slots
REM                   Check that n_past grows turn-over-turn (not resetting to ~0).
REM  -np 4            Four parallel KV slots — one per concurrent student session.
REM                   IMPORTANT: without -np > 1, every new connection competes for
REM                   the same single slot. A second student's request evicts the
REM                   first student's cached system prompt prefix, even though both
REM                   share the identical static system prompt. This is the most
REM                   common reason prompt caching silently fails in multi-user
REM                   deployments. Size -np to peak concurrent sessions, not total
REM                   user count (most students are idle between turns).
REM ==================================================================

set MODEL=backend\models\EduMentor-Qwen3-Q6_K.gguf

echo [EduMentor] Starting llama.cpp server...
echo Model: %MODEL%
echo Port:  8080
echo.

"C:\Users\savan\.docker\bin\inference\llama-server.exe" ^
  -m %MODEL% ^
  -c 4096 ^
  -ngl 28 ^
  --host 0.0.0.0 ^
  --port 8080 ^
  --temp 0.6 ^
  --top-p 0.9 ^
  --repeat-penalty 1.08 ^
  --cache-reuse 256 ^
  --slots ^
  -np 1

pause
