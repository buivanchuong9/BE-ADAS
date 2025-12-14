@echo off
REM =============================================================================
REM ADAS Backend - One-Click Start for Windows Server
REM Automatically installs dependencies and starts the server on port 52000
REM Compatible with Python 3.10+ (Python 3.13 recommended)
REM =============================================================================
setlocal

echo ================================================================================
echo  ADAS Backend - Starting...
echo ================================================================================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

echo [1/5] Checking Python version...
python --version

REM Create virtual environment if it doesn't exist
if not exist venv (
    echo [2/5] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
) else (
    echo [2/5] Virtual environment already exists
)

REM Activate virtual environment
echo [3/5] Activating virtual environment...
call venv\Scripts\activate
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)

REM Upgrade pip, setuptools, wheel
echo [4/5] Upgrading pip and installing dependencies...
python -m pip install --upgrade pip setuptools wheel --quiet

REM Install PyTorch CPU version for Python 3.13+ (nightly build)
echo     - Installing PyTorch (CPU version)...
pip install --no-cache-dir --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cpu --quiet

REM Install other dependencies
echo     - Installing FastAPI, OpenCV, and other packages...
pip install --no-cache-dir -r requirements.txt --quiet

REM Install Ultralytics (YOLO) without dependencies to avoid conflicts
echo     - Installing Ultralytics YOLO...
pip install --no-cache-dir ultralytics==8.3.23 --no-deps --quiet

echo.
echo ================================================================================
echo  Installation Complete!
echo ================================================================================
echo  Server Configuration:
echo    - Host: 0.0.0.0
echo    - Port: 52000
echo    - API Endpoint: /vision/frame
echo    - Health Check: /health
echo    - Documentation: http://localhost:52000/docs
echo ================================================================================
echo.
echo [5/5] Starting ADAS Backend...
echo.

REM Start the server
python main.py

REM If server stops, pause to see any errors
if errorlevel 1 (
    echo.
    echo [ERROR] Server stopped with error code %errorlevel%
    pause
)

endlocal

