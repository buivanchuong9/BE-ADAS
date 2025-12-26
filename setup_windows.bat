# ================================================
# WINDOWS SERVER DEPLOYMENT - AUTO SETUP
# Chạy file này để tự động cấu hình .env
# ================================================

@echo off
echo ========================================
echo ADAS Backend - Windows Server Setup
echo ========================================
echo.

REM Kiểm tra thư mục hiện tại
if not exist "backend" (
    echo ERROR: Vui long chay script nay tu thu muc BE-ADAS
    echo Current directory: %CD%
    pause
    exit /b 1
)

echo [1/5] Tao thu muc storage...
if not exist "backend\storage\raw" mkdir "backend\storage\raw"
if not exist "backend\storage\result" mkdir "backend\storage\result"
if not exist "backend\storage\audio_cache" mkdir "backend\storage\audio_cache"
if not exist "backend\storage\snapshots" mkdir "backend\storage\snapshots"
if not exist "backend\logs" mkdir "backend\logs"
echo ✓ Thu muc storage da duoc tao

echo.
echo [2/5] Copy file cau hinh production...
copy /Y .env.production backend\.env
echo ✓ File .env da duoc tao

echo.
echo [3/5] QUAN TRONG - Can sua thong tin sau:
echo.
echo Mo file: backend\.env
echo.
echo Tim dong: DB_PASSWORD=THAY_PASSWORD_SQL_SERVER_O_DAY
echo Sua thanh: DB_PASSWORD=your_actual_password
echo.
echo Tim dong: SECRET_KEY=...
echo Sua thanh: SECRET_KEY=your-random-32-character-secret-key
echo.
pause

echo.
echo [4/5] Mo file .env de ban sua...
notepad backend\.env

echo.
echo [5/5] Kiem tra cau hinh...
echo.
type backend\.env | findstr /C:"DB_PASSWORD" /C:"SECRET_KEY" /C:"PORT"
echo.

echo ========================================
echo HOAN THANH SETUP!
echo ========================================
echo.
echo KE TIEP:
echo 1. Kiem tra lai DB_PASSWORD trong backend\.env
echo 2. Chay: python run.py --production
echo 3. Mo trinh duyet: http://localhost:52000/docs
echo.
echo Neu gap loi, xem file: SQL_SERVER_SETUP.md
echo ========================================
pause
