# 📚 ADAS Backend API Documentation

> **Base URL:** `https://adas-api.aiotlab.edu.vn`  
> **Swagger UI:** [/docs](https://adas-api.aiotlab.edu.vn/docs)  
> **Version:** 3.0.2  
> **Cập nhật:** 01/03/2026  

---

## Mục Lục

| # | Nhóm | Mô tả | Dùng cho |
|---|------|-------|----------|
| 1 | [📱 Mobile API](#1--mobile-api) | Upload, status, download, history | App điện thoại |
| 2 | [🎬 Video API](#2--video-api) | Upload/xử lý video ADAS | Web FE |
| 3 | [🚗 Driver Monitor API](#3--driver-monitor-api) | Giám sát tài xế (in-cabin) | Web FE + Mobile |
| 4 | [📡 Video SSE](#4--video-sse-realtime) | Realtime progress qua SSE | Web FE |
| 5 | [📺 HLS Streaming](#5--hls-streaming-api) | Xem video realtime khi đang xử lý | Web FE |
| 6 | [🔐 Authentication](#6--authentication-api) | Đăng nhập Supabase JWT | Web FE + Mobile |
| 7 | [📊 Analytics](#7--analytics-api) | Biểu đồ, thống kê chuyến đi | Web FE |
| 8 | [🏢 Admin](#8--admin-dashboard-api) | Dashboard quản trị | Admin Panel |
| 9 | [🤖 AI Chat](#9--ai-chat-api) | Chat với AI assistant | Web FE |
| 10 | [📂 Dataset](#10--dataset-api) | Quản lý dataset video/ảnh | Web FE |
| 11 | [🎯 Detections](#11--detections-api) | Lưu/truy vấn kết quả phát hiện | Web FE |
| 12 | [🎥 Videos](#12--videos-management-api) | Quản lý video đã upload | Web FE |
| 13 | [☁️ Upload & Storage](#13--upload--storage-api) | Upload file, thông tin lưu trữ | Web FE |
| 14 | [🔧 System](#14--system-endpoints) | Health check, logs, debug | DevOps |

---

## Quy Ước Chung

### Authentication
- Một số endpoint yêu cầu Supabase JWT token
- Header: `Authorization: Bearer {supabase_jwt_token}`
- Các API upload video **KHÔNG** yêu cầu auth (public)

### Status Codes
| Code | Ý nghĩa |
|------|---------|
| `200` | Thành công |
| `202` | Accepted (job đã vào hàng đợi) |
| `400` | Request không hợp lệ |
| `401` | Chưa xác thực / token hết hạn |
| `404` | Không tìm thấy |
| `413` | File quá lớn |
| `422` | Validation error |
| `500` | Lỗi server |

### Video Processing Flow
```
Upload → pending → processing → completed/failed
                       ↓
              GPU Worker tự động claim job
```

---

## 1. 📱 Mobile API

> **Prefix:** `/api/mobile`  
> **Dùng cho:** App điện thoại (Flutter/React Native)  
> **Lưu ý:** Các API mobile **cũng dùng được cho web FE**. Flow giống nhau: upload → poll status → download.

---

### `POST /api/mobile/video/upload`

**Upload video để phân tích ADAS (non-blocking)**

Trả về `job_id` ngay lập tức, AI xử lý ở background.

| Param | Loại | Kiểu | Bắt buộc | Mặc định | Mô tả |
|-------|------|------|----------|----------|-------|
| `file` | form-data | File | ✅ | — | Video MP4/MOV/AVI, tối đa 500MB |
| `video_type` | query | string | ❌ | `"dashcam"` | `"dashcam"` hoặc `"phone"` |
| `device` | query | string | ❌ | `"cuda"` | `"cuda"` hoặc `"cpu"` |

**Response `202 Accepted`:**
```json
{
  "success": true,
  "job_id": "9d507862-f5ec-4c7e-a617-153528f5377d",
  "status": "queued",
  "message": "Video đã được nhận và đang chờ xử lý",
  "estimated_time_seconds": 120,
  "created_at": "2026-03-01T12:00:00Z"
}
```

**Errors:**
| Code | Error Code | Khi nào |
|------|-----------|---------|
| `400` | `INVALID_FORMAT` | File không phải video hợp lệ |
| `413` | `FILE_TOO_LARGE` | File > 500MB |
| `500` | `PROCESSING_ERROR` | Lỗi khi ghi file |

**Frontend Example (JavaScript):**
```javascript
const formData = new FormData();
formData.append('file', videoFile);

const res = await fetch('https://adas-api.aiotlab.edu.vn/api/mobile/video/upload?video_type=dashcam', {
  method: 'POST',
  body: formData
});
const { job_id } = await res.json();
// Lưu job_id để poll status
```

---

### `GET /api/mobile/video/status/{job_id}`

**Kiểm tra trạng thái xử lý video**

Mobile app nên poll mỗi **3-5 giây**. Web FE dùng SSE thì không cần poll.

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `job_id` | path | string | Job ID từ upload |

**Response khi đang xử lý:**
```json
{
  "success": true,
  "job_id": "9d507862-...",
  "status": "processing",
  "progress_percent": 45,
  "current_step": "Đang phát hiện phương tiện...",
  "eta_seconds": 60,
  "queue_position": null,
  "message": null,
  "started_at": "2026-03-01T12:00:00Z",
  "completed_at": null,
  "failed_at": null,
  "result": null,
  "error": null
}
```

**Response khi hoàn thành (`status == "completed"`):**
```json
{
  "success": true,
  "job_id": "9d507862-...",
  "status": "completed",
  "progress_percent": 100,
  "result": {
    "video_url": "https://adas-api.aiotlab.edu.vn/public/results/9d507862_result.mp4",
    "thumbnail_url": "https://adas-api.aiotlab.edu.vn/public/results/9d507862_thumb.jpg",
    "cars_detected": 15,
    "pedestrians_detected": 3,
    "lane_departures": 2,
    "warnings_count": 5,
    "safety_score": 82,
    "duration_seconds": 120.0,
    "events": [
      {
        "type": "lane_departure",
        "timestamp": "01:30",
        "severity": "warning",
        "description": "Xe lệch làn phải"
      }
    ]
  }
}
```

**Response khi thất bại (`status == "failed"`):**
```json
{
  "success": true,
  "job_id": "9d507862-...",
  "status": "failed",
  "error": {
    "code": "PROCESSING_ERROR",
    "message": "Không thể xử lý video: GPU memory overflow"
  }
}
```

**Frontend Polling Example:**
```javascript
const pollStatus = async (jobId) => {
  const interval = setInterval(async () => {
    const res = await fetch(`/api/mobile/video/status/${jobId}`);
    const data = await res.json();
    
    updateProgressBar(data.progress_percent);
    
    if (data.status === 'completed') {
      clearInterval(interval);
      showResult(data.result);
    } else if (data.status === 'failed') {
      clearInterval(interval);
      showError(data.error.message);
    }
  }, 3000); // Poll mỗi 3 giây
};
```

---

### `GET /api/mobile/video/download/{job_id}`

**Tải video kết quả đã xử lý**

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `job_id` | path | string | Job ID |

**Response:** Binary video file (`video/mp4`)  
**Headers:** `Content-Disposition: attachment; filename="adas_result_9d507862.mp4"`

**Errors:**
| Code | Khi nào |
|------|---------|
| `400` | Video chưa xử lý xong (`status != completed`) |
| `404` | Job không tồn tại hoặc file kết quả không có |

**Frontend Example:**
```javascript
// Cách 1: Download trực tiếp
window.open(`/api/mobile/video/download/${jobId}`);

// Cách 2: Dùng video_url từ status response
videoPlayer.src = result.video_url;
```

---

### `GET /api/mobile/video/history`

**Lấy lịch sử phân tích video**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `page` | query | int | `1` | Trang hiện tại (min: 1) |
| `limit` | query | int | `10` | Số items/trang (min: 1, max: 50) |

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "job_id": "9d507862-...",
      "status": "completed",
      "video_url": "https://adas-api.aiotlab.edu.vn/public/results/...",
      "thumbnail_url": "https://adas-api.aiotlab.edu.vn/public/results/..._thumb.jpg",
      "safety_score": 85,
      "created_at": "2026-03-01T12:00:00Z",
      "completed_at": "2026-03-01T12:02:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 10,
    "total": 25,
    "total_pages": 3
  }
}
```

---

### `GET /api/mobile/health`

**Health check cho mobile API**

**Response:**
```json
{
  "status": "healthy",
  "service": "ADAS Mobile API",
  "version": "1.0.0",
  "endpoints": [
    "POST /api/mobile/video/upload",
    "GET /api/mobile/video/status/{job_id}",
    "GET /api/mobile/video/download/{job_id}",
    "GET /api/mobile/video/history"
  ]
}
```

---

## 2. 🎬 Video API

> **Prefix:** `/api/video`  
> **Dùng cho:** Web Frontend — upload, xem kết quả, download video ADAS

---

### `POST /api/video/upload`

**Upload video để phân tích ADAS (async)**

| Param | Loại | Kiểu | Bắt buộc | Mặc định | Mô tả |
|-------|------|------|----------|----------|-------|
| `file` | form-data | File | ✅ | — | Video MP4/AVI/MOV, tối đa 500MB |
| `video_type` | query | string | ❌ | `"dashcam"` | `"dashcam"` (camera hành trình) hoặc `"in_cabin"` (camera trong xe) |
| `device` | query | string | ❌ | `"cuda"` | `"cpu"` hoặc `"cuda"` |

> ⚠️ **`video_type` quan trọng:**
> - `"dashcam"` → chạy pipeline ADAS: lane detection, object detection, distance estimation, collision warning
> - `"in_cabin"` → chạy pipeline Driver Monitor: face mesh, drowsiness, phone detection, seatbelt

**Response `200`:** (schema: `VideoJobResponse`)
```json
{
  "id": 1,
  "job_id": "9d507862-f5ec-4c7e-a617-153528f5377d",
  "video_filename": "project_video.mp4",
  "video_path": "/storage/raw/9d507862.../project_video.mp4",
  "video_size_mb": 45.2,
  "duration_seconds": null,
  "fps": null,
  "resolution": null,
  "status": "pending",
  "progress_percent": 0,
  "result_path": null,
  "error_message": null,
  "processing_time_seconds": null,
  "trip_id": null,
  "created_at": "2026-03-01T12:00:00Z",
  "updated_at": "2026-03-01T12:00:00Z",
  "started_at": null,
  "completed_at": null,
  "video_url": null,
  "full_result_video_url": null
}
```

---

### `POST /api/video/upload-sync`

**Upload VÀ xử lý ĐỒNG BỘ (blocking — chờ GPU xong mới trả kết quả)**

> ⏱️ Thời gian xử lý:
> - 10s video → ~10-15s
> - 30s video → ~25-35s
> - 60s video → ~50-70s

| Param | Loại | Kiểu | Bắt buộc | Mặc định | Mô tả |
|-------|------|------|----------|----------|-------|
| `file` | form-data | File | ✅ | — | Tối đa **200MB** (nhỏ hơn async) |
| `video_type` | query | string | ❌ | `"dashcam"` | `"dashcam"` hoặc `"in_cabin"` |

**Response `200`:**
```json
{
  "job_id": "9d507862-...",
  "status": "completed",
  "video_url": "https://adas-api.aiotlab.edu.vn/public/results/9d507862.../result.mp4",
  "full_result_video_url": "https://adas-api.aiotlab.edu.vn/public/results/9d507862.../result.mp4",
  "processing_time_seconds": 35,
  "frames_processed": 900,
  "events_count": 12,
  "message": "Video analyzed successfully in 35s"
}
```

---

### `POST /api/video/analyze`

**Retry job đã failed (đẩy lại vào hàng đợi)**

> ⚠️ **Không cần cho upload mới** — worker tự động claim. Chỉ dùng khi job bị fail và muốn thử lại.

**Request body `application/json`:**
```json
{
  "job_id": "9d507862-..."
}
```

**Response:**
```json
{
  "message": "Job reset to pending - workers will claim it automatically",
  "job_id": "9d507862-...",
  "status": "pending"
}
```

---

### `GET /api/video/progress/{job_id}`

**Lấy tiến trình xử lý (polling endpoint, hỗ trợ HLS)**

**Response:**
```json
{
  "job_id": "9d507862-...",
  "status": "processing",
  "progress_percent": 50,
  "processing_time_seconds": 30,
  "hls_ready": true,
  "hls_playlist_url": "https://adas-api.aiotlab.edu.vn/api/hls/9d507862.../playlist.m3u8",
  "segments_generated": 15,
  "total_segments": 30,
  "result_path": null
}
```

---

### `GET /api/video/result/{job_id}`

**Lấy kết quả phân tích (sau khi completed)**

**Response:** Schema `VideoJobResponse` (giống upload response, nhưng có đầy đủ `result_path`, `processing_time_seconds`, `completed_at`, v.v.)

---

### `GET /api/video/download/{job_id}/{filename}`

**Download video đã xử lý**

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `job_id` | path | string | Job ID |
| `filename` | path | string | Tên file (bị ignore, luôn trả `result.mp4`) |

**Response:** Binary `video/mp4`

---

### `GET /api/video/list`

**Liệt kê tất cả video đã upload**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `limit` | query | int | `10` | Số kết quả tối đa |
| `offset` | query | int | `0` | Bỏ qua N kết quả |
| `status` | query | string | — | Filter: `"pending"`, `"processing"`, `"completed"`, `"failed"` |

**Response:**
```json
{
  "videos": [
    {
      "id": 1,
      "job_id": "9d507862-...",
      "video_filename": "video.mp4",
      "status": "completed",
      "progress_percent": 100,
      "video_size_mb": 45.2,
      "created_at": "2026-03-01T12:00:00Z",
      "completed_at": "2026-03-01T12:02:00Z"
    }
  ],
  "total": 25,
  "limit": 10,
  "offset": 0
}
```

---

### `GET /api/video/sample/{job_id}/{filename}`

**Download video gốc (chưa xử lý)**

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `job_id` | path | string | Job ID |
| `filename` | path | string | Tên file gốc |

**Response:** Binary `video/mp4`

---

### `GET /api/video/sample`

**Lấy video mẫu demo**

**Response:** Binary `video/mp4` (file mẫu `sample_video.mp4`)

---

### `DELETE /api/video/job/{job_id}`

**Xóa job và tất cả files liên quan**

**Response:**
```json
{
  "message": "Job 9d507862-... deleted successfully"
}
```

---

### `GET /api/video/health`

**Health check**

**Response:**
```json
{
  "status": "healthy",
  "service": "ADAS Video Analysis API",
  "version": "1.0.0"
}
```

---

## 3. 🚗 Driver Monitor API

> **Prefix:** `/api`  
> **Dùng cho:** Phân tích video in-cabin (giám sát tài xế)
> 
> **Tính năng phân tích:**
> - MediaPipe Face Mesh (468 landmarks)
> - EAR (Eye Aspect Ratio) — phát hiện mắt nhắm
> - Phát hiện ngủ gật, ngáp
> - Phát hiện dùng điện thoại
> - Phát hiện uống nước, hút thuốc
> - Head Pose — phát hiện không nhìn đường
> - Seatbelt Detection — phát hiện dây an toàn
> - Attention Score (0-100)

---

### `POST /api/driver-monitor/analyze`

**Upload video giám sát tài xế**

| Param | Loại | Kiểu | Bắt buộc | Mặc định | Mô tả |
|-------|------|------|----------|----------|-------|
| `file` | form-data | File | ✅ | — | Video MP4/AVI/MOV, tối đa 500MB |
| `camera_id` | form-data | string | ❌ | `"in_cabin_camera"` | Tên camera |
| `device` | form-data | string | ❌ | `"cuda"` | `"cpu"` hoặc `"cuda"` |

**Response `200`:** Schema `VideoJobResponse` + thêm:
```json
{
  "id": 1,
  "job_id": "97924c1d-...",
  "status": "pending",
  "download_url": "/api/download/97924c1d-...",
  "result_url": "/api/video/result/97924c1d-..."
}
```

> 💡 **Sau khi completed**, dùng `GET /api/download/{job_id}` để tải hoặc `GET /api/mobile/video/status/{job_id}` để check trạng thái.

---

### `GET /api/download/{job_id}`

**Download video driver monitoring đã xử lý (có annotations)**

Video kết quả bao gồm:
- Facial landmarks (468 điểm)
- EAR/MAR metrics overlay
- Head pose angles
- Vietnamese alerts (cảnh báo tiếng Việt)
- Detected objects (điện thoại, chai nước)
- Seatbelt status
- Attention score dashboard

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `job_id` | path | string | Job ID từ `/analyze` |

**Response:** Binary `video/mp4`  
**Headers:** `Content-Disposition: attachment; filename="driver_monitoring_97924c1d.mp4"`

---

### `POST /api/driver-status`

**Lưu trạng thái tài xế realtime**

**Request body `application/json`:**
```json
{
  "driver_id": "driver_001",
  "fatigue_level": 30,
  "distraction_level": 10,
  "eyes_closed": false,
  "head_pose": {"yaw": 5.2, "pitch": -3.1, "roll": 1.0},
  "timestamp": "2026-03-01T12:00:00Z",
  "camera_id": "in_cabin_camera"
}
```

| Field | Kiểu | Bắt buộc | Mô tả |
|-------|------|----------|-------|
| `driver_id` | string | ❌ | ID tài xế |
| `fatigue_level` | int (0-100) | ✅ | Mức mệt mỏi |
| `distraction_level` | int (0-100) | ✅ | Mức mất tập trung |
| `eyes_closed` | bool | ✅ | Mắt đang nhắm? |
| `head_pose` | object | ❌ | `{yaw, pitch, roll}` |
| `timestamp` | string (ISO) | ✅ | Thời gian |
| `camera_id` | string | ❌ | ID camera |

**Response:**
```json
{
  "success": true,
  "alert_triggered": true,
  "recommendations": ["High fatigue detected - take an immediate break"]
}
```

---

### `GET /api/driver-status`

**Lấy trạng thái tài xế hiện tại**

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `driver_id` | query | string | Lọc theo tài xế (optional) |
| `camera_id` | query | string | Lọc theo camera (optional) |

**Response:**
```json
{
  "success": true,
  "status": {
    "fatigue_level": 30,
    "distraction_level": 10,
    "eyes_closed": false,
    "last_updated": "2026-03-01T12:00:00",
    "alert_status": "normal"
  }
}
```

---

### `GET /api/driver-status/history`

**Lấy lịch sử trạng thái tài xế**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `driver_id` | query | string | — | Lọc theo tài xế |
| `from_date` | query | string | — | Ngày bắt đầu (ISO) |
| `to_date` | query | string | — | Ngày kết thúc (ISO) |
| `limit` | query | int | `100` | Số record tối đa |

**Response:**
```json
{
  "success": true,
  "history": [
    {
      "fatigue_level": 30,
      "distraction_level": 10,
      "eyes_closed": false,
      "timestamp": "2026-03-01T12:00:00",
      "alert_status": "normal"
    }
  ]
}
```

---

### `GET /api/samples/list`

**Liệt kê video mẫu driver monitoring (Gallery)**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `limit` | query | int | `20` | Số video tối đa |
| `offset` | query | int | `0` | Skip N kết quả |

**Response:**
```json
{
  "success": true,
  "samples": [...],
  "total": 5
}
```

---

## 4. 📡 Video SSE (Realtime)

> **Prefix:** `/api/video`  
> **Dùng cho:** Web FE nhận cập nhật realtime (thay vì polling)

---

### `GET /api/video/stream/{job_id}`

**SSE stream realtime tiến trình xử lý video**

Client nhận partial results trong **1-3 giây** sau upload.

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `job_id` | path | string | Job ID từ upload |

**Content-Type:** `text/event-stream`

**SSE Events:**

| Event Type | Khi nào | Data |
|------------|---------|------|
| `progress` | Mỗi 2s hoặc khi thay đổi | `{job_id, status, progress, event_count, partial_events}` |
| `complete` | Xử lý xong | `{job_id, status, progress: 100, events, processing_time}` |
| `error` | Có lỗi | `{error: "..."}` |
| `timeout` | Sau 3 phút | `{error: "Stream timeout after 3 minutes"}` |

**Frontend Example:**
```javascript
const eventSource = new EventSource(`/api/video/stream/${jobId}`);

eventSource.addEventListener('progress', (e) => {
  const data = JSON.parse(e.data);
  console.log('Progress:', data.progress, '%');
  console.log('Events detected:', data.event_count);
  
  // Hiển thị partial events lên UI
  if (data.partial_events) {
    data.partial_events.forEach(event => addEventToUI(event));
  }
});

eventSource.addEventListener('complete', (e) => {
  const data = JSON.parse(e.data);
  console.log('Done! Total events:', data.events.length);
  showResultVideo(data.result_path);
  eventSource.close();
});

eventSource.addEventListener('error', (e) => {
  console.error('Error:', e.data);
  eventSource.close();
});
```

---

### `GET /api/video/stream/{job_id}/events`

**Lấy partial events (thay thế SSE nếu client không hỗ trợ)**

Poll mỗi **2-3 giây**.

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `job_id` | path | string | — | Job ID |
| `limit` | query | int | `10` | Số events trả về |
| `offset` | query | int | `0` | Offset phân trang |

**Response:**
```json
{
  "job_id": "9d507862-...",
  "status": "processing",
  "progress": 45,
  "event_count": 20,
  "total_events": 20,
  "events": [
    {
      "type": "lane_departure",
      "level": "warning",
      "time": 15.5,
      "frame": 465,
      "description": "Xe lệch làn phải"
    }
  ]
}
```

---

## 5. 📺 HLS Streaming API

> **Prefix:** `/api/hls`  
> **Dùng cho:** Xem video realtime ngay khi đang xử lý (không cần đợi xong)

---

### `GET /api/hls/{job_id}/status`

**Kiểm tra nhanh trạng thái HLS (nhẹ, poll ~500ms)**

**Response:**
```json
{
  "ready": true,
  "segments_available": 15,
  "total_segments": 30,
  "playlist_url": "https://adas-api.aiotlab.edu.vn/api/hls/9d507862.../playlist.m3u8",
  "status": "processing"
}
```

---

### `GET /api/hls/{job_id}/playlist.m3u8`

**Phục vụ HLS playlist (M3U8)**

Dùng trực tiếp trong `<video>` tag hoặc player như HLS.js.

**Response:** `application/vnd.apple.mpegurl`  
**Cache:** `no-cache, no-store, must-revalidate` (playlist luôn thay đổi khi đang xử lý)

**Frontend Example:**
```javascript
import Hls from 'hls.js';

const video = document.querySelector('video');
const hls = new Hls();
hls.loadSource(`/api/hls/${jobId}/playlist.m3u8`);
hls.attachMedia(video);
video.play();
```

---

### `GET /api/hls/{job_id}/{segment_filename}`

**Phục vụ HLS segment (.ts)**

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `job_id` | path | string | Job ID |
| `segment_filename` | path | string | VD: `segment_00000.ts` |

**Response:** `video/mp2t`  
**Cache:** `public, max-age=31536000` (segment không đổi, cache forever)

---

## 6. 🔐 Authentication API

> **Prefix:** `/api/auth`  
> **Auth Provider:** Supabase Auth (JWT)  
> **Hybrid ID:** Supabase UUID ↔ Database integer ID

---

### `GET /api/auth/me`

**Lấy thông tin user đang đăng nhập** 🔒 **Yêu cầu auth**

**Headers:** `Authorization: Bearer {supabase_jwt_token}`

**Response:**
```json
{
  "success": true,
  "user": {
    "id": 123,
    "auth_id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "role": "admin"
  }
}
```

| Field | Kiểu | Mô tả |
|-------|------|-------|
| `id` | int | Integer ID từ database (dùng cho FK, legacy) |
| `auth_id` | string (UUID) | UUID từ Supabase Auth |
| `email` | string | Email người dùng |
| `role` | string | Vai trò: `"admin"`, `"driver"`, `"fleet_manager"` |

**Errors:**
| Code | Khi nào |
|------|---------|
| `401` | Token không hợp lệ / hết hạn |
| `503` | Database không khả dụng |

---

### `GET /api/auth/status`

**Kiểm tra trạng thái auth (không bắn 401)**

**Headers:** `Authorization: Bearer {token}` *(optional)*

**Response (đã đăng nhập):**
```json
{
  "authenticated": true,
  "user": {"id": 123, "auth_id": "uuid-...", "email": "user@example.com", "role": "admin"}
}
```

**Response (chưa đăng nhập):**
```json
{
  "authenticated": false,
  "user": null
}
```

> 💡 Dùng endpoint này để check auth mà không gây redirect / 401

---

### `GET /api/auth/protected`

**Endpoint mẫu minh họa protected route** 🔒 **Yêu cầu auth**

**Response:**
```json
{
  "message": "Hello user@example.com! This is a protected endpoint.",
  "hybrid_id": {
    "database_id": 123,
    "supabase_auth_id": "550e8400-..."
  },
  "user_info": {"id": 123, "auth_id": "uuid", "email": "...", "role": "admin"},
  "metadata": {"issued_at": 1737000000, "expires_at": 1737003600}
}
```

---

## 7. 📊 Analytics API

> **Prefix:** `/api/analytics`  
> **Dùng cho:** Biểu đồ và thống kê trên dashboard

---

### `GET /api/analytics/speed-over-time`

**Dữ liệu tốc độ theo thời gian (Line Chart)**

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `trip_id` | query | int | Trip ID (optional, mặc định = trip gần nhất) |

**Response:**
```json
{
  "labels": ["0:00", "0:15", "0:30", "0:45", "1:00"],
  "data": [0, 45, 60, 70, 68],
  "unit": "km/h",
  "trip_id": 123,
  "chart_title": "Speed Over Time"
}
```

---

### `GET /api/analytics/fatigue-over-time`

**Mức độ mệt mỏi theo thời gian (Line Chart)**

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `trip_id` | query | int | Trip ID (optional) |

**Response:**
```json
{
  "labels": ["0:00", "0:30", "1:00", "1:30", "2:00"],
  "data": [10, 15, 23, 30, 40],
  "unit": "%",
  "trip_id": 123,
  "chart_title": "Fatigue Level Over Time"
}
```

---

### `GET /api/analytics/safety-score-comparison`

**So sánh điểm an toàn theo ngày (Bar Chart)**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `days` | query | int | `7` | Số ngày so sánh |

**Response:**
```json
{
  "labels": ["Today", "Yesterday", "3 Days Ago", "1 Week Ago"],
  "data": [85, 78, 82, 75],
  "colors": ["#10b981", "#f59e0b", "#10b981", "#ef4444"],
  "chart_title": "Safety Score Comparison"
}
```

---

### `GET /api/analytics/recommendations`

**Gợi ý an toàn dựa trên dữ liệu chuyến đi**

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `trip_id` | query | int | Trip ID (optional, mặc định = 3 trips gần nhất) |

**Response:**
```json
{
  "recommendations": [
    {
      "title": "Increase Safety Distance",
      "description": "You have 2 collision warnings. Please increase distance from the vehicle ahead.",
      "severity": "warning",
      "icon": "⚠️"
    },
    {
      "title": "Take a Break",
      "description": "Fatigue level exceeded 60% during your trip. Consider resting.",
      "severity": "critical",
      "icon": "🛑"
    }
  ],
  "trip_count": 3,
  "total_alerts": 15,
  "total_critical": 2
}
```

---

### `GET /api/analytics/summary`

**Tổng quan phân tích (dashboard stats card)**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `period` | query | string | `"today"` | `"today"`, `"week"`, `"month"`, `"all"` |

**Response:**
```json
{
  "period": "today",
  "total_trips": 25,
  "total_distance": 450.5,
  "avg_safety_score": 82.3,
  "total_alerts": 15,
  "total_critical_alerts": 2,
  "avg_speed": 55.0
}
```

---

## 8. 🏢 Admin Dashboard API

> **Prefix:** `/admin`  
> **Dùng cho:** Trang quản trị hệ thống

---

### `GET /admin/overview`

**Thống kê tổng quan**

**Response (schema: `OverviewStats`):**
```json
{
  "total_users": 50,
  "total_videos": 200,
  "total_processed": 180,
  "active_jobs": 5,
  "system_status": "operational"
}
```

---

### `GET /admin/statistics`

**Thống kê chi tiết cho biểu đồ (Chart.js Ready)**

**Response (schema: `ProcessingStats`):**
```json
{
  "daily_uploads": {
    "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "datasets": [
      {
        "label": "Videos Uploaded",
        "data": [5, 3, 7, 2, 8, 4, 6],
        "borderColor": "#6366f1"
      }
    ]
  },
  "status_distribution": {
    "labels": ["Completed", "Failed", "Processing", "Pending"],
    "datasets": [
      {
        "label": "Job Status",
        "data": [120, 10, 5, 15],
        "backgroundColor": ["#10b981", "#ef4444", "#f59e0b", "#6366f1"]
      }
    ]
  }
}
```

---

### `GET /admin/dashboard/cards`

**Dữ liệu cho 4 thẻ info trên đầu dashboard**

**Response:**
```json
{
  "system_status": "Trực tuyến",
  "active_cameras": 3,
  "total_detections": 5000,
  "today_alerts": 12
}
```

---

### `GET /admin/dashboard/charts/detection-trend`

**Chart 1: Xu hướng phát hiện realtime (Line) — 30 phút, mỗi 5 phút**

**Response (Chart.js ready):**
```json
{
  "labels": ["10:00", "10:05", "10:10", "10:15", "10:20", "10:25"],
  "datasets": [
    {"label": "Xe cộ", "data": [5, 8, 12, 6, 10, 7], "borderColor": "#36A2EB"},
    {"label": "Người đi bộ", "data": [2, 3, 1, 4, 2, 3], "borderColor": "#4BC0C0"}
  ]
}
```

---

### `GET /admin/dashboard/charts/detection-accuracy`

**Chart 2: Độ chính xác phát hiện 7 ngày (Line)**

**Response:**
```json
{
  "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
  "datasets": [
    {"label": "Độ chính xác (%)", "data": [85.2, 92.1, 88.5, 90.3, 87.6, 91.0, 89.4]}
  ]
}
```

---

### `GET /admin/dashboard/charts/detection-distribution`

**Chart 3: Phân bố phát hiện (Pie Chart)**

**Response:**
```json
{
  "labels": ["Xe", "Người", "Chu kỳ", "Khác"],
  "datasets": [
    {"data": [500, 200, 50, 30], "backgroundColor": ["#36A2EB", "#9966FF", "#FF9F40", "#4BC0C0"]}
  ]
}
```

---

### `GET /admin/dashboard/charts/system-performance`

**Chart 4: Hiệu suất xử lý FPS (Line)**

**Response:**
```json
{
  "labels": ["0", "1", "2", "3", "4", "5", "6"],
  "datasets": [
    {"label": "Hiệu suất", "data": [25, 28, 30, 27, 29, 31, 28]}
  ]
}
```

---

## 9. 🤖 AI Chat API

> **Prefix:** `/api/ai-chat`  
> **Dùng cho:** Chat assistant trên web (keyword-based)

---

### `POST /api/ai-chat`

**Gửi tin nhắn cho AI assistant**

**Request body `application/json`:**
```json
{
  "message": "ADAS là gì?",
  "session_id": "optional-session-uuid",
  "context": null
}
```

| Field | Kiểu | Bắt buộc | Mô tả |
|-------|------|----------|-------|
| `message` | string | ✅ | Tin nhắn người dùng |
| `session_id` | string | ❌ | Session ID để giữ context hội thoại |
| `context` | any | ❌ | Context bổ sung |

**Response:**
```json
{
  "success": true,
  "message": "ADAS là gì?",
  "response": "ADAS (Advanced Driver Assistance Systems) là hệ thống hỗ trợ lái xe tiên tiến...",
  "timestamp": "2026-03-01T12:00:00Z",
  "session_id": "a1b2c3d4-..."
}
```

---

### `GET /api/ai-chat/history`

**Lấy lịch sử chat**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `session_id` | query | string | — | Lọc theo session |
| `limit` | query | int | `50` | Số tin nhắn tối đa |

**Response:**
```json
{
  "success": true,
  "messages": [
    {"id": 1, "session_id": "uuid", "role": "user", "content": "ADAS là gì?", "timestamp": "..."},
    {"id": 2, "session_id": "uuid", "role": "assistant", "content": "ADAS là...", "timestamp": "..."}
  ]
}
```

---

### `DELETE /api/ai-chat/session/{id}`

**Xóa một chat session**

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `id` | path | string | Session ID cần xóa |

**Response:**
```json
{
  "success": true,
  "message": "Deleted 5 messages from session 'a1b2c3d4-...'"
}
```

---

## 10. 📂 Dataset API

> **Prefix:** `/api/dataset`  
> **Dùng cho:** Quản lý dataset video/ảnh

---

### `GET /api/dataset`

**Liệt kê datasets**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `limit` | query | int | `50` | Số items/trang |
| `page` | query | int | `1` | Trang |
| `status` | query | string | — | `"uploaded"`, `"processing"`, `"ready"`, `"error"` |
| `type` | query | string | — | `"video"`, `"image"` |

**Response:**
```json
{
  "success": true,
  "data": [...],
  "total": 25,
  "page": 1,
  "limit": 50
}
```

---

### `POST /api/dataset`

**Upload file vào dataset**

| Param | Loại | Kiểu | Bắt buộc | Mặc định | Mô tả |
|-------|------|------|----------|----------|-------|
| `file` | form-data | File | ✅ | — | Video hoặc ảnh |
| `description` | form-data | string | ❌ | — | Mô tả |
| `type` | form-data | string | ❌ | `"video"` | `"video"` hoặc `"image"` |
| `tags` | form-data | string | ❌ | — | Tags phân cách bằng dấu phẩy |

**Response:**
```json
{
  "success": true,
  "message": "File uploaded successfully",
  "data": {
    "id": 1,
    "filename": "test.mp4",
    "file_path": "...",
    "file_size_mb": 45.2,
    "uploaded_at": "2026-03-01T12:00:00Z"
  }
}
```

---

### `GET /api/dataset/{id}`

**Lấy chi tiết dataset item**

**Response:**
```json
{"success": true, "data": {"id": 1, "filename": "...", "detections_count": 20}}
```

---

### `DELETE /api/dataset/{id}`

**Xóa dataset item**

**Response:**
```json
{"success": true, "message": "Dataset item 'test.mp4' deleted successfully"}
```

---

## 11. 🎯 Detections API

> **Prefix:** `/api/detections`  
> **Dùng cho:** Lưu/truy vấn kết quả phát hiện đối tượng

---

### `POST /api/detections/save`

**Lưu kết quả phát hiện từ video/webcam**

**Request body `application/json`:**
```json
{
  "video_id": 1,
  "camera_id": "cam_01",
  "detections": [
    {
      "class_name": "car",
      "class_id": 2,
      "confidence": 0.95,
      "bbox": [100, 200, 300, 400],
      "timestamp": "00:01:30"
    }
  ],
  "metadata": {"fps": 30}
}
```

**Response:**
```json
{"success": true, "detection_id": 1, "message": "Saved 5 detections successfully"}
```

---

### `GET /api/detections/recent`

**Lấy detections gần đây**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `limit` | query | int | `20` | Số kết quả |
| `camera_id` | query | string | — | Lọc theo camera |
| `class_name` | query | string | — | Lọc theo class |

**Response:**
```json
{
  "success": true,
  "detections": [
    {"id": 1, "class_name": "car", "confidence": 0.95, "timestamp": "...", "camera_id": "cam_01", "bbox": [100, 200, 300, 400]}
  ]
}
```

---

### `GET /api/detections/stats`

**Thống kê detections cho dashboard**

**Response:**
```json
{
  "success": true,
  "total_detections": 500,
  "classes": [
    {"class_name": "car", "count": 200, "avg_confidence": 0.92},
    {"class_name": "person", "count": 150, "avg_confidence": 0.88}
  ],
  "by_camera": [
    {"camera_id": "cam_01", "count": 300},
    {"camera_id": "cam_02", "count": 200}
  ]
}
```

---

## 12. 🎥 Videos Management API

> **Prefix:** `/api/videos` + `/api/video`  
> **Dùng cho:** Quản lý video đã upload (CRUD)

---

### `GET /api/videos/list`

**Liệt kê tất cả video**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `limit` | query | int | `50` | Số video/trang |
| `page` | query | int | `1` | Trang |
| `status` | query | string | — | `"uploaded"`, `"processing"`, `"completed"` |
| `processed` | query | bool | — | Đã xử lý chưa |

**Response:**
```json
{
  "success": true,
  "videos": [
    {
      "id": 1,
      "filename": "video.mp4",
      "thumbnail_url": "...",
      "duration_seconds": 120,
      "uploaded_at": "...",
      "processed": true,
      "detections_count": 50,
      "status": "completed"
    }
  ],
  "total": 10
}
```

---

### `GET /api/videos/{id}`

**Chi tiết video kèm detections + events**

**Response:**
```json
{
  "success": true,
  "video": {
    "id": 1,
    "filename": "video.mp4",
    "detections": [...],
    "events": [...]
  }
}
```

---

### `DELETE /api/videos/{id}`

**Xóa video + detections liên quan**

**Response:**
```json
{"success": true, "message": "Video 'video.mp4' deleted successfully"}
```

---

### `GET /api/videos/{id}/detections`

**Lấy detections timeline cho video**

| Param | Loại | Kiểu | Mô tả |
|-------|------|------|-------|
| `id` | path | int | Video ID |
| `class_name` | query | string | Lọc theo class (optional) |
| `min_confidence` | query | float | Confidence tối thiểu (optional) |

**Response:**
```json
{
  "success": true,
  "detections": [
    {
      "frame_number": 0,
      "timestamp_seconds": 0.0,
      "detections": [
        {"class_name": "car", "confidence": 0.95, "bbox": [100, 200, 300, 400]}
      ]
    }
  ]
}
```

---

### `GET /api/video/{id}/process-status`

**Trạng thái xử lý video (polling khi processing)**

**Response:**
```json
{
  "success": true,
  "progress": 45,
  "current_frame": 450,
  "total_frames": 1000,
  "status": "processing",
  "detections_count": 20,
  "estimated_time_remaining_seconds": 30
}
```

---

## 13. ☁️ Upload & Storage API

> **Prefix:** `/api/upload`, `/api/storage`  
> **Dùng cho:** Upload ảnh, batch upload, quản lý dung lượng

---

### `POST /api/upload/image`

**Upload một ảnh đơn**

| Param | Loại | Kiểu | Bắt buộc | Mô tả |
|-------|------|------|----------|-------|
| `file` | form-data | File | ✅ | Ảnh JPG/PNG, tối đa 50MB |

**Response:**
```json
{
  "success": true,
  "file_path": "backend/storage/images/2026/03/photo_20260301_120000.jpg",
  "url": "https://adas-api.aiotlab.edu.vn/api/files/images/2026/03/photo_20260301_120000.jpg",
  "file_size_mb": 2.5,
  "uploaded_at": "2026-03-01T12:00:00"
}
```

---

### `POST /api/upload/batch`

**Upload nhiều file cùng lúc**

| Param | Loại | Kiểu | Bắt buộc | Mô tả |
|-------|------|------|----------|-------|
| `files` | form-data | File[] | ✅ | Mảng files, max 500MB/file |

**Response:**
```json
{
  "success": true,
  "uploaded": [
    {"filename": "photo1.jpg", "url": "...", "file_path": "...", "file_size_mb": 2.5}
  ],
  "failed": [
    {"filename": "huge.zip", "error": "File too large (>500MB)"}
  ],
  "total_uploaded": 3,
  "total_failed": 1
}
```

---

### `GET /api/storage/info`

**Thông tin dung lượng lưu trữ**

**Response:**
```json
{
  "success": true,
  "total_gb": 1000.0,
  "used_gb": 45.2,
  "available_gb": 954.8,
  "usage_percentage": 4.5,
  "files_count": 150,
  "videos_count": 150,
  "completed_count": 120,
  "processing_count": 5,
  "failed_count": 10,
  "pending_count": 15,
  "processing_gb": 0
}
```

---

### `DELETE /api/storage/cleanup`

**Dọn dẹp files cũ**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `days_old` | query | int | `90` | Xóa files cũ hơn N ngày |

**Response:**
```json
{
  "success": true,
  "message": "Deleted 15 files older than 90 days",
  "deleted_count": 15,
  "deleted_size_gb": 3.5,
  "remaining_count": 135
}
```

---

## 14. 🔧 System Endpoints

---

### `GET /`

**Root — Thông tin API**

### `GET /health`

**Health check với Cloudflare detection**

**Response:**
```json
{
  "status": "healthy",
  "server": "ADAS Backend",
  "cloudflare": true,
  "cf_ray": "abc123..."
}
```

### `GET /api/logs/recent`

**Lấy log gần đây**

| Param | Loại | Kiểu | Mặc định | Mô tả |
|-------|------|------|----------|-------|
| `lines` | query | int | `100` | Số dòng log |

### `GET /api/logs/stats`

**Thống kê file log**

### `GET /public/results/{filename}`

**Phục vụ video kết quả (public, hỗ trợ Range Request)**

> ⚠️ Không cần auth. Hỗ trợ HTTP 206 (partial content) cho streaming.

### `POST /debug/upload-test`

**Kiểm tra upload qua Cloudflare (debug, không xử lý)**

### `GET /ws/alerts/stats`

**Thống kê WebSocket connections**

### `GET /ws/video/stats`

**Thống kê WebSocket video connections**

---

## 📋 Bảng Tổng Hợp Response Schemas

### `VideoJobResponse`
| Field | Kiểu | Mô tả |
|-------|------|-------|
| `id` | int | DB ID |
| `job_id` | string/UUID | Job UUID |
| `video_filename` | string | Tên file gốc |
| `video_path` | string | Đường dẫn file gốc |
| `video_size_mb` | float? | Dung lượng (MB) |
| `duration_seconds` | int? | Thời lượng (giây) |
| `fps` | float? | FPS video |
| `resolution` | string? | VD: "1920x1080" |
| `status` | string | `pending` / `processing` / `completed` / `failed` |
| `progress_percent` | int | 0-100 |
| `result_path` | string? | Đường dẫn kết quả |
| `error_message` | string? | Lỗi (nếu failed) |
| `processing_time_seconds` | int? | Thời gian xử lý |
| `trip_id` | int? | ID chuyến đi |
| `created_at` | datetime | Thời gian tạo |
| `updated_at` | datetime | Thời gian cập nhật |
| `started_at` | datetime? | Bắt đầu xử lý |
| `completed_at` | datetime? | Hoàn thành xử lý |
| `video_url` | string? | URL xem video kết quả |
| `full_result_video_url` | string? | URL đầy đủ |

### `UploadResponse` (Mobile)
| Field | Kiểu | Mô tả |
|-------|------|-------|
| `success` | bool | |
| `job_id` | string | Job UUID |
| `status` | string | `"queued"` |
| `message` | string | Thông báo |
| `estimated_time_seconds` | int | Thời gian ước tính |
| `created_at` | datetime | |

### `StatusResponse` (Mobile)
| Field | Kiểu | Mô tả |
|-------|------|-------|
| `success` | bool | |
| `job_id` | string | |
| `status` | string | `pending`/`processing`/`completed`/`failed` |
| `progress_percent` | int | 0-100 |
| `current_step` | string? | Bước đang thực hiện |
| `eta_seconds` | int? | Thời gian còn lại |
| `queue_position` | int? | Vị trí trong hàng đợi |
| `message` | string? | |
| `started_at` | datetime? | |
| `completed_at` | datetime? | |
| `failed_at` | datetime? | |
| `result` | AnalysisResult? | Kết quả (khi completed) |
| `error` | ErrorDetail? | Lỗi (khi failed) |

### `AnalysisResult`
| Field | Kiểu | Mô tả |
|-------|------|-------|
| `video_url` | string? | URL video kết quả |
| `thumbnail_url` | string? | URL thumbnail |
| `cars_detected` | int | Số xe phát hiện |
| `pedestrians_detected` | int | Số người đi bộ |
| `lane_departures` | int | Số lần lệch làn |
| `warnings_count` | int | Số cảnh báo |
| `safety_score` | int | Điểm an toàn (0-100) |
| `duration_seconds` | float | Thời lượng video |
| `events` | array | Danh sách sự kiện |

---

## 🔄 Flow Tích Hợp Cho FE

### Flow 1: Upload Async + Poll (Mobile/Web)
```
1. POST /api/mobile/video/upload        → nhận job_id
2. GET  /api/mobile/video/status/{id}   → poll mỗi 3s
3. Khi status == "completed"            → lấy result.video_url
4. GET  /api/mobile/video/download/{id} → tải video (optional)
```

### Flow 2: Upload Async + SSE (Web - Recommended)
```
1. POST /api/video/upload               → nhận job_id
2. GET  /api/video/stream/{id}          → SSE stream
3. Nhận event "progress"                → cập nhật progress bar
4. Nhận event "complete"                → hiển thị kết quả
```

### Flow 3: Upload Sync (Quick Demo)
```
1. POST /api/video/upload-sync          → chờ, nhận kết quả ngay
   (Chỉ dùng cho video nhỏ < 200MB)
```

### Flow 4: Driver Monitoring
```
1. POST /api/driver-monitor/analyze     → nhận job_id
2. GET  /api/mobile/video/status/{id}   → poll (hoặc dùng SSE)
3. GET  /api/download/{id}              → tải video annotated
```

### Flow 5: HLS Live Preview
```
1. POST /api/video/upload               → nhận job_id
2. GET  /api/hls/{id}/status            → poll mỗi 500ms
3. Khi ready == true                    → gắn playlist vào HLS.js player
4. GET  /api/hls/{id}/playlist.m3u8     → stream live
```

---

> **Lưu ý cho FE Team:**
> - API Mobile (`/api/mobile/*`) **dùng được cho cả web** vì response schema clean hơn
> - Tất cả endpoint upload video đều **không cần auth** (public)
> - Dùng `video_type: "in_cabin"` cho camera trong xe, `"dashcam"` cho camera hành trình
> - Response chart data từ Admin/Analytics API đã format sẵn cho **Chart.js**
> - SSE endpoint tốt hơn polling cho web (giảm request, realtime hơn)

---

**Phát triển bởi:** ADAS Research Team — Bùi Văn Chương  
**Server:** Ubuntu Linux + NVIDIA A30 GPU + PostgreSQL  
**Domain:** `https://adas-api.aiotlab.edu.vn`
