@echo off
REM Clean setup and run (CPU, Python 3.13+, Windows)
setlocal

REM Remove existing venv (optional clean)
if exist venv (
    rmdir /s /q venv
)

python -m venv venv
call venv\Scripts\activate

python -m pip install --upgrade pip setuptools wheel

REM Install torch/torchvision nightly CPU for Python 3.13
pip install --no-cache-dir --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cpu

REM Install remaining deps
pip install --no-cache-dir -r requirements.txt

REM Install ultralytics without pulling torch again
pip install --no-cache-dir ultralytics==8.3.23 --no-deps

REM Run server
python main.py

endlocal

