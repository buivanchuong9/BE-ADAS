## 🔧 Chi Tiết Từng Lệnh

### Full Command Set (Copy-Paste) - Production Ready
# kết nối vào database

sudo -u postgres psql -d adas_db

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
# 5. Kill tất cả services cũ
pkill -u phonglv -f "gpu_worker.py"
pkill -u phonglv -f "uvicorn backend.app.main"
pkill -u phonglv -f "celery -A"

# 6. Export env và path
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=$PYTHONPATH:$(pwd)

# 7. Start API (Backend)
echo "🚀 Starting API Server..."
nohup python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 52000 --workers 4 --proxy-headers > api.log 2>&1 &

# 8. Start GPU Workers (Video Processing)
# Launch 4 workers for optimal A30 utilization
echo "🚀 Starting 4 GPU Workers..."
for i in {0..3}; do
    nohup python3 workers/gpu_worker_v3_hybrid.py --worker-id worker_$i --database-url "$DATABASE_URL" > worker_$i.log 2>&1 &
done

# 9. Xem log (API)
tail -f api.log
#10. xem worker
ps aux | grep gpu_worker_v3_hybrid

# 10. Test (Ctrl+C để thoát tail, rồi test)
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
