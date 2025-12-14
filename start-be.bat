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

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo.
    echo Please install Python 3.10+ from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
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

REM Create virtual environment if it doesn't exist
if not exist venv (
    echo [Step 3/7] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo   [ERROR] Failed to create virtual environment
        echo   Trying to clean up and retry...
        rmdir /s /q venv 2>nul
        timeout /t 2 /nobreak >nul
        python -m venv venv
        if errorlevel 1 (
            echo   [FATAL] Cannot create virtual environment
            pause
            exit /b 1
        )
    )
    echo   - Virtual environment created successfully
) else (
    echo [Step 3/7] Virtual environment already exists
)
echo.

REM Activate virtual environment
echo [Step 4/7] Activating virtual environment...
call venv\Scripts\activate
if e ================================================================================
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
set LAST_START_TIME=0

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

REM Get current time (seconds since midnight)
for /f "tokens=1-3 delims=:., " %%a in ("%time%") do (
    set /a CURRENT_TIME=%%a*3600+%%b*60+%%c
)

REM Check if restarting too fast (less than 10 seconds)
set /a TIME_DIFF=CURRENT_TIME-LAST_START_TIME
if %TIME_DIFF% LSS 10 (
    set /a FAST_RESTART_COUNT+=1
    if !FAST_RESTART_COUNT! GEQ %MAX_FAST_RESTARTS% (
        echo.
        echo [WARNING] Server is restarting too frequently!
        echo Waiting 30 seconds before next attempt...
        timeout /t 30 /nobreak
        set FAST_RESTART_COUNT=0
    )
) else (
    set FAST_RESTART_COUNT=0
)
set LAST_START_TIME=%CURRENT_TIME%

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
    echo Server stopped gracefully.
    echo Restarting in 5 seconds...
    timeout /t 5 /nobreak
) else (
    echo [ERROR] Server crashed with error code %EXIT_CODE%
    echo Auto-restarting in 10 seconds...
    echo Check logs/backend.log for details
    timeout /t 10 /nobreak
)

REM Kill any lingering processes on port 52000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :52000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

REM Restart the server
goto START_LOOP

REM This line should never be reached    echo   Retrying PyTorch installation...
    pip install --no-cache-dir --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cpu --disable-pip-version-check
)
echo   - PyTorch installed

REM Install other dependencies
echo   [2/3] Installing FastAPI, OpenCV, and other packages...
pip install --no-cache-dir -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo   Some packages failed, retrying individually...
    pip install fastapi uvicorn[standard] opencv-python numpy sqlalchemy pydantic --disable-pip-version-check
)
echo   - Core packages installed

REM Install Ultralytics YOLO
echo   [3/3] Installing Ultralytics YOLO...
pip install --no-cache-dir ultralytics==8.3.23 --no-deps --quiet --disable-pip-version-check
if errorlevel 1 (
    pip install ultralytics==8.3.23 --no-deps --disable-pip-version-check
)
echo   - Ultralytics installed
echo.

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

