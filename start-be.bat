@echo off
REM One-click start for Windows (CPU build)
setlocal

REM Create venv if missing
if not exist venv (
    python -m venv venv
)

call venv\Scripts\activate

REM Upgrade pip/setuptools/wheel to avoid build issues
python -m pip install --upgrade pip setuptools wheel

REM Install Torch CPU wheels from official index (avoids DLL load errors)
pip install --no-cache-dir torch==2.3.1+cpu torchvision==0.18.1+cpu --extra-index-url https://download.pytorch.org/whl/cpu

REM Install remaining dependencies
pip install --no-cache-dir -r requirements.txt

REM Run server
python main.py

endlocal

