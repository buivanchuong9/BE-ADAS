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
pkill -u phonglv -f "gpu_worker"
pkill -u phonglv -f "uvicorn backend.app.main"
pkill -9 ffmpeg  

# 6. Export env và path
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=$PYTHONPATH:$(pwd)



# 7. Start API (Backend)
echo "🚀 Starting API Server..."
nohup python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 52000 --workers 4 --proxy-headers > api.log 2>&1 &

# 8. Start GPU Workers (Python Only - STABLE)
# Khuyến nghị: 1 worker cho mỗi GPU A30
echo "🚀 Starting GPU Worker (Simple & Stable)..."
# Log worker vào api.log luôn để xem 1 chỗ
nohup python3 workers/gpu_worker_simple.py --worker-id worker_0 --device cuda --database-url "$DATABASE_URL" >> api.log 2>&1 &

# Nếu có nhiều GPU, chạy thêm worker:
# CUDA_VISIBLE_DEVICES=1 nohup python3 workers/gpu_worker_simple.py --worker-id worker_1 --device cuda > worker_1.log 2>&1 &

# 9. Xem log (API + Worker cùng 1 chỗ)
tail -f api.log
# Sẽ thấy:
#   [GPU] Loading pipeline for 'dashcam'...
#   [GPU] ✅ dashcam pipeline sẵn sàng
#   [JOB] <uuid> - Start processing
#   [PROGRESS] [<uuid>]  15%  frame=150/1000  speed=42.3fps  ETA=20s
#   [PROGRESS] [<uuid>]  45%  frame=450/1000  speed=45.1fps  ETA=12s
#   [DONE] Job <uuid> completed in 22s (45.4 fps)

# 10. Verify latest code is pulled
git log --oneline -1
# Should show: "fix: remove video_path from job_data..."

# 11. Xem worker đang chạy
ps aux | grep gpu_worker_simple

# 11. Kiểm tra không có zombie FFmpeg (QUAN TRỌNG!)
ps aux | grep ffmpeg
# Nên RỖNG hoặc chỉ có process đang encode

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
- [ ] `tail -f api.log` thấy log "Application startup complete"
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
pkill -u phonglv -f "gpu_worker"
pkill -u phonglv -9 uvicorn
pkill -9 ffmpeg  # Kill zombie FFmpeg (CRITICAL!)

# Export env và path
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

# Start API (log vào api.log)
nohup uvicorn backend.app.main:app --host 0.0.0.0 --port 52000 --proxy-headers >> api.log 2>&1 &

# Start GPU Worker (Python Only - STABLE)
cd ~/BE-ADAS
# Gộp worker log vào api.log để theo dõi 1 chỗ
nohup python3 workers/gpu_worker_simple.py --worker-id worker_0 --device cuda --database-url "$DATABASE_URL" >> api.log 2>&1 &

# Xem log tất cả (API + Worker trong 1 luồng)
tail -f api.log

# Check worker running
ps aux | grep gpu_worker_simple

# Check no zombie FFmpeg (CRITICAL!)
ps aux | grep ffmpeg
# Should be EMPTY or only active encoding processes
```

**Sau khi thấy log chạy OK, Ctrl+C rồi test:**
```bash
curl http://localhost:52000/health
curl https://adas-api.aiotlab.edu.vn/health

# Monitor GPU utilization (should be >80% when processing)
watch nvidia-smi

# View ALL logs (API + Worker) in one stream
tail -f api.log

# Filter chỉ worker progress
tail -f api.log | grep -E "PROGRESS|JOB|DONE|GPU|ERROR"
```

**Thời gian:** 2-3 phút  
**Khó:** ⭐ (Rất dễ)

---

## 📊 MONITORING & VERIFICATION

### Check System Health
```bash
# 1. Check services running
ps aux | grep -E "uvicorn|gpu_worker_simple"

# 2. Check GPU utilization
nvidia-smi

# 3. Check NO zombie FFmpeg (CRITICAL!)
ps aux | grep ffmpeg
# Should be EMPTY when no job running

# 4. Check worker logs (gộp trong api.log)
grep PROGRESS api.log | tail -5
# Should see: [PROGRESS] [uuid]  75%  frame=750/1000  speed=45fps  ETA=5s

grep DONE api.log | tail -5
# Should see: [DONE] Job uuid completed in 22s (45.4 fps)

# 5. Test video upload
curl -X POST http://localhost:52000/api/video/upload \
  -F "file=@test_video.mp4" \
  -F "video_type=dashcam" \
  -F "device=cuda"
```

### Expected Performance (A30 GPU)
- Processing speed: **40-60 FPS** (1.5-2x realtime)
- VRAM usage: **4-5 GB** per worker
- CPU usage: **< 50%** (overlay is CPU but lightweight)
- Latency: **< 30s** for 60s video
- Zombie processes: **ZERO** ✅

### Troubleshooting
```bash
# If video doesn't play on Safari/Chrome:
# Check pixel format (MUST be yuv420p)
ffprobe -v error -select_streams v:0 \
  -show_entries stream=pix_fmt \
  -of default=noprint_wrappers=1:nokey=1 \
  result.mp4
# Expected: yuv420p

# If VRAM leak detected:
# Restart worker to clear
pkill -f gpu_worker_simple
nohup python3 workers/gpu_worker_simple.py --worker-id worker_0 --device cuda --database-url "$DATABASE_URL" >> api.log 2>&1 &
```

✅ **Sẵn sàng!**
