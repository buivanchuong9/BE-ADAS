# HƯỚNG DẪN DEPLOY LÊN UBUNTU SERVER
# kết nối vào database

psql -h localhost -U admin_user -d adas_db

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

### 5.5️⃣ **QUAN TRỌNG: Configure Redis Unix Socket** 🔧

**Lý do:** Fix lỗi "Error 22: Invalid argument" khi Celery connect Redis qua TCP.

```bash
# 1. Enable Unix socket trong Redis config
sudo tee -a /etc/redis/redis.conf > /dev/null <<EOF

# Unix socket for Celery (faster + no TCP socket errors)
unixsocket /var/run/redis/redis-server.sock
unixsocketperm 777
EOF

# 2. Restart Redis
sudo systemctl restart redis-server

# 3. Verify socket exists
ls -la /var/run/redis/redis-server.sock

# Expected output:
# srwxrwxrwx 1 redis redis 0 Feb  2 10:00 /var/run/redis/redis-server.sock

# 4. Test connection
### 5.5 ⚠️ **Redis Configuration (Shared Server Warning)**

#### **Option A: Shared Server (AN TOÀN - Recommended)**

Nếu server có nhiều app/user dùng chung Redis → KHÔNG nên config Redis:

```bash
# 1. Kiểm tra xem Redis có bị share không
sudo ss -tlnp | grep 6379
# Nếu thấy nhiều process khác nhau → shared server

# 2. Dùng mặc định TCP (KHÔNG cần thay đổi gì)
# App sẽ tự động dùng TCP connection

# 3. Restart Celery worker như bình thường
pkill -9 -f "celery"
cd ~/BE-ADAS/backend
python -m celery -A app.core.celery_config worker --loglevel=info --pool=solo
```

**Lý do:** Thay đổi Redis config ảnh hưởng TẤT CẢ app trên server → có thể làm sập service khác!

---

#### **Option B: Dedicated Redis (Nhanh nhất - Chỉ khi có Redis riêng)**

Nếu bạn **chắc chắn** Redis chỉ phục vụ app này (hoặc có quyền root config riêng):

```bash
# 1. Enable Unix socket
sudo tee -a /etc/redis/redis.conf > /dev/null <<EOF
unixsocket /var/run/redis/redis-server.sock
unixsocketperm 770
EOF

# 2. Set ownership
sudo chown redis:phonglv /var/run/redis/redis-server.sock

# 3. Restart Redis (⚠️ ảnh hưởng tất cả app dùng Redis!)
sudo systemctl restart redis-server

# 4. Test
redis-cli -s /var/run/redis/redis-server.sock ping  # Should return PONG

# 5. Enable trong app (set environment variable)
export REDIS_USE_UNIX_SOCKET=true
cd ~/BE-ADAS/backend
python -m celery -A app.core.celery_config worker --loglevel=info --pool=solo
```

### 6️⃣ Restart Server (V2.0 - NO Celery!)

**⚠️ IMPORTANT: Architecture V2.0**
- ❌ LOẠI BỎ: Celery, Redis, Celery Beat
- ✅ THAY BẰNG: PostgreSQL Queue + GPU Workers (gpu_worker_v2.py)

**Deployment Commands:**

```bash
# ========================================
# BƯỚC 1: KILL OLD PROCESSES
# ========================================
pkill -9 -f "celery"           # Kill Celery (cũ - không dùng nữa)
pkill -9 -f "gpu_worker"       # Kill GPU workers (cũ)
pkill -u phonglv -9 uvicorn    # Kill FastAPI
sleep 2

# ========================================
# BƯỚC 2: SETUP ENVIRONMENT
# ========================================
cd ~/BE-ADAS

# Load .env variables
export $(grep -v '^#' .env | xargs)

# Set Python path
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

# VERIFY PostgreSQL connection
echo "DATABASE_URL: $DATABASE_URL"
# Expected: postgresql://user:pass@localhost:5432/adas_production

# ========================================
# BƯỚC 3: START FASTAPI BACKEND
# ========================================
mkdir -p logs

nohup uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port 52000 \
  --proxy-headers \
  > logs/backend.log 2>&1 &

echo "✅ FastAPI started (PID: $!)"
sleep 3

# Verify API started
curl -s http://localhost:52000/health | head -5

# ========================================
# BƯỚC 4: START GPU WORKERS (V2)
# ========================================
# Số workers tùy theo VRAM:
#   - 24GB GPU → 4 workers (6GB/worker)
#   - 16GB GPU → 2-3 workers
#   - 12GB GPU → 2 workers

NUM_WORKERS=4

for i in $(seq 0 $((NUM_WORKERS - 1))); do
  nohup python workers/gpu_worker_v2.py \
    --worker-id worker_$i \
    --device cuda \
    > logs/worker_${i}.log 2>&1 &
  
  echo "✅ Worker $i started (PID: $!)"
  sleep 1
done

# ========================================
# BƯỚC 5: VERIFY SERVICES
# ========================================
sleep 2
echo ""
echo "=== RUNNING SERVICES ==="
ps aux | grep -E "uvicorn|gpu_worker_v2" | grep -v grep
echo ""

# Test API
echo "Testing API..."
curl -s http://localhost:52000/health

echo ""
echo "=== LOGS ==="
echo "Backend: tail -f logs/backend.log"
echo "Worker 0: tail -f logs/worker_0.log"
echo "Worker 1: tail -f logs/worker_1.log"
echo "Worker 2: tail -f logs/worker_2.log"
echo "Worker 3: tail -f logs/worker_3.log"
echo ""
echo "GPU Monitor: watch -n 1 nvidia-smi"
```

**Giải thích V2 Architecture:**
- ❌ **LOẠI BỎ:** `celery worker`, `celery beat`, Redis  
- ✅ **THAY BẰNG:** `gpu_worker_v2.py` (multi-process, tự động claim jobs)  
- ✅ **JOB QUEUE:** PostgreSQL với atomic locking (`SELECT FOR UPDATE SKIP LOCKED`)  
- ✅ **NEW FEATURES:** HLS progressive streaming + Optical Flow lane optimization (80% faster)

---

### 6.5️⃣ **OPTION B: Dùng Screen (Recommended - Tắt Terminal Được)**

**Ưu điểm:** Detach/reattach session, tắt SSH terminal không mất process

```bash
# Install screen (nếu chưa có)
sudo apt-get install screen -y

cd ~/BE-ADAS
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

# Tạo screen cho API
screen -dmS adas-api bash -c "
  uvicorn backend.app.main:app --host 0.0.0.0 --port 52000 --proxy-headers
"

# Tạo screen cho workers (loop 0-3)
for i in {0..3}; do
  screen -dmS adas-worker-$i bash -c "
    export DATABASE_URL='$DATABASE_URL'
    export PYTHONPATH='$PYTHONPATH'
    cd ~/BE-ADAS
    python workers/gpu_worker_v2.py --worker-id worker_$i --device cuda
  "
done

# Verify screens
screen -ls

# Xem log worker 0 (real-time)
screen -r adas-worker-0
# Press Ctrl+A, D để thoát (vẫn chạy background)

# Kill tất cả khi cần restart
screen -X -S adas-api quit
for i in {0..3}; do screen -X -S adas-worker-$i quit; done
```

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

# 5. Kill tất cả services cũ
pkill -9 -f "celery"
pkill -u phonglv -9 uvicorn
redis-cli FLUSHALL

# 6. Export env và path
cd ~/BE-ADAS
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

# 7. Start API
nohup uvicorn backend.app.main:app --host 0.0.0.0 --port 52000 --proxy-headers > backend.log 2>&1 &

# 8. Start Celery Worker
cd ~/BE-ADAS
nohup python -m celery -A app.core.celery_config worker --loglevel=info --pool=solo > logs/worker.log 2>&1 &

# 9. Start Celery Beat
cd ~/BE-ADAS
nohup python -m celery -A app.core.celery_config beat --loglevel=info > logs/beat.log 2>&1 &

# 10. Xem log
tail -f backend.log

# 11. Test (Ctrl+C để thoát tail, rồi test)
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

# Kill tất cả services cũ
pkill -9 -f "celery"
pkill -u phonglv -9 uvicorn
redis-cli FLUSHALL

# Export env và path
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

# Start API
nohup uvicorn backend.app.main:app --host 0.0.0.0 --port 52000 --proxy-headers > backend.log 2>&1 &

# Start Celery Worker
cd ~/BE-ADAS
nohup python -m celery -A app.core.celery_config worker --loglevel=info --pool=solo > logs/worker.log 2>&1 &

# Start Celery Beat
cd ~/BE-ADAS
nohup python -m celery -A app.core.celery_config beat --loglevel=info > logs/beat.log 2>&1 &

# Xem log
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
