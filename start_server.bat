@echo off
REM Start ADAS Backend Server - Windows
REM Production-grade startup script

echo =========================================
echo ADAS Backend - Starting...
echo =========================================

REM Create required directories
if not exist logs mkdir logs
if not exist uploads\videos mkdir uploads\videos
if not exist ai_models\weights mkdir ai_models\weights

REM Check Python version
python --version

REM Start server
echo Starting FastAPI server on port 52000...
python main.py

pause
