@echo off
REM ADAS Backend - Windows Server Startup
REM Production-grade with auto-install

echo ==========================================
echo ADAS Backend - Starting...
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo Please install Python 3.10+ from https://www.python.org
    pause
    exit /b 1
)

echo [OK] Python found
python --version
echo.

REM Create directories
if not exist logs mkdir logs
if not exist uploads\videos mkdir uploads\videos
if not exist ai_models\weights mkdir ai_models\weights
echo [OK] Directories created
echo.

REM Check if dependencies installed
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing dependencies...
    echo This may take a few minutes on first run...
    echo.
    
    REM Upgrade pip first
    python -m pip install --upgrade pip
    
    REM Install from Windows-specific requirements
    if exist requirements_windows.txt (
        echo Installing from requirements_windows.txt...
        pip install -r requirements_windows.txt
    ) else (
        echo Installing from requirements.txt...
        pip install fastapi uvicorn pydantic==2.9.2 sqlalchemy python-multipart python-dotenv httpx aiofiles
    )
    
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Failed to install dependencies
        echo.
        echo Try manually:
        echo   pip install -r requirements_windows.txt
        echo.
        pause
        exit /b 1
    )
    
    echo.
    echo [OK] Dependencies installed
) else (
    echo [OK] Dependencies already installed
)

echo.
echo ==========================================
echo Starting FastAPI server...
echo ==========================================
echo Server: http://localhost:52000
echo Docs:   http://localhost:52000/docs
echo Health: http://localhost:52000/health
echo.
echo Press Ctrl+C to stop
echo ==========================================
echo.

REM Start server
python main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server failed to start
    echo Check logs/adas_backend_*.log for details
    echo.
    pause
)
