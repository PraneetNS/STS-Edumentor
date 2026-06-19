@echo off
REM ==================================================================
REM  EduMentor Voice - llama.cpp Server Launcher (Windows)
REM
REM  Run this FIRST, before starting the FastAPI backend.
REM  Requires llama-server.exe to be on your PATH or at the path below.
REM
REM  GPU offload: -ngl 9999 offloads all layers to GPU (NVIDIA).
REM  Reduce -ngl if you see CUDA out-of-memory errors.
REM ==================================================================

set MODEL=backend\models\edumentor-Q6_K.gguf

echo [EduMentor] Starting llama.cpp server...
echo Model: %MODEL%
echo Port:  8080
echo.

"C:\Users\savan\.docker\bin\inference\llama-server.exe" ^
  -m %MODEL% ^
  -c 16384 ^
  -ngl 9999 ^
  --host 0.0.0.0 ^
  --port 8080 ^
  --temp 0.6 ^
  --top-p 0.9 ^
  --repeat-penalty 1.08

pause
