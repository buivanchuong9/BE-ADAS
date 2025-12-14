@echo off
REM =============================================================================
REM ADAS Backend - One-Click Startup (Complete Edition)
REM NO external dependencies - Everything auto-installs
REM =============================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title ADAS Backend Server

cls
echo ====================================================================
echo                   ADAS BACKEND - AUTO INSTALLER
echo ====================================================================
echo.

REM ============================================================================
REM STEP 1: CHECK PYTHON
REM ============================================================================
echo [1/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python not found!
    echo.
    echo Please install Python 3.10+ from: https://www.python.org
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo       Python %PY_VER% - OK
echo.

REM ============================================================================
REM STEP 2: CHECK PROJECT FILES
REM ============================================================================
echo [2/6] Checking project files...
if not exist main.py (
    echo [ERROR] main.py not found
    echo Please run this script from the project root directory
    pause
    exit /b 1
)
echo       main.py - OK
echo.

REM ============================================================================
REM STEP 3: CREATE VIRTUAL ENVIRONMENT
REM ============================================================================
echo [3/6] Setting up virtual environment...

if exist venv (
    echo       Virtual environment exists
) else (
    echo       Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo       Created successfully
)

REM Activate venv
call venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    echo Try deleting 'venv' folder and run again
    pause
    exit /b 1
)
echo       Activated
echo.

REM ============================================================================
REM STEP 4: UPGRADE PIP
REM ============================================================================
echo [4/6] Upgrading pip...
python -m pip install --upgrade pip --quiet --disable-pip-version-check 2>nul
echo       Done
echo.

REM ============================================================================
REM STEP 5: INSTALL DEPENDENCIES (AUTO-FIX)
REM ============================================================================
echo [5/6] Installing dependencies...
echo       This may take 5-10 minutes on first run...
echo.

REM Create required directories first
if not exist logs mkdir logs >nul 2>&1
if not exist logs\alerts mkdir logs\alerts >nul 2>&1
if not exist uploads mkdir uploads >nul 2>&1
if not exist uploads\videos mkdir uploads\videos >nul 2>&1
if not exist ai_models mkdir ai_models >nul 2>&1
if not exist ai_models\weights mkdir ai_models\weights >nul 2>&1
if not exist dataset mkdir dataset >nul 2>&1
if not exist dataset\raw mkdir dataset\raw >nul 2>&1
if not exist dataset\labels mkdir dataset\labels >nul 2>&1

REM Try installing from requirements.txt
echo       Installing from requirements.txt...
pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (
    echo       requirements.txt failed, installing manually...
    echo.
    
    REM Install core packages one by one
    echo       [5.1] Core framework...
    pip install fastapi==0.115.0 --quiet --disable-pip-version-check 2>nul
    pip install uvicorn==0.32.0 --quiet --disable-pip-version-check 2>nul
    pip install pydantic==2.9.2 --quiet --disable-pip-version-check 2>nul
    pip install pydantic-settings==2.6.1 --quiet --disable-pip-version-check 2>nul
    
    echo       [5.2] Database...
    pip install sqlalchemy==2.0.36 --quiet --disable-pip-version-check 2>nul
    
    echo       [5.3] Video processing (REQUIRED)...
    pip install opencv-python-headless==4.10.0.84 --quiet --disable-pip-version-check 2>nul
    if errorlevel 1 (
        echo              Trying without version...
        pip install opencv-python-headless --quiet --disable-pip-version-check 2>nul
    )
    
    pip install numpy==1.26.4 --quiet --disable-pip-version-check 2>nul
    if errorlevel 1 (
        echo              Trying without version...
        pip install numpy --quiet --disable-pip-version-check 2>nul
    )
    
    echo       [5.4] Utilities...
    pip install python-multipart --quiet --disable-pip-version-check 2>nul
    pip install python-dotenv --quiet --disable-pip-version-check 2>nul
    pip install httpx --quiet --disable-pip-version-check 2>nul
    pip install aiofiles --quiet --disable-pip-version-check 2>nul
    pip install pillow --quiet --disable-pip-version-check 2>nul
    
    echo.
    echo       Manual installation complete
)

REM Verify critical packages
echo.
echo       Verifying critical packages...
python -c "import fastapi" 2>nul || (echo [WARN] FastAPI missing & pip install fastapi --quiet)
python -c "import uvicorn" 2>nul || (echo [WARN] Uvicorn missing & pip install uvicorn --quiet)
python -c "import sqlalchemy" 2>nul || (echo [WARN] SQLAlchemy missing & pip install sqlalchemy --quiet)
python -c "import pydantic" 2>nul || (echo [WARN] Pydantic missing & pip install pydantic --quiet)

REM Check OpenCV - CRITICAL for video processing
python -c "import cv2" 2>nul
if errorlevel 1 (
    echo.
    echo       [CRITICAL] OpenCV missing - Installing now...
    pip install opencv-python-headless numpy
    python -c "import cv2" 2>nul
    if errorlevel 1 (
        echo       [ERROR] OpenCV installation failed
        echo       Video processing will NOT work without OpenCV
        echo.
        echo       Try manually: pip install opencv-python-headless
        echo.
        pause
    )
)

python -c "import numpy" 2>nul
if errorlevel 1 (
    echo       [CRITICAL] NumPy missing - Installing now...
    pip install numpy
)

echo       All packages ready
echo.

REM ============================================================================
REM STEP 6: START SERVER
REM ============================================================================
echo [6/6] Starting server...
echo.
echo ====================================================================
echo                      SERVER STARTING
echo ====================================================================
echo.
echo   Public API:  https://adas-api.aiotlab.edu.vn
echo   Local:       http://localhost:52000
echo   API Docs:    http://localhost:52000/docs
echo   Health:      http://localhost:52000/health
echo.
echo   Frontend can call: https://adas-api.aiotlab.edu.vn/[endpoint]
echo.
echo   Press Ctrl+C to stop server
echo.
echo ====================================================================
echo.

REM Verify syntax before starting
echo Verifying Python code...
python -m py_compile main.py 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Python syntax error detected!
    echo.
    python -m py_compile main.py
    echo.
    echo Please fix the errors above before starting
    pause
    exit /b 1
)
echo Code syntax OK
echo.

REM Check if port is already in use
netstat -ano | findstr ":52000" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo [WARNING] Port 52000 is already in use!
    echo.
    echo Existing process on port 52000:
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :52000 ^| findstr LISTENING') do (
        echo   PID: %%a
        tasklist /FI "PID eq %%a" | findstr /V "Image Name"
    )
    echo.
    choice /C YN /N /M "Kill existing process and continue? (Y/N): "
    if errorlevel 2 (
        echo.
        echo Startup cancelled by user
        pause
        exit /b 0
    )
    echo.
    echo Killing process on port 52000...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :52000 ^| findstr LISTENING') do (
        taskkill /F /PID %%a >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)

REM Start Python server (this blocks until server stops)
echo Starting Python server...
echo.
python main.py
set EXIT_CODE=%errorlevel%

echo.
echo ====================================================================
echo                      SERVER STOPPED
echo ====================================================================
echo.

if %EXIT_CODE% EQU 0 (
    echo [OK] Server stopped normally (user requested)
    echo.
) else (
    echo [ERROR] Server crashed with exit code: %EXIT_CODE%
    echo.
    echo Troubleshooting:
    echo   1. Check logs folder for detailed error messages
    echo   2. Verify all dependencies: pip list
    echo   3. Test imports: python -c "import fastapi, uvicorn, cv2"
    echo   4. Check port 52000: netstat -ano ^| findstr :52000
    echo.
    echo Recent log file:
    if exist logs (
        for /f %%f in ('dir /b /od logs\adas_backend_*.log 2^>nul') do set LASTLOG=%%f
        if defined LASTLOG (
            echo   logs\!LASTLOG!
            echo.
            echo Last 10 lines:
            powershell -Command "Get-Content logs\!LASTLOG! -Tail 10"
        )
    )
    echo.
)

pause

