# API Endpoints - ADAS Video Analysis

**Server:** https://adas-api.aiotlab.edu.vn/  
**Port:** 52000  
**Docs:** https://adas-api.aiotlab.edu.vn/docs

---

## ✅ Available Endpoints

### 1. POST /api/video/upload
Upload video for analysis

**Request:**
```bash
curl -X POST "https://adas-api.aiotlab.edu.vn/api/video/upload" \
  -F "file=@video.mp4" \
  -F "video_type=dashcam" \
  -F "device=cpu"
```

**Parameters:**
- `file`: Video file (mp4, avi, mov, mkv)
- `video_type`: `dashcam` hoặc `in_cabin`
- `device`: `cpu` hoặc `cuda`

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "Video uploaded successfully. Processing started."
}
```

---

### 2. GET /api/video/result/{job_id}
Check processing status và get results

**Request:**
```bash
curl "https://adas-api.aiotlab.edu.vn/api/video/result/{job_id}"
```

**Response (Processing):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "created_at": "2025-12-21T23:22:36",
  "updated_at": "2025-12-21T23:22:40"
}
```

**Response (Completed):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result_video_url": "/api/video/download/{job_id}/result.mp4",
  "events": [...],
  "stats": {...},
  "created_at": "2025-12-21T23:22:36",
  "updated_at": "2025-12-21T23:25:10"
}
```

---

### 3. GET /api/video/download/{job_id}/{filename}
Download processed video

**Request:**
```bash
curl -O "https://adas-api.aiotlab.edu.vn/api/video/download/{job_id}/result.mp4"
```

**Response:** Video file MP4

---

## 📊 Video Types Supported

### Dashcam (video_type="dashcam")
Phân tích video từ camera trước xe:
- ✅ Curved lane detection (phát hiện làn đường cong)
- ✅ Object detection (xe, người, xe máy)
- ✅ Distance estimation (ước tính khoảng cách)
- ✅ Lane departure warning (cảnh báo lệch làn)
- ✅ Forward collision warning (cảnh báo va chạm)
- ✅ Traffic sign recognition (biển báo)

### In-Cabin (video_type="in_cabin")
Phân tích video giám sát tài xế:
- ✅ Face detection (phát hiện khuôn mặt)
- ✅ Drowsiness detection (phát hiện buồn ngủ)
- ✅ Eye closure detection (EAR - Eye Aspect Ratio)
- ✅ Yawn detection (MAR - Mouth Aspect Ratio)
- ✅ Head pose estimation (góc nghiêng đầu)

---

## ⚠️ QUAN TRỌNG: Models Chưa Có!

**HIỆN TẠI THIẾU:**
```
backend/models/
  └── yolo11n.pt  ❌ CHƯA CÓ
```

**PHẢI TẢI MODEL TRƯỚC KHI DÙNG:**

### Option 1: Tự động tải (Recommended)
Ultralytics sẽ tự động tải model lần đầu chạy:
```python
# Trong object_detector_v11.py sẽ tự tải
from ultralytics import YOLO
model = YOLO('yolo11n.pt')  # Auto download nếu chưa có
```

### Option 2: Tải thủ công
```bash
# Tải YOLOv11 nano model
curl -L "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt" \
  -o backend/models/yolo11n.pt
```

### Option 3: Python script
```python
from ultralytics import YOLO

# Download model
model = YOLO('yolo11n.pt')
print("Model downloaded successfully!")
```

---

## 🧪 Test API

### 1. Mở Swagger UI
```
https://adas-api.aiotlab.edu.vn/docs
```

### 2. Test Upload
- Click **POST /api/video/upload**
- Click **Try it out**
- Upload file video test
- Chọn `video_type`: dashcam
- Execute

### 3. Check Result
- Copy `job_id` từ response
- Click **GET /api/video/result/{job_id}**
- Paste job_id
- Execute
- Poll mỗi 5-10s cho đến khi `status = "completed"`

### 4. Download Video
- Click **GET /api/video/download/{job_id}/{filename}**
- Paste job_id và filename: `result.mp4`
- Execute

---

## 📝 Full Example

```bash
# 1. Upload video
RESPONSE=$(curl -X POST "https://adas-api.aiotlab.edu.vn/api/video/upload" \
  -F "file=@dashcam_test.mp4" \
  -F "video_type=dashcam" \
  -F "device=cpu")

# 2. Extract job_id
JOB_ID=$(echo $RESPONSE | jq -r '.job_id')
echo "Job ID: $JOB_ID"

# 3. Poll for result
while true; do
  STATUS=$(curl -s "https://adas-api.aiotlab.edu.vn/api/video/result/$JOB_ID" | jq -r '.status')
  echo "Status: $STATUS"
  
  if [ "$STATUS" == "completed" ]; then
    break
  fi
  
  sleep 10
done

# 4. Download result
curl -O "https://adas-api.aiotlab.edu.vn/api/video/download/$JOB_ID/result.mp4"
echo "Downloaded: result.mp4"
```

---

## ✅ Server Status

**Current State:**
- ✅ Server running on port 52000
- ✅ API endpoints ready
- ✅ Perception modules loaded
- ⚠️  YOLOv11 model will auto-download on first use
- ⚠️  MediaPipe models will auto-download on first use

**First Request:**
- Sẽ mất 1-2 phút để tải models lần đầu
- Các request sau sẽ nhanh hơn

---

**Ready to use! 🚀**
