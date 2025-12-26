# ADAS Backend - Lệnh Khởi Động Nhanh

## 🚀 CÁCH CHẠY ĐƠN GIẢN NHẤT

### 1️⃣ Lần Đầu Tiên (Cài đặt + Chạy)
```bash
# Bước 1: Clone code
git clone https://github.com/buivanchuong9/BE-ADAS.git
cd BE-ADAS

# Bước 2: Tạo virtual environment
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# Bước 3: Cài dependencies
pip install -r requirements.txt

# Bước 4: Chạy!
python run.py
```

### 2️⃣ Lần Sau (Chỉ cần chạy)
```bash
# Windows
cd BE-ADAS
.\venv\Scripts\activate
python run.py

# macOS/Linux
cd BE-ADAS
source venv/bin/activate
python run.py
```

---

## 🎯 CÁC LỆNH CHÍNH

### Development Mode (Khuyến nghị)
```bash
python run.py
```
- ✅ Auto reload khi code thay đổi
- ✅ Port: 8000
- ✅ Tự động init database
- 📖 Docs: http://localhost:8000/docs

### Production Mode
```bash
python run.py --production
```
- ✅ Port: 52000
- ✅ No reload (ổn định hơn)
- 📖 Docs: http://localhost:52000/docs

### Custom Port
```bash
python run.py --port 8080
```

### Không Auto Reload
```bash
python run.py --no-reload
```

---

## 🔧 LỆNH THAY THẾ (Nếu run.py Không Chạy)

### Cách 1: Chạy trực tiếp Uvicorn
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Cách 2: Init DB riêng
```bash
cd backend
python scripts/init_db.py
uvicorn app.main:app --reload
```

---

## ✅ SAU KHI CHẠY

### Truy cập các endpoint:
- 📖 **API Docs**: http://localhost:8000/docs
- 🏥 **Health Check**: http://localhost:8000/health
- 📊 **OpenAPI Schema**: http://localhost:8000/openapi.json

### Test API:
```bash
# Health check
curl http://localhost:8000/health

# Production
curl https://adas-api.aiotlab.edu.vn:52000/health
```

---

## 🐛 FIX LỖI THƯỜNG GẶP

### Lỗi: "No module named 'fastapi'"
```bash
pip install -r requirements.txt
```

### Lỗi: "SyntaxError: import * only allowed at module level"
✅ Đã fix trong code mới nhất, pull lại:
```bash
git pull origin main
```

### Lỗi: "numpy version conflict"
```bash
pip uninstall numpy opencv-python -y
pip install numpy==1.26.4
pip install opencv-python-headless==4.10.0.84
```

### Lỗi: "Database error"
```bash
cd backend
python scripts/init_db.py
```

### Lỗi: "Permission denied" (Windows)
- Chạy CMD/PowerShell as Administrator
- Tắt antivirus tạm thời

---

## 📦 TẤT CẢ TRONG MỘT LỆNH (QUICK START)

### Windows
```cmd
git clone https://github.com/buivanchuong9/BE-ADAS.git && cd BE-ADAS && python -m venv venv && .\venv\Scripts\activate && pip install -r requirements.txt && python run.py
```

### macOS/Linux
```bash
git clone https://github.com/buivanchuong9/BE-ADAS.git && cd BE-ADAS && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python run.py
```

---

## 🎓 TÓM TẮT

| Lệnh | Mục đích |
|------|----------|
| `python run.py` | Chạy development (khuyến nghị) |
| `python run.py --production` | Chạy production mode |
| `python run.py --port 8080` | Chạy với port tùy chỉnh |
| `cd backend && uvicorn app.main:app --reload` | Chạy trực tiếp (thay thế) |

**Mở trình duyệt**: http://localhost:8000/docs 🎉
