@echo off
REM Windows Server - Dependency Installer
REM Safe installation without compilation

echo ==========================================
echo ADAS Backend - Windows Installation
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

echo [OK] Python version:
python --version
echo.

REM Upgrade pip
echo [1/3] Upgrading pip...
python -m pip install --upgrade pip
echo.

REM Install core dependencies
echo [2/3] Installing core dependencies...
pip install fastapi==0.115.0 uvicorn==0.32.0 pydantic==2.9.2 sqlalchemy==2.0.36 python-multipart python-dotenv httpx aiofiles

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Installation failed
    pause
    exit /b 1
)

echo.
echo [3/3] Creating directories...
if not exist logs mkdir logs
if not exist uploads\videos mkdir uploads\videos
if not exist ai_models\weights mkdir ai_models\weights

echo.
echo ==========================================
echo Installation Complete!
echo ==========================================
echo.
echo Next steps:
echo   1. Run: start_server.bat
echo   2. Test: http://localhost:52000/health
echo   3. Docs: http://localhost:52000/docs
echo.
echo Note: Video processing disabled (no OpenCV)
echo      API will work but video upload returns error
echo.
pause
