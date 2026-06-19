@echo off
REM ==================================================================
REM  EduMentor Voice - FastAPI Backend Launcher (Windows)
REM
REM  Run this AFTER starting the llama.cpp server.
REM  It automatically activates the virtual environment (.venv310)
REM  and launches the FastAPI backend.
REM ==================================================================

echo [EduMentor] Starting FastAPI Backend...
echo.

cd backend

if not exist .venv310 (
    echo [ERROR] Virtual environment .venv310 was not found.
    echo Please make sure you are in the EduMentor-Voice/backend directory
    echo and have run:
    echo   python -m venv .venv310
    echo   .venv310\Scripts\activate
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo Activating virtual environment (.venv310)...
call .venv310\Scripts\activate

echo Launching FastAPI server...
python -m uvicorn main:app --host 0.0.0.0 --port 8000

pause
