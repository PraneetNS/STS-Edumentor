@echo off
echo ============================================================
echo   EduMentor Voice -- Stopping All Running Servers
echo ============================================================
echo.

:: Kill processes on port 8000 (Backend API Server)
echo [1/4] Stopping Backend API Server on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo Killing process PID %%a on port 8000
    taskkill /F /PID %%a >nul 2>&1
)

:: Kill processes on port 8080 (LLM llama-server)
echo [2/4] Stopping LLM Server on port 8080...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8080 ^| findstr LISTENING') do (
    echo Killing process PID %%a on port 8080
    taskkill /F /PID %%a >nul 2>&1
)

:: Kill processes on port 5173 (Vite Frontend Server)
echo [3/4] Stopping Frontend Server on port 5173...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING') do (
    echo Killing process PID %%a on port 5173
    taskkill /F /PID %%a >nul 2>&1
)

:: Kill Cloudflare tunnels
echo [4/4] Stopping Cloudflare tunnels (cloudflared)...
taskkill /F /IM cloudflared.exe >nul 2>&1
taskkill /F /IM cloudflared >nul 2>&1

echo.
echo ============================================================
echo   All servers and tunnels stopped successfully!
echo ============================================================
echo.
pause
