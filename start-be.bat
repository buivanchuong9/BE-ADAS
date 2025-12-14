@echo off
REM =============================================================================
REM ADAS Backend - Production Windows Server Startup Script
REM Professional FastAPI + AI Backend System
REM Version 5.0 - Production Mode
REM =============================================================================
setlocal EnableDelayedExpansion

REM Set UTF-8 encoding for proper character display
chcp 65001 >nul 2>&1

title ADAS Backend - Production Server

REM Create logs directory
if not exist logs mkdir logs
if not exist logs\alerts mkdir logs\alerts

REM Initialize variables
set PYTHON_OK=0
set PROJECT_OK=0
set VENV_OK=0
set DEPS_OK=0
set EXIT_CODE=0

REM ============================================================================
REM MAIN ENTRY POINT
REM ============================================================================
cls
echo.
echo ================================================================================
echo            ADAS BACKEND SYSTEM - PRODUCTION MODE
echo ================================================================================
echo  FastAPI + AI Models Backend
echo  Production-Ready Windows Server Edition
echo  Host: 0.0.0.0 ^| Port: 52000
echo ================================================================================
echo.

call :LOG INFO "Starting ADAS Backend initialization..."
echo.

REM ============================================================================
REM STEP 1: CHECK PYTHON INSTALLATION
REM ============================================================================
call :LOG INFO "Step 1/5: Checking Python installation..."

python --version >nul 2>&1
if errorlevel 1 (
    call :LOG ERROR "Python not found in system PATH"
    echo.
    echo  ❌ CRITICAL ERROR: Python is not installed or not accessible
    echo.
    echo  Required: Python 3.10 or higher
    echo  Download: https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During installation, check "Add Python to PATH"
    echo.
    set PYTHON_OK=0
    goto :ERROR_HALT
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VERSION=%%i
call :LOG INFO "Found Python %PY_VERSION%"

REM Check Python version >= 3.10
python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>nul
if errorlevel 1 (
    call :LOG ERROR "Python version too old: %PY_VERSION%"
    echo.
    echo  ❌ ERROR: Python version too old
    echo.
    echo  Required: Python 3.10 or higher
    echo  Current: %PY_VERSION%
    echo  Download: https://www.python.org/downloads/
    echo.
    set PYTHON_OK=0
    goto :ERROR_HALT
)

python -c "import sys; print('  → Python executable: ' + sys.executable)"
set PYTHON_OK=1
echo.

REM ============================================================================
REM STEP 2: VERIFY PROJECT STRUCTURE
REM ============================================================================
call :LOG INFO "Step 2/5: Verifying project structure..."

echo   → Current directory: %CD%

if not exist main.py (
    call :LOG ERROR "main.py not found in current directory"
    echo.
    echo  ❌ ERROR: main.py not found
    echo.
    echo  Current directory: %CD%
    echo  Required files: main.py, requirements.txt
    echo.
    echo  Please ensure start-be.bat is in the project root folder.
    echo.
    set PROJECT_OK=0
    goto :ERROR_HALT
)

if not exist requirements.txt (
    call :LOG ERROR "requirements.txt not found"
    echo.
    echo  ❌ ERROR: requirements.txt not found
    echo.
    echo  This file is required for dependency installation.
    echo  Please ensure you have the complete project files.
    echo.
    set PROJECT_OK=0
    goto :ERROR_HALT
)

echo   → main.py: Found
echo   → requirements.txt: Found
if exist config.py echo   → config.py: Found
if exist vision echo   → vision/: Found
if exist ai_models echo   → ai_models/: Found

call :LOG INFO "Project structure validated"
set PROJECT_OK=1
echo.

REM ============================================================================
REM STEP 3: VIRTUAL ENVIRONMENT SETUP
REM ============================================================================
call :LOG INFO "Step 3/5: Setting up virtual environment..."

if exist venv (
    call :LOG INFO "Virtual environment exists, activating..."
    goto :ACTIVATE_VENV
)

call :LOG INFO "Creating virtual environment..."
echo   → This may take 30-60 seconds...

python -m venv venv 2>nul
if errorlevel 1 (
    call :LOG ERROR "Failed to create virtual environment"
    echo.
    echo  ❌ ERROR: Cannot create virtual environment
    echo.
    echo  Possible causes:
    echo    - Insufficient disk space (need ~500MB free)
    echo    - Permission issues (try running as Administrator)
    echo    - Antivirus blocking (disable temporarily)
    echo.
    set VENV_OK=0
    goto :ERROR_HALT
)

call :LOG INFO "Virtual environment created successfully"

:ACTIVATE_VENV
if not exist venv\Scripts\activate.bat (
    call :LOG ERROR "Virtual environment corrupted (activate.bat missing)"
    echo.
    echo  ❌ ERROR: Virtual environment is corrupted
    echo.
    echo  Solution: Delete 'venv' folder and restart this script
    echo.
    set VENV_OK=0
    goto :ERROR_HALT
)

call venv\Scripts\activate 2>nul
if errorlevel 1 (
    call :LOG ERROR "Failed to activate virtual environment"
    echo.
    echo  ❌ ERROR: Cannot activate virtual environment
    echo.
    echo  Solution: Delete 'venv' folder and restart this script
    echo.
    set VENV_OK=0
    goto :ERROR_HALT
)

echo   → Virtual environment: Active
python -c "import sys; print('  → Python location: ' + sys.executable)"
call :LOG INFO "Virtual environment ready"
set VENV_OK=1
echo.

REM ============================================================================
REM STEP 4: INSTALL DEPENDENCIES
REM ============================================================================
call :LOG INFO "Step 4/5: Installing dependencies..."

echo   → Upgrading pip...
python -m pip install --upgrade pip --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (
    call :LOG WARN "Pip upgrade failed, continuing..."
)

echo   → Installing requirements.txt...
echo   → This may take 5-10 minutes on first run...
echo.

pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (
    call :LOG WARN "Silent install failed, retrying with output..."
    echo.
    
    pip install -r requirements.txt 2>&1
    if errorlevel 1 (
        call :LOG ERROR "Failed to install dependencies"
        echo.
        echo  ❌ ERROR: Dependency installation failed
        echo.
        echo  Try manually:
        echo    venv\Scripts\activate
        echo    pip install -r requirements.txt
        echo.
        set DEPS_OK=0
        goto :ERROR_HALT
    )
)

echo.
echo   → Verifying critical imports...
python -c "import fastapi, uvicorn, cv2, numpy" 2>nul
if errorlevel 1 (
    call :LOG ERROR "Import verification failed"
    echo.
    echo  ❌ ERROR: Some critical packages are not importable
    echo.
    echo  Missing: FastAPI, Uvicorn, OpenCV, or NumPy
    echo  Try: pip install fastapi uvicorn opencv-python numpy
    echo.
    set DEPS_OK=0
    goto :ERROR_HALT
)

call :LOG INFO "Dependencies installed successfully"
set DEPS_OK=1
echo.

REM ============================================================================
REM STEP 5: START SERVER
REM ============================================================================
echo ================================================================================
echo  🚀 ADAS API is LIVE at https://adas-api.aiotlab.edu.vn
echo  📚 Swagger Documentation: /docs
echo  🔧 Host: 0.0.0.0
echo  🔌 Port: 52000
echo ================================================================================
echo.

call :LOG INFO "Step 5/5: Starting FastAPI server..."
echo.
echo   Press Ctrl+C to stop the server
echo   Server output:
echo.
echo ================================================================================
echo.

python main.py
set EXIT_CODE=!errorlevel!

echo.
echo ================================================================================
if !EXIT_CODE! EQU 0 (
    call :LOG INFO "Server stopped gracefully"
    echo  ℹ️  SERVER STOPPED - Normal shutdown
) else (
    call :LOG ERROR "Server crashed with exit code !EXIT_CODE!"
    echo  ❌ SERVER CRASHED - Exit code: !EXIT_CODE!
)
echo ================================================================================
echo.

goto :SERVER_STOPPED

REM ============================================================================
REM ERROR HANDLER
REM ============================================================================
:ERROR_HALT
echo.
echo ================================================================================
echo  ❌ INITIALIZATION FAILED
echo ================================================================================
echo.
echo  Please resolve the errors above and restart this script.
echo.
echo  Window will remain open for review.
echo  Press any key to exit...
echo.
echo ================================================================================
echo.
pause >nul
goto :END

REM ============================================================================
REM SERVER STOPPED HANDLER
REM ============================================================================
:SERVER_STOPPED
echo.
echo  Window will remain open for review.
echo  Press any key to exit...
echo.
pause >nul
goto :END

REM ============================================================================
REM LOGGING FUNCTION
REM ============================================================================
:LOG
set LOG_LEVEL=%~1
set LOG_MSG=%~2
for /f "tokens=1-3 delims=:." %%a in ("%time: =0%") do (
    set TIMESTAMP=%%a:%%b:%%c
)
echo [!TIMESTAMP!] [%LOG_LEVEL%] %LOG_MSG%
goto :EOF

REM ============================================================================
REM SCRIPT END
REM ============================================================================
:END
endlocal

