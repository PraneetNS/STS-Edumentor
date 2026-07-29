@echo off
REM ==================================================================
REM  EduMentor Voice - llama.cpp Server Launcher (Windows)
REM
REM  Run this FIRST, before starting the FastAPI backend.
REM  Requires llama-server.exe to be on PATH or at the path below.
REM
REM  KEY SETTINGS:
REM  -c 4096   Total context window. With -np 1 (single slot), each
REM             request gets the full 4096 tokens — enough for:
REM               system prompt (~1600t) + history (~750t) + reply (~350t)
REM             = ~2700t per turn with ~1300t headroom.
REM
REM  -np 1     Single parallel slot. In llama.cpp the total context (-c)
REM             is divided equally across all slots. With -np 4 at c=4096
REM             each slot only gets 1024 tokens, causing HTTP 400 errors
REM             on any request >1024 tokens. -np 1 gives the full 4096
REM             to every request. Fine for a single-user dev setup.
REM
REM  -ngl 20   GPU layers. VRAM budget on RTX 3050 (3365 MB free):
REM               model weights @ ngl=20  ~2410 MB
REM               KV cache  1 slot x 4096  ~100 MB
REM               Whisper + Kokoro + VAD   ~400 MB
REM               total                   ~2910 MB  < 3365 MB free
REM
REM  --slots   Expose /slots endpoint for cache-hit verification.
REM ==================================================================

set MODEL=backend\models\EduMentor-Qwen3-Q6_K.gguf

REM Add Ollama lib dir + CUDA v12 DLLs to PATH so GPU support is loaded
set OLLAMA_LIB=C:\Users\savan\AppData\Local\Programs\Ollama\lib\ollama
set PATH=%OLLAMA_LIB%;%OLLAMA_LIB%\cuda_v12;%PATH%

echo [EduMentor] Starting llama.cpp server...
echo Model: %MODEL%
echo Port:  8080
echo.

"%OLLAMA_LIB%\llama-server.exe" ^
  -m %MODEL% ^
  -c 4096 ^
  -ngl 20 ^
  --cache-type-k q8_0 ^
  --cache-type-v q8_0 ^
  --flash-attn on ^
  -cb ^
  --mlock ^
  --host 0.0.0.0 ^
  --port 8080 ^
  --temp 0.6 ^
  --top-p 0.9 ^
  --repeat-penalty 1.08 ^
  --slots ^
  --metrics ^
  -np 1

pause
