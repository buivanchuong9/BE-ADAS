@echo off
REM One-click start for Windows (CPU, Python 3.13). Requires VC++ Redistributable.
setlocal

REM Create venv if missing
if not exist venv (
    python -m venv venv
)

call venv\Scripts\activate

REM Upgrade pip/setuptools/wheel
python -m pip install --upgrade pip setuptools wheel

REM Install torch/torchvision nightly CPU wheels for Python 3.13
pip install --no-cache-dir --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cpu

REM Install the remaining deps (no torch/torchvision/ultralytics inside requirements)
pip install --no-cache-dir -r requirements.txt

REM Install ultralytics pinned (no deps to avoid re-pulling torch)
pip install --no-cache-dir ultralytics==8.3.23 --no-deps

REM Run server
python main.py

endlocal

