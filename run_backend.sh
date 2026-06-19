#!/bin/bash
# ==================================================================
#  EduMentor Voice - FastAPI Backend Launcher (Linux/macOS)
# ==================================================================

echo "[EduMentor] Starting FastAPI Backend..."
echo ""

cd backend || exit 1

if [ ! -d ".venv310" ]; then
    echo "[ERROR] Virtual environment .venv310 was not found."
    echo "Please make sure you have created .venv310 and installed requirements."
    echo ""
    exit 1
fi

echo "Activating virtual environment (.venv310)..."
source .venv310/bin/activate

echo "Launching FastAPI server..."
python -m uvicorn main:app --host 0.0.0.0 --port 8000
