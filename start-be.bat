@echo off
REM =============================================================================
REM ADAS Backend - Professional Production Server
REM FastAPI + AI Models System
REM Version 6.0 - Enterprise Edition
REM =============================================================================
setlocal EnableDelayedExpansion

chcp 65001 >nul 2>&1
title ADAS Backend - Production Server

REM ============================================================================
REM CONFIGURATION
REM ============================================================================
set SERVER_HOST=0.0.0.0
set SERVER_PORT=52000
set API_URL=https://adas-api.aiotlab.edu.vn
set MAX_RETRY_ATTEMPTS=3
set RETRY_DELAY=5

REM Create directories
if not exist logs mkdir logs >nul 2>&1
if not exist logs\alerts mkdir logs\alerts >nul 2>&1

REM Initialize status flags
set PYTHON_OK=0
set PROJECT_OK=0
set VENV_OK=0
set DEPS_OK=0
set SERVER_RUNNING=0

REM ============================================================================
REM MAIN ENTRY POINT
REM ============================================================================
cls
call :PRINT_BANNER
echo.

call :LOG INFO "Initializing ADAS Backend System..."
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
echo.
call :PRINT_SERVER_INFO
echo.

call :LOG INFO "Step 5/5: Starting FastAPI server..."
echo.

:SERVER_START
set SERVER_RUNNING=1
call :LOG INFO "Launching Python main.py..."
echo.
echo ┌────────────────────────────────────────────────────────────────────────────┐
echo │                        SERVER OUTPUT                                       │
echo └────────────────────────────────────────────────────────────────────────────┘
echo.

python main.py
set EXIT_CODE=!errorlevel!
set SERVER_RUNNING=0

echo.
echo ┌────────────────────────────────────────────────────────────────────────────┐
echo │                        SERVER STOPPED                                      │
echo └────────────────────────────────────────────────────────────────────────────┘
echo.

if !EXIT_CODE! EQU 0 (
    call :LOG INFO "Server stopped gracefully (Exit code: 0)"
    echo  ✅ Normal shutdown - User requested stop
    echo.
    goto :GRACEFUL_STOP
) else (
    call :LOG ERROR "Server crashed with exit code !EXIT_CODE!"
    call :HANDLE_CRASH !EXIT_CODE!
    goto :END
)

REM ============================================================================
REM ERROR HANDLERS
REM ============================================================================
:ERROR_HALT
echo.
echo ╔════════════════════════════════════════════════════════════════════════════╗
echo ║                        ❌ INITIALIZATION FAILED                            ║
echo ╚════════════════════════════════════════════════════════════════════════════╝
echo.
echo  ⚠️  Please resolve the errors above and restart this script.
echo.
echo  💡 Common solutions:
echo     1. Ensure Python 3.10+ is installed
echo     2. Check internet connection for dependency downloads
echo     3. Run as Administrator if permission errors occur
echo     4. Verify project files exist (main.py, requirements.txt)
echo.
echo ────────────────────────────────────────────────────────────────────────────
echo  Press any key to exit...
echo ────────────────────────────────────────────────────────────────────────────
pause >nul
goto :END

:GRACEFUL_STOP
echo  ℹ️  Server has been stopped normally.
echo.
echo  To restart the server, simply run this script again.
echo.
echo ────────────────────────────────────────────────────────────────────────────
echo  Press any key to exit...
echo ────────────────────────────────────────────────────────────────────────────
pause >nul
goto :END

:HANDLE_CRASH
set CRASH_EXIT_CODE=%~1
echo.
echo ╔════════════════════════════════════════════════════════════════════════════╗
echo ║                           ❌ SERVER CRASHED                                ║
echo ╚════════════════════════════════════════════════════════════════════════════╝
echo.
echo  Exit Code: !CRASH_EXIT_CODE!
echo  Time: %date% %time%
echo.

REM Diagnose common errors
if !CRASH_EXIT_CODE! EQU 1 (
    echo  🔍 Diagnosis: Python execution error
    echo.
    echo  Common causes:
    echo     • Syntax error in Python code (IndentationError, SyntaxError)
    echo     • Missing import or module not found
    echo     • Runtime exception in application code
    echo.
    echo  💡 Solutions:
    echo     1. Check the error message above
    echo     2. Fix Python syntax errors in main.py or imported modules
    echo     3. Verify all required packages are installed
    echo     4. Run: python -m py_compile main.py
    echo.
)

if !CRASH_EXIT_CODE! EQU 3 (
    echo  🔍 Diagnosis: Port conflict
    echo.
    echo  💡 Solution:
    echo     Port %SERVER_PORT% may be in use by another process
    echo     Run: netstat -ano ^| findstr :%SERVER_PORT%
    echo.
)

echo ────────────────────────────────────────────────────────────────────────────
echo  Options:
echo    [R] Retry now
echo    [Q] Quit
echo ────────────────────────────────────────────────────────────────────────────
echo.
choice /C RQ /N /M "Select option (R/Q): "
set USER_CHOICE=!errorlevel!

if !USER_CHOICE! EQU 1 (
    echo.
    call :LOG INFO "User requested retry..."
    echo  🔄 Restarting server...
    echo.
    timeout /t 2 /nobreak >nul
    goto :SERVER_START
) else (
    echo.
    call :LOG INFO "User chose to exit"
    goto :END
)

REM ============================================================================
REM UTILITY FUNCTIONS
REM ============================================================================
:PRINT_BANNER
echo ╔════════════════════════════════════════════════════════════════════════════╗
echo ║                                                                            ║
echo ║                   ADAS BACKEND SYSTEM - PRODUCTION MODE                   ║
echo ║                                                                            ║
echo ║                    FastAPI + AI Models Backend                            ║
echo ║               Production-Ready Windows Server Edition                     ║
echo ║                                                                            ║
echo ╚════════════════════════════════════════════════════════════════════════════╝
goto :EOF

:PRINT_SERVER_INFO
echo ╔════════════════════════════════════════════════════════════════════════════╗
echo ║                      🚀 SERVER CONFIGURATION                               ║
echo ╚════════════════════════════════════════════════════════════════════════════╝
echo.
echo   🌐 Public URL:  %API_URL%
echo   📚 API Docs:    %API_URL%/docs
echo   🔧 Host:        %SERVER_HOST%
echo   🔌 Port:        %SERVER_PORT%
echo   ❤️  Health:      http://localhost:%SERVER_PORT%/health
echo.
echo ╔════════════════════════════════════════════════════════════════════════════╗
echo ║                      Press Ctrl+C to stop the server                      ║
echo ╚════════════════════════════════════════════════════════════════════════════╝
goto :EOF

:LOG
set LOG_LEVEL=%~1
set LOG_MSG=%~2
for /f "tokens=1-3 delims=:." %%a in ("%time: =0%") do set TIMESTAMP=%%a:%%b:%%c

if "%LOG_LEVEL%"=="INFO" (
    echo [!TIMESTAMP!] [ℹ️  INFO] %LOG_MSG%
) else if "%LOG_LEVEL%"=="ERROR" (
    echo [!TIMESTAMP!] [❌ ERROR] %LOG_MSG%
) else if "%LOG_LEVEL%"=="WARN" (
    echo [!TIMESTAMP!] [⚠️  WARN] %LOG_MSG%
) else (
    echo [!TIMESTAMP!] [%LOG_LEVEL%] %LOG_MSG%
)
goto :EOF

REM ============================================================================
REM SCRIPT END
REM ============================================================================
:END
echo.
echo ════════════════════════════════════════════════════════════════════════════
echo  ADAS Backend System - Session ended
echo  Thank you for using ADAS Backend!
echo ════════════════════════════════════════════════════════════════════════════
echo.
endlocal

