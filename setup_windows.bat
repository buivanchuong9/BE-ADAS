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
echo.
echo Chon cach chay SQL Server:
echo   1. SQL Server Native (cai tren Windows)
echo   2. SQL Server Docker (chay trong container)
echo.
set /p SQL_TYPE="Nhap 1 hoac 2: "

if "%SQL_TYPE%"=="2" (
    echo.
    echo ✓ Su dung SQL Server Docker config
    copy /Y .env.production.docker backend\.env
    echo.
    echo TAT CA THONG TIN DA DUOC CAU HINH SAN!
    echo   - DB_PASSWORD: 123456aA@$
    echo   - SECRET_KEY: adas-prod-2025-k8s9m2n4p6q7r1s3t5v8w0x2y4z6a1b3c5d7e9f
    echo   - Port: 52000
    echo.
    echo KHONG CAN SUA GI THEM!
    echo.
    echo Chay Docker SQL Server:
    echo   docker run -d --name sql_server_demo -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=123456aA@$" -p 1433:1433 mcr.microsoft.com/mssql/server:2019-latest
    echo.
) else (
    echo.
    echo ✓ Su dung SQL Server Native config
    copy /Y .env.production.native backend\.env
    echo.
    echo DA CAU HINH:
    echo   - SECRET_KEY: adas-prod-2025-k8s9m2n4p6q7r1s3t5v8w0x2y4z6a1b3c5d7e9f
    echo   - Port: 52000
    echo.
    echo CAN SUA:
    echo   - DB_PASSWORD: password SQL Server cua ban
    echo.
    pause
    echo.
    echo Mo file .env de sua DB_PASSWORD...
    notepad backend\.env
)

echo.
echo [3/5] Kiem tra cau hinh...
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
