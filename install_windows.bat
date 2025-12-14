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
echo [2/4] Installing core dependencies...
pip install fastapi==0.115.0 uvicorn==0.32.0 pydantic==2.9.2 sqlalchemy==2.0.36 python-multipart python-dotenv httpx aiofiles

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Core installation failed
    pause
    exit /b 1
)

echo.
echo [3/4] Installing OpenCV and NumPy (REQUIRED)...
pip install opencv-python-headless==4.10.0.84 numpy==1.26.4

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] OpenCV installation failed - Video processing will not work!
    pause
    exit /b 1
)

echo.
echo [4/4] Creating directories...
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
echo OpenCV installed - Video processing ENABLED
echo.
echo Ready to process .mp4 files!
echo.
pause
