@echo off
REM =================================================
REM ADAS Backend - Quick Start Production Mode
REM Chạy file này từ bất kỳ đâu để start server
REM =================================================

cd /d "%~dp0"
echo ========================================
echo   ADAS Backend - Production Mode
echo ========================================
echo.

python run.py --production

pause
