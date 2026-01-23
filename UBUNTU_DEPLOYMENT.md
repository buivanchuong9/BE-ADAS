# HƯỚNG DẪN DEPLOY LÊN UBUNTU SERVER

## 📋 Các Bước Deploy

### 1️⃣ SSH vào Ubuntu Server

```bash
ssh user@your-server-ip
# Hoặc
ssh user@adas-api.aiotlab.edu.vn
```

### 2️⃣ Navigate đến thư mục project

```bash
cd /path/to/BE-ADAS
# Ví dụ: cd /home/ubuntu/BE-ADAS
```

### 3️⃣ Pull code mới từ GitHub

```bash
git pull origin main
```

Kết quả sẽ hiển thị:
```
Updating b61a9a4..c6aedcf
Fast-forward
 18 files changed, 1033 insertions(+), 7887 deletions(-)
 create mode 100644 DEPLOYMENT_CHECKLIST.md
 create mode 100644 FRONTEND_INTEGRATION.md
 create mode 100644 backend/app/core/supabase_auth.py
 ...
```

### 4️⃣ Install Dependencies Mới

```bash
# Activate virtual environment (nếu có)
source venv/bin/activate
# hoặc
source .venv/bin/activate

# Install supabase và các dependencies mới
pip install -r requirements.txt
```

Verify supabase đã được cài:
```bash
pip list | grep supabase
```

Nên thấy:
```
supabase              2.x.x
supabase-auth         2.x.x
supabase-functions    2.x.x
...
```

### 5️⃣ Kiểm Tra Config

```bash
# Xem config file
cat backend/app/core/config.py | grep SUPABASE
```

Nên thấy:
```python
SUPABASE_PROJECT_URL: str = "https://kijdjdtuyeywmthhuoac.supabase.co"
SUPABASE_ANON_KEY: str = "eyJhbGc..."
```

✅ **Đã có ANON_KEY rồi, không cần set thêm!**

### 6️⃣ Restart Server (Production Setup)

**Cách chạy thực tế trên server:**

```bash
# 1. Kill hết
pkill -9 -f "celery"
pkill -u phonglv -9 uvicorn

# 2. Vào thư mục GỐC
cd ~/BE-ADAS

# 3. Env & Path
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

# 4. START API (Giữ nguyên)
nohup uvicorn backend.app.main:app --host 0.0.0.0 --port 52000 --proxy-headers > backend.log 2>&1 &

# 5. START CELERY (SỬA LẠI: Dùng pool=solo để an toàn cho GPU)
# Lưu ý: Vì PYTHONPATH đã trỏ vào backend rồi, nên start từ "app" là đủ.
nohup python -m celery -A app.core.celery_config worker --loglevel=info --pool=solo > logs/worker.log 2>&1 &

# 6. Start Beat (SỬA LẠI tương tự)
nohup python -m celery -A app.core.celery_config beat --loglevel=info > logs/beat.log 2>&1 &

# 6. Xem log real-time
tail -f backend.log

tail -f logs/worker.log
```

**Giải thích từng lệnh:**
- `pkill -u phonglv -9 uvicorn` → Force kill tất cả process uvicorn của user phonglv
- `export $(grep -v '^#' .env | xargs)` → Load tất cả biến trong file .env
- `export PYTHONPATH=...` → Thêm backend vào Python path
- `nohup ... &` → Chạy server background, không bị kill khi đóng SSH
- `> backend.log 2>&1` → Redirect stdout và stderr vào file log
- `tail -f backend.log` → Xem log real-time

**Lưu ý:** Port là **52000** (không phải 8000)

### 7️⃣ Verify Server Đang Chạy

```bash
# Test health endpoint
curl http://localhost:52000/health

# Test auth endpoint
curl http://localhost:52000/api/auth/status
```

Kết quả mong đợi:
```json
{
  "status": "healthy",
  "service": "ADAS Video Analysis API",
  ...
}
```

```json
{
  "authenticated": false,
  "user": null
}
```

### 8️⃣ Test Từ Bên Ngoài (Production URL)

```bash
# Từ máy local hoặc máy khác
curl https://adas-api.aiotlab.edu.vn/health
curl https://adas-api.aiotlab.edu.vn/api/auth/status
```

---

## 🔧 Chi Tiết Từng Lệnh

### Full Command Set (Copy-Paste) - Production Ready

```bash
# 1. SSH vào server
ssh phonglv@adas-api.aiotlab.edu.vn

# 2. Vào thư mục project
cd ~/BE-ADAS

# 3. Pull code mới từ GitHub
git pull origin main

# 4. Install dependencies mới
pip install -r requirements.txt

# 5. Restart server
pkill -u phonglv -9 uvicorn
cd ~/BE-ADAS
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
nohup uvicorn backend.app.main:app --host 0.0.0.0 --port 52000 --proxy-headers > backend.log 2>&1 &

# 6. Xem log
tail -f backend.log

# 7. Test (Ctrl+C để thoát tail, rồi test)
curl http://localhost:52000/health
curl http://localhost:52000/api/auth/status
```

---

## ⚠️ Lưu Ý Quan Trọng

### 1. Không Cần Database Migration!

**Lý do:** Backend hiện tại sẽ query trực tiếp vào **Supabase Database** (table `users` bạn vừa tạo).

Config đã có:
- `SUPABASE_PROJECT_URL` ✅
- `SUPABASE_ANON_KEY` ✅

→ Backend sẽ tự động connect vào Supabase!

### 2. Port Configuration

- Backend chạy trên port **52000**
- Cloudflare/Nginx reverse proxy: 443/80 → 52000
- Đảm bảo Nginx config đúng:

```nginx
location / {
    proxy_pass http://localhost:52000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

### 3. Firewall

Đảm bảo port 52000 được mở (nếu cần):
```bash
sudo ufw allow 52000
```

### 4. Check Process

Xem server có đang chạy không:
```bash
ps aux | grep uvicorn
# hoặc
lsof -i:52000
```

---

## 🧪 Test End-to-End

### Từ Frontend:

```javascript
// 1. Login Supabase
const { data } = await supabase.auth.signInWithPassword({
  email: 'buivanchuong9t910@gmail.com',
  password: 'your_password'
})

const token = data.session.access_token

// 2. Call backend
const response = await fetch('https://adas-api.aiotlab.edu.vn/api/auth/me', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})

const userData = await response.json()
console.log(userData)
// Expected: {success: true, user: {id: 1, auth_id: "7b6b2ea6-...", ...}}
```

---

## 🐛 Troubleshooting

### Lỗi: "Module 'supabase' not found"
```bash
pip install supabase>=2.0.0
```

### Lỗi: "Connection refused"
→ Server chưa start hoặc đã die
```bash
# Check process
ps aux | grep uvicorn

# Restart
python run.py
```

### Lỗi: "Database unavailable"
→ Check SUPABASE_ANON_KEY trong config
```bash
cat backend/app/core/config.py | grep ANON_KEY
```

### Lỗi 401: "User not synced"
→ User chưa tồn tại trong Supabase `users` table
→ Tạo user trong Supabase Table Editor

---

## ✅ Checklist Hoàn Thành

- [ ] SSH vào server thành công
- [ ] `git pull` không có conflict
- [ ] `pip install -r requirements.txt` thành công
- [ ] `pip list | grep supabase` hiển thị version 2.x.x
- [ ] Server restart thành công (process ID hiển thị)
- [ ] `tail -f backend.log` thấy log "Application startup complete"
- [ ] `curl localhost:52000/health` return 200
- [ ] `curl https://adas-api.aiotlab.edu.vn/health` return 200
- [ ] Frontend có thể gọi API với Supabase token

---

## 🚀 Deploy Nhanh (TL;DR)

```bash
# Copy-paste toàn bộ block này vào terminal
ssh phonglv@adas-api.aiotlab.edu.vn
cd ~/BE-ADAS
git pull origin main
pip install -r requirements.txt
pkill -u phonglv -9 uvicorn
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
nohup uvicorn backend.app.main:app --host 0.0.0.0 --port 52000 --proxy-headers > backend.log 2>&1 &
tail -f backend.log
```

**Sau khi thấy log chạy OK, Ctrl+C rồi test:**
```bash
curl http://localhost:52000/health
curl https://adas-api.aiotlab.edu.vn/health
```

**Thời gian:** 2-3 phút  
**Khó:** ⭐ (Rất dễ)

✅ **Sẵn sàng!**
