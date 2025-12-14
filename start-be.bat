@echo off
REM =============================================================================
REM ADAS Backend - Production Auto-Start for Windows Server
REM One-click solution: Auto-install, Auto-fix, Auto-restart
REM Runs forever until manually stopped
REM =============================================================================
setlocal enabledelayedexpansion

title ADAS Backend Server

echo.
echo ================================================================================
echo           ADAS Backend - Production Auto-Start System
echo ================================================================================
echo  Features: Auto-install, Auto-restart, Port management, Health monitoring
echo ================================================================================
echo.
echo Starting in 2 seconds... (this window will stay open)
timeout /t 2 /nobreak >nul
echo.

REM Check if Python is installed
echo [Diagnostic] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ===============================================================================
    echo  [ERROR] PYTHON NOT FOUND!
    echo ===============================================================================
    echo.
    echo Python is not installed or not in PATH.
    echo.
    echo Solution:
    echo  1. Download Python 3.10+ from: https://www.python.org/downloads/
    echo  2. During installation, CHECK the box: "Add Python to PATH"
    echo  3. After installation, RESTART this script
    echo.
    echo ===============================================================================
    echo.
    pause
    exit /b 1
)

echo [Step 1/7] Python version detected:
python --version
echo.

REM Kill any existing process on port 52000
echo [Step 2/7] Checking port 52000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :52000 ^| findstr LISTENING') do (
    echo   - Killing process PID %%a on port 52000
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul
echo   - Port 52000 is now free
echo.

REM Create logs directory if not exists
if not exist logs mkdir logs

REM Verify main.py exists
if not exist main.py (
    echo.
    echo ===============================================================================
    echo  [ERROR] main.py not found!
    echo ===============================================================================
    echo.
    echo  Current directory: %CD%
    echo.
    echo  Solution:
    echo    - Make sure you're running start-be.bat from the project root folder
    echo    - The folder should contain: main.py, requirements.txt, etc.
    echo    - Do NOT move start-be.bat to another location
    echo.
    pause
    exit /b 1
)

REM Verify requirements.txt exists
if not exist requirements.txt (
    echo.
    echo ===============================================================================
    echo  [ERROR] requirements.txt not found!
    echo ===============================================================================
    echo.
    echo  Current directory: %CD%
    echo.
    echo  This file is required for installation.
    echo  Make sure you have the complete project files.
    echo.
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist venv (
    echo [Step 3/7] Creating virtual environment...
    echo   This may take 30-60 seconds, please wait...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo   [ERROR] Failed to create virtual environment!
        echo   Possible causes:
        echo     - Insufficient disk space (need ~500MB)
        echo     - Antivirus software blocking Python
        echo     - Corrupted Python installation
        echo.
        echo   Attempting cleanup and retry in 3 seconds...
        timeout /t 3 /nobreak
        rmdir /s /q venv 2>nul
        python -m venv venv
        if errorlevel 1 (
            echo.
            echo   [FATAL] Cannot create virtual environment after retry!
            echo   Please check the errors above and try again.
            echo.
            pause
            exit /b 1
        )
    )
    echo   - Virtual environment created successfully
) else (
    echo [Step 3/7] Virtual environment already exists (reusing)
)
echo.

REM Activate virtual environment
echo [Step 4/7] Activating virtual environment...
if not exist venv\Scripts\activate.bat (
    echo.
    echo   [ERROR] Virtual environment is corrupted!
    echo   File missing: venv\Scripts\activate.bat
    echo.
    echo   Deleting corrupted venv and recreating in 3 seconds...
    timeout /t 3 /nobreak
    rmdir /s /q venv 2>nul
    python -m venv venv
    if errorlevel 1 (
        echo   [FATAL] Cannot recreate virtual environment
        pause
        exit /b 1
    )
)

call venv\Scripts\activate
if errorlevel 1 (
    echo.
    echo   [ERROR] Failed to activate virtual environment!
    echo   This should rarely happen. Attempting to recreate...
    echo.
    timeout /t 3 /nobreak
    rmdir /s /q venv 2>nul
    python -m venv venv
    call venv\Scripts\activate
    if errorlevel 1 (
        echo   [FATAL] Activation failed even after recreation
        pause
        exit /b 1
    )
)
echo   - Virtual environment activated successfully
echo.

REM Upgrade pip
echo [Step 5/7] Upgrading pip and core packages...
python -m pip install --upgrade pip setuptools wheel --quiet --disable-pip-version-check
if errorlevel 1 (
    echo   [WARNING] Pip upgrade failed, continuing anyway...
)
echo   - Pip upgraded
echo.

REM Install dependencies
echo [Step 6/7] Installing dependencies (first-time: 5-10 minutes)...
echo   Progress: [1/3] PyTorch  [2/3] Packages  [3/3] YOLO
echo.

REM Install PyTorch
echo   [1/3] Installing PyTorch (CPU version) - Large download...
echo         This step alone may take 3-5 minutes
pip install --no-cache-dir --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cpu --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo   [WARNING] PyTorch installation failed, retrying with output...
    pip install --no-cache-dir --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cpu --disable-pip-version-check
    if errorlevel 1 (
        echo.
        echo   [ERROR] PyTorch installation failed!
        echo   Possible solutions:
        echo     - Check internet connection
        echo     - Run as Administrator
        echo     - Check disk space (need ~2GB free)
        echo     - Disable antivirus temporarily
        echo.
        pause
        exit /b 1
    )
)
echo   - PyTorch installed successfully
echo.

REM Install other packages
echo   [2/3] Installing FastAPI, OpenCV, and other packages...
pip install --no-cache-dir -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo   [WARNING] Some packages failed, retrying with output...
    pip install --no-cache-dir -r requirements.txt --disable-pip-version-check
    if errorlevel 1 (
        echo.
        echo   [WARNING] Bulk install failed, trying core packages individually...
        pip install fastapi uvicorn[standard] opencv-python numpy sqlalchemy pydantic --disable-pip-version-check
    )
)
echo   - Core packages installed successfully
echo.

REM Install Ultralytics
echo   [3/3] Installing Ultralytics YOLO...
pip install --no-cache-dir ultralytics==8.3.23 --no-deps --quiet --disable-pip-version-check
if errorlevel 1 (
    pip install ultralytics==8.3.23 --no-deps --disable-pip-version-check
)
echo   - Ultralytics installed successfully
echo.

echo ================================================================================
echo  Installation Complete!
echo ================================================================================
echo  Server Configuration:
echo    - Host: 0.0.0.0 (accessible from network)
echo    - Port: 52000
echo    - API: POST /vision/frame
echo    - Health: GET /health
echo    - Docs: http://localhost:52000/docs
echo.
echo  Auto-Features:
echo    - Auto-restart on crash (infinite loop)
echo    - Auto-kill port conflicts
echo    - Error logging to logs/backend.log
echo ================================================================================
echo.

REM Start infinite restart loop
set RESTART_COUNT=0
set MAX_FAST_RESTARTS=5

:START_LOOP
set /a RESTART_COUNT+=1

echo [Step 7/7] Starting ADAS Backend (attempt #%RESTART_COUNT%)...
echo   - Time: %date% %time%
echo   - Log: logs/backend.log
echo.
echo ================================================================================
echo  SERVER IS RUNNING - Press Ctrl+C to stop
echo ================================================================================
echo.

REM Check if restarting too frequently
if %RESTART_COUNT% GTR 1 (
    if %RESTART_COUNT% LEQ %MAX_FAST_RESTARTS% (
        echo   [INFO] Quick restart #%RESTART_COUNT% - monitoring for crash loop...
        echo.
    )
    if %RESTART_COUNT% EQU %MAX_FAST_RESTARTS% (
        echo.
        echo ========================================================================
        echo  [WARNING] Server has crashed %MAX_FAST_RESTARTS% times in a row!
        echo ========================================================================
        echo.
        echo  This indicates a serious problem. Possible causes:
        echo    - Missing dependencies (delete venv folder and restart)
        echo    - Corrupted model files in ai_models/weights/
        echo    - Port 52000 still in use by another program
        echo    - Python syntax error in main.py or imported modules
        echo    - Missing Python packages
        echo.
        echo  Actions taken:
        echo    - Waiting 30 seconds before next restart
        echo    - Check logs/backend.log for detailed error messages
        echo.
        echo  To fix:
        echo    1. Close this window
        echo    2. Delete the 'venv' folder
        echo    3. Run start-be.bat again for fresh installation
        echo.
        timeout /t 30 /nobreak
        set RESTART_COUNT=0
        echo  Retrying now...
        echo.
    )
)

REM Start the server
python main.py

REM Capture exit code
set EXIT_CODE=%errorlevel%

echo.
echo ================================================================================
echo  Server stopped with exit code: %EXIT_CODE%
echo  Time: %date% %time%
echo ================================================================================
echo.

if %EXIT_CODE% EQU 0 (
    echo Server stopped gracefully (normal shutdown).
    echo Restarting in 5 seconds...
    timeout /t 5 /nobreak
) else (
    echo [ERROR] Server crashed with error code %EXIT_CODE%
    echo Check logs/backend.log for details
    echo Auto-restarting in 10 seconds...
    timeout /t 10 /nobreak
)

REM Kill any lingering processes on port 52000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :52000 ^| findstr LISTENING') do (
    echo Cleaning up process PID %%a on port 52000...
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

REM Restart the loop
goto START_LOOP

REM This line should never be reached
endlocal

