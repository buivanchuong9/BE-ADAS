@echo off
REM Quick startup test - Run before deploying to Windows Server
echo ====================================================================
echo              ADAS Backend - Startup Test
echo ====================================================================
echo.

echo [1] Testing Python installation...
python --version
if errorlevel 1 (
    echo [FAIL] Python not found
    pause
    exit /b 1
)
echo [OK]
echo.

echo [2] Testing project files...
if not exist main.py (
    echo [FAIL] main.py not found
    pause
    exit /b 1
)
echo [OK]
echo.

echo [3] Testing Python syntax...
python -m py_compile main.py
if errorlevel 1 (
    echo [FAIL] Syntax errors detected
    pause
    exit /b 1
)
echo [OK]
echo.

echo [4] Testing dependencies...
python test_server.py
if errorlevel 1 (
    echo [FAIL] Dependencies test failed
    pause
    exit /b 1
)
echo.

echo ====================================================================
echo                    ALL TESTS PASSED
echo ====================================================================
echo.
echo Server is ready to start!
echo.
echo To start server:
echo   - Double-click: start-be.bat
echo   - Or run: python main.py
echo.
echo Public API:  https://adas-api.aiotlab.edu.vn
echo Local API:   http://localhost:52000
echo API Docs:    http://localhost:52000/docs
echo.
pause
