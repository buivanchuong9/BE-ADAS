# 🚀 HƯỚNG DẪN CHẠY Dự ÁN ADAS BACKEND

## 📋 Yêu Cầu Hệ Thống

### Windows Server:
- Windows 10/11 hoặc Windows Server 2019/2022
- Python 3.11.x (khuyến nghị 3.11.7)
- SQL Server 2019/2022 Express trở lên
- ODBC Driver 17/18 for SQL Server
- RAM: ≥8GB (khuyến nghị 16GB)
- GPU: CUDA-capable NVIDIA GPU (tùy chọn, có thể chạy CPU)

### macOS/Linux (Development):
- Python 3.11.x
- PostgreSQL hoặc SQL Server (Docker)
- RAM: ≥8GB

---

## 🔧 CÁCH 1: CHẠY DEVELOPMENT (Máy Cá Nhân)

### Bước 1: Clone Repository
```bash
git clone https://github.com/buivanchuong9/BE-ADAS.git
cd BE-ADAS
```

### Bước 2: Tạo Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Bước 3: Cài Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**LƯU Ý**: Nếu gặp lỗi `sqlalchemy==2.0.36 not found`, chạy:
```bash
pip install sqlalchemy==2.0.25 pyodbc==5.1.0 alembic==1.13.1
```

### Bước 4: Cấu Hình Database

#### Option A: SQL Server (Windows)
1. Cài SQL Server 2019 Express
2. Tạo database `adas_db`
3. Tạo file `.env`:
```env
DATABASE_URL=mssql+pyodbc://sa:YourPassword@localhost/adas_db?driver=ODBC+Driver+17+for+SQL+Server

SECRET_KEY=your-secret-key-change-this
ENVIRONMENT=development
```

#### Option B: SQLite (Nhanh - Cho Test)
```env
DATABASE_URL=sqlite:///./adas.db
SECRET_KEY=your-secret-key-change-this
ENVIRONMENT=development
```

### Bước 5: Khởi Tạo Database
```bash
cd backend
python scripts/init_db.py
```

### Bước 6: Chạy Server
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Truy cập:**
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

---

## 🏭 CÁCH 2: CHẠY PRODUCTION (Windows Server)

### Bước 1: Cài Python 3.11
```powershell
# Download từ python.org
# Chọn "Add Python to PATH"
python --version  # Kiểm tra: 3.11.x
```

### Bước 2: Cài SQL Server
1. Download SQL Server 2022 Express
2. Cài SSMS (SQL Server Management Studio)
3. Enable TCP/IP trong SQL Configuration Manager
4. Tạo database `adas_production`

### Bước 3: Cài ODBC Driver
```powershell
# Download từ Microsoft
# ODBC Driver 18 for SQL Server (64-bit)
```

### Bước 4: Setup Project
```powershell
cd C:\inetpub\wwwroot\adas-backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Bước 5: Production Config
Tạo `.env`:
```env
DATABASE_URL=mssql+pyodbc://sa:StrongPassword123@localhost/adas_production?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes

SECRET_KEY=production-secret-key-min-32-chars-abc123xyz789
ENVIRONMENT=production
LOG_LEVEL=INFO

# AI Models
YOLO_MODEL_PATH=C:/inetpub/wwwroot/adas-backend/backend/models/yolov11n.pt
MEDIAPIPE_MODEL_PATH=C:/inetpub/wwwroot/adas-backend/backend/models

# Storage
UPLOAD_DIR=C:/inetpub/wwwroot/adas-backend/backend/storage/raw
RESULT_DIR=C:/inetpub/wwwroot/adas-backend/backend/storage/result
AUDIO_CACHE_DIR=C:/inetpub/wwwroot/adas-backend/backend/storage/audio_cache
```

### Bước 6: Init Database
```powershell
cd backend
python scripts/init_db.py
python scripts/seed_data.py  # Tạo user admin mặc định
```

### Bước 7: Test Chạy
```powershell
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Mở trình duyệt: http://localhost:8000/docs

### Bước 8: Setup IIS (Production)
Chi tiết xem file [WINDOWS_SERVER_DEPLOYMENT.md](WINDOWS_SERVER_DEPLOYMENT.md)

---

## 🧪 KIỂM TRA HỆ THỐNG

### Test 1: Dependencies
```bash
python -c "import fastapi, uvicorn, sqlalchemy, cv2, torch; print('✅ All imports OK')"
```

### Test 2: Database Connection
```bash
cd backend
python scripts/test_connection.py
```

### Test 3: Full Test Suite
```bash
python test_all_phases.py
```

**Kết quả mong đợi:** 7/7 tests PASSED

### Test 4: API Health Check
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-12-26T..."
}
```

---

## 🔥 TROUBLESHOOTING

### Lỗi: "No module named 'fastapi'"
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Lỗi: "pyodbc.Error: Data source name not found"
- Cài ODBC Driver 17/18 for SQL Server
- Kiểm tra connection string trong `.env`

### Lỗi: "sqlalchemy version not found"
```bash
pip install sqlalchemy==2.0.25
```

### Lỗi: "Could not find a version that satisfies torch"
```bash
# CPU only (nhanh hơn)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# CUDA 11.8 (nếu có GPU)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Lỗi: "Permission denied" (Windows)
- Chạy PowerShell as Administrator
- Disable antivirus tạm thời khi cài packages

---

## 📦 CÁC LỆNH THƯỜNG DÙNG

### Development
```bash
# Chạy server với hot-reload
cd backend
uvicorn app.main:app --reload --port 8000

# Chạy test
python test_all_phases.py

# Xem logs
tail -f logs/adas.log
```

### Database Migration
```bash
# Tạo migration mới
alembic revision -m "add new table"

# Chạy migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Production
```bash
# Chạy với Gunicorn (Linux)
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000

# Chạy với Uvicorn (Windows)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 🎯 API ENDPOINTS CHÍNH

### Authentication
- `POST /api/auth/login` - Đăng nhập
- `POST /api/auth/register` - Đăng ký

### Video Processing
- `POST /api/videos/upload` - Upload video
- `POST /api/videos/process` - Xử lý video
- `GET /api/videos/{id}/status` - Trạng thái xử lý

### Real-time Alerts
- `WS /ws/alerts` - WebSocket alerts stream

### AI Models
- `GET /api/models/list` - Danh sách models
- `POST /api/models/update` - Cập nhật model

Chi tiết: http://localhost:8000/docs

---

## 📱 CONTACT & SUPPORT

**Repository:** https://github.com/buivanchuong9/BE-ADAS.git

**Documentation:**
- [Windows Deployment](WINDOWS_SERVER_DEPLOYMENT.md)
- [Database Setup](DATABASE_SETUP_GUIDE.md)
- [Implementation Summary](IMPLEMENTATION_COMPLETE_PHASE_3-10.md)

**Team:** NCKH ADAS Development Team  
**Date:** December 2025
