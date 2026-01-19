# 🛡️ SAFE DEPLOYMENT - Hệ Thống Celery + Redis (An Toàn Tuyệt Đối)

**Mục đích**: Deploy hệ thống xịn (Celery + Redis) nhưng **KHÔNG BAO GIỜ làm sập server**

---

## ⚠️ QUY TẮC VÀNG

```
✅ CHỈ kill process của BẠN (bằng PID cụ thể)
✅ CHỈ dùng Redis CÓ SẴN (không tự start)
✅ CHỈ restart service ADAS (không động service khác)
❌ TUYỆT ĐỐI KHÔNG dùng: pkill, killall, restart all, reboot
```

---

## 📋 CHECKLIST TRƯỚC KHI DEPLOY

### 1. Kiểm Tra Redis Đã Có Chưa

```bash
# Kiểm tra Redis đang chạy
redis-cli ping

# Phải trả về: PONG
# Nếu lỗi → Hỏi admin trước!
```

**Nếu Redis chưa có**: Liên hệ admin trường để cài Redis hoặc dùng Redis trên server khác.

### 2. Kiểm Tra Process Đang Chạy CỦA BẠN

```bash
# Xem process của user phonglv
ps aux | grep phonglv | grep -E "uvicorn|celery"

# Output ví dụ:
# phonglv   12345  0.5  1.2  uvicorn backend.app.main:app
# phonglv   12346  0.3  0.8  celery worker
```

Ghi nhớ các **PID** (cột thứ 2): 12345, 12346

### 3. Kiểm Tra Port 52000 Có Đang Dùng Không

```bash
# Xem process đang dùng port 52000
lsof -i :52000

# Hoặc
netstat -tulnp | grep 52000

# Nếu thấy PID → ghi nhớ để kill sau
```

---

## 🚀 BƯỚC 1: CHUẨN BỊ

### 1.1. SSH vào Server

```bash
ssh phonglv@server_ip
```

### 1.2. Pull Code Mới

```bash
cd ~/BE-ADAS

# Pull code từ Git
git pull origin main

# Hoặc upload file trực tiếp
# scp -r backend/ phonglv@server:/home/phonglv/BE-ADAS/
```

### 1.3. Cài Dependencies (nếu cần)

```bash
# Activate conda environment
conda activate be-adas

# Cài dependencies mới (Celery, Redis)
pip install celery==5.3.4 redis==5.0.1 kombu==5.3.4

# Kiểm tra
pip list | grep celery
```

---

## 🛑 BƯỚC 2: DỪNG PROCESS CŨ (AN TOÀN)

### Cách 1: Kill Bằng PID Cụ Thể (AN TOÀN NHẤT)

```bash
# Xem PID của uvicorn
ps aux | grep "phonglv" | grep "uvicorn" | grep -v grep
# Ghi nhớ PID, ví dụ: 12345

# Kill ĐÚNG process đó
kill -9 12345

# Xem PID của celery worker (nếu có)
ps aux | grep "phonglv" | grep "celery worker" | grep -v grep
# Ví dụ PID: 12346

kill -9 12346

# Xem PID của celery beat (nếu có)
ps aux | grep "phonglv" | grep "celery beat" | grep -v grep
# Ví dụ PID: 12347

kill -9 12347
```

### Cách 2: Kill Theo User + Process Name (An Toàn)

```bash
# Kill CHỈ uvicorn của user phonglv
pkill -u phonglv -f "uvicorn backend.app.main:app"

# Kill CHỈ celery của user phonglv
pkill -u phonglv -f "celery.*worker"
pkill -u phonglv -f "celery.*beat"
```

**KHÔNG dùng**: `pkill uvicorn` (không có `-u phonglv`) → Nguy hiểm!

### Cách 3: Nếu Dùng Supervisor

```bash
# Restart CHỈ service ADAS
supervisorctl restart adas_api
supervisorctl restart adas_celery_worker
supervisorctl restart adas_celery_beat

# KHÔNG dùng: supervisorctl restart all
```

---

## ▶️ BƯỚC 3: START SERVICES MỚI

### 3.1. Load Environment Variables

```bash
cd ~/BE-ADAS

# Load từ file .env (nếu có)
export $(grep -v '^#' .env | xargs)

# Set PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

# Kiểm tra
echo $PYTHONPATH
```

### 3.2. Verify Redis Connection

```bash
# Test kết nối Redis
redis-cli ping
# Phải trả về: PONG

# Kiểm tra Redis URL trong .env
grep REDIS_URL .env
# Nếu không có, thêm vào:
# echo "REDIS_URL=redis://localhost:6379/0" >> .env
```

### 3.3. Start API Server

```bash
nohup uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port 52000 \
  --proxy-headers \
  > logs/api.log 2>&1 &

# Ghi nhớ PID
echo "API Server PID: $!"

# Kiểm tra log
tail -n 20 logs/api.log
```

**Kiểm tra thành công**:
```
INFO:     Uvicorn running on http://0.0.0.0:52000
INFO:     Application startup complete
```

### 3.4. Start Celery Worker

```bash
nohup celery -A backend.app.core.celery_config worker \
  --loglevel=info \
  --concurrency=2 \
  --queues=celery,video_processing \
  > logs/celery_worker.log 2>&1 &

# Ghi nhớ PID
echo "Celery Worker PID: $!"

# Kiểm tra log
tail -n 20 logs/celery_worker.log
```

**Kiểm tra thành công**:
```
[INFO/MainProcess] Connected to redis://localhost:6379/0
[INFO/MainProcess] celery@hostname ready.
```

### 3.5. Start Celery Beat (Cleanup Task)

```bash
nohup celery -A backend.app.core.celery_config beat \
  --loglevel=info \
  > logs/celery_beat.log 2>&1 &

# Ghi nhớ PID
echo "Celery Beat PID: $!"

# Kiểm tra log
tail -n 20 logs/celery_beat.log
```

**Kiểm tra thành công**:
```
[INFO/MainProcess] beat: Starting...
[INFO/MainProcess] Scheduler: Sending due task ...
```

---

## ✅ BƯỚC 4: VERIFY DEPLOYMENT

### 4.1. Kiểm Tra Processes Đang Chạy

```bash
# Xem tất cả process của bạn
ps aux | grep phonglv | grep -E "uvicorn|celery"

# Phải thấy 3 processes:
# 1. uvicorn backend.app.main:app
# 2. celery worker
# 3. celery beat
```

### 4.2. Test API Health

```bash
# Test API endpoint
curl http://localhost:52000/

# Hoặc public URL
curl https://adas-api.aiotlab.edu.vn/
```

**Response mong đợi**:
```json
{
  "message": "ADAS API is running",
  "version": "2.1"
}
```

### 4.3. Test Upload Video

```bash
# Upload video nhỏ để test
curl -X POST "http://localhost:52000/api/video/upload" \
  -F "file=@test_video.mp4" \
  -F "video_type=dashcam"

# Response:
# {"job_id": "xxx", "status": "queued"}
```

### 4.4. Monitor Celery Queue

```bash
# Xem task trong queue
celery -A backend.app.core.celery_config inspect active

# Kiểm tra worker status
celery -A backend.app.core.celery_config inspect stats
```

### 4.5. Real-time Log Monitoring

```bash
# Terminal 1: API logs
tail -f logs/api.log

# Terminal 2: Worker logs
tail -f logs/celery_worker.log

# Terminal 3: Beat logs
tail -f logs/celery_beat.log
```

---

## 📝 SAVE PIDs (Quan Trọng!)

Sau khi start xong, lưu PIDs để dễ quản lý:

```bash
# Tạo file lưu PIDs
cat > ~/BE-ADAS/pids.txt << EOF
# ADAS Service PIDs - $(date)
API_PID=$(pgrep -u phonglv -f "uvicorn backend.app.main:app")
WORKER_PID=$(pgrep -u phonglv -f "celery.*worker")
BEAT_PID=$(pgrep -u phonglv -f "celery.*beat")
EOF

# Xem PIDs
cat ~/BE-ADAS/pids.txt
```

**Kill dễ dàng khi cần**:
```bash
# Load PIDs
source ~/BE-ADAS/pids.txt

# Kill từng service
kill -9 $API_PID
kill -9 $WORKER_PID
kill -9 $BEAT_PID
```

---

## 🔄 RESTART AN TOÀN

Khi cần restart (ví dụ: sau khi sửa code):

```bash
# 1. Load PIDs
source ~/BE-ADAS/pids.txt

# 2. Kill processes cũ
kill -9 $API_PID $WORKER_PID $BEAT_PID

# 3. Chờ 2 giây
sleep 2

# 4. Start lại (copy lệnh từ BƯỚC 3)
# ... (giống BƯỚC 3.3, 3.4, 3.5)
```

---

## 🚨 TROUBLESHOOTING

### Lỗi: "Connection refused" khi kết nối Redis

```bash
# Kiểm tra Redis đang chạy
redis-cli ping

# Nếu không chạy → Liên hệ admin
# KHÔNG tự start: redis-server (nguy hiểm!)
```

### Lỗi: "Address already in use" (port 52000)

```bash
# Xem process đang dùng port 52000
lsof -i :52000

# Kill process cụ thể (dùng PID từ output trên)
kill -9 <PID>

# Hoặc đổi port (trong .env):
# PORT=52001
```

### Lỗi: Celery không nhận task

```bash
# Kiểm tra Celery worker đang chạy
ps aux | grep celery | grep worker

# Kiểm tra kết nối Redis
redis-cli
> PING
> KEYS *

# Restart worker
pkill -u phonglv -f "celery.*worker"
# Sau đó start lại (BƯỚC 3.4)
```

### Lỗi: Process bị kill tự động

```bash
# Kiểm tra logs hệ thống
tail -f /var/log/syslog | grep phonglv

# Có thể do:
# - Out of memory → Giảm concurrency
# - Admin kill → Liên hệ admin
# - Supervisor restart → Cấu hình lại supervisor
```

---

## 📊 MONITORING

### Disk Usage

```bash
# Kiểm tra dung lượng
du -sh ~/BE-ADAS/backend/storage/*

# Cleanup manual (nếu cần)
find ~/BE-ADAS/backend/storage/result -type f -mtime +7 -delete
```

### Memory Usage

```bash
# Xem memory của processes
ps aux | grep phonglv | grep -E "uvicorn|celery" | awk '{print $2, $4, $11}'

# Nếu quá cao → Giảm concurrency:
# celery worker --concurrency=1
```

### Log Rotation

```bash
# Tạo cron job để rotate logs
crontab -e

# Thêm:
# 0 3 * * * cd ~/BE-ADAS && mv logs/api.log logs/api.log.$(date +\%Y\%m\%d) && : > logs/api.log
```

---

## ✅ CHECKLIST HOÀN THÀNH

- [ ] Redis đang chạy (`redis-cli ping` → PONG)
- [ ] Code đã pull về (`git pull`)
- [ ] Dependencies đã cài (`pip install ...`)
- [ ] Process cũ đã kill (bằng PID cụ thể)
- [ ] API server đang chạy (check port 52000)
- [ ] Celery worker đang chạy (check logs)
- [ ] Celery beat đang chạy (check logs)
- [ ] Test upload thành công
- [ ] PIDs đã lưu vào file

---

## 🎯 TÓM TẮT: 5 Bước Deploy An Toàn

```bash
# 1. Kiểm tra Redis
redis-cli ping

# 2. Pull code
cd ~/BE-ADAS && git pull

# 3. Kill process cũ (dùng PID)
ps aux | grep phonglv | grep uvicorn  # Ghi PID
kill -9 <PID>

# 4. Start services mới
cd ~/BE-ADAS
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
nohup uvicorn backend.app.main:app --host 0.0.0.0 --port 52000 > logs/api.log 2>&1 &
nohup celery -A backend.app.core.celery_config worker --concurrency=2 > logs/worker.log 2>&1 &
nohup celery -A backend.app.core.celery_config beat > logs/beat.log 2>&1 &

# 5. Verify
tail -f logs/api.log
curl http://localhost:52000/
```

---

## 🔒 Lệnh CẤM TUYỆT ĐỐI

```bash
❌ sudo reboot
❌ sudo shutdown
❌ pkill -9 uvicorn              # Không có -u phonglv
❌ killall uvicorn
❌ supervisorctl restart all
❌ systemctl restart supervisord
❌ redis-server                  # Tự start Redis mới
❌ systemctl restart redis
```đê

**Chỉ dùng**:
```bash
✅ kill -9 <PID>                 # Kill theo PID cụ thể
✅ pkill -u phonglv -f "..."     # Kill theo user + pattern
✅ supervisorctl restart adas_*  # Restart CHỈ service ADAS
```

---

**Nguyên tắc**: Luôn kiểm tra 2 lần trước khi chạy lệnh có từ khóa: `kill`, `restart`, `stop`, `shutdown`

**Deployment an toàn = Deployment thành công!** 🎉
