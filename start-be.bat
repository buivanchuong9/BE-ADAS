@echo off
REM One-click start for Windows
setlocal

REM Create venv if missing
if not exist venv (
    python -m venv venv
)

call venv\Scripts\activate

REM Upgrade pip/setuptools/wheel to avoid build issues
python -m pip install --upgrade pip setuptools wheel

REM Install dependencies (no cache to avoid stale wheels)
pip install --no-cache-dir -r requirements.txt

REM Run server
python main.py

endlocal

