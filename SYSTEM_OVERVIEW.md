# TỔNG QUAN HỆ THỐNG BACKEND ADAS

> **Tài liệu kỹ thuật chi tiết cho hệ thống Backend ADAS (Advanced Driver Assistance System)**  
> Phiên bản: 2.0.0  
> Ngày cập nhật: 27/12/2025

---

## 1. MỤC ĐÍCH VÀ PHẠM VI HỆ THỐNG

### 1.1 Vấn Đề Giải Quyết
Hệ thống backend ADAS cung cấp **API RESTful** và **WebSocket** để:
- Xử lý video dashcam và in-cabin với AI
- Phát hiện nguy hiểm: va chạm, lệch làn, mệt mỏi tài xế
- Nhận diện đối tượng: xe, người, biển báo giao thông
- Cảnh báo thời gian thực qua WebSocket
- Lưu trữ và phân tích dữ liệu chuyến đi

### 1.2 Người Dùng Mục Tiêu
- **Frontend Web/Mobile**: Giao diện người dùng cuối
- **Hệ thống IoT**: Camera dashcam, thiết bị giám sát
- **Nhà phát triển**: Tích hợp API vào ứng dụng của họ
- **Nhà nghiên cứu**: Phân tích dữ liệu ADAS

### 1.3 Use Cases Chính
1. **Upload và xử lý video**: Người dùng upload video → AI phân tích → Trả về kết quả
2. **Streaming real-time**: Camera gửi frame → Xử lý ngay lập tức → Cảnh báo qua WebSocket
3. **Quản lý chuyến đi**: Tạo trip → Ghi nhận sự kiện → Thống kê an toàn
4. **Chatbot AI**: Hỏi đáp về hệ thống ADAS

---

## 2. KIẾN TRÚC TỔNG QUAN

### 2.1 Sơ Đồ Kiến Trúc (Mô Tả Text)

```
┌─────────────────────────────────────────────────────────────┐
│                      CLIENT LAYER                            │
│  (Web Frontend, Mobile App, IoT Devices)                    │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTP/HTTPS + WebSocket
┌──────────────────▼──────────────────────────────────────────┐
│                   FASTAPI APPLICATION                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │   CORS     │  │    Auth    │  │  Logging   │            │
│  │ Middleware │  │ Middleware │  │  Middleware│            │
│  └────────────┘  └────────────┘  └────────────┘            │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                    API ROUTER LAYER                          │
│  /api/video  /api/events  /api/trips  /api/streaming  ...  │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                   SERVICE LAYER                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ VideoService │ │  JobService  │ │ RiskEngine   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│              REPOSITORY LAYER (Data Access)                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ VideoJobRepo │ │  EventRepo   │ │   TripRepo   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                 DATABASE LAYER                               │
│           Microsoft SQL Server 2022                          │
│  (video_jobs, safety_events, trips, users, ...)            │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                  AI PERCEPTION LAYER                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ YOLOv11      │ │ Lane Detector│ │ MediaPipe    │        │
│  │ (Object)     │ │ (Geometry)   │ │ (Driver)     │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
│         ▲                                                     │
│         │ Gọi từ JobService (Background Thread)             │
└─────────┴───────────────────────────────────────────────────┘
```

### 2.2 Phân Tầng Kiến Trúc

| Tầng | Trách Nhiệm | Công Nghệ |
|------|-------------|-----------|
| **Router** | Nhận HTTP request, validate input | FastAPI APIRouter |
| **Service** | Business logic, orchestration | Python classes |
| **Repository** | Truy vấn database, CRUD operations | SQLAlchemy async |
| **Database** | Lưu trữ persistent data | MS SQL Server |
| **AI Perception** | Xử lý video, phát hiện đối tượng | YOLOv11, MediaPipe, OpenCV |

### 2.3 Technology Stack

- **Framework**: FastAPI 0.104+
- **Database**: Microsoft SQL Server 2022 (pyodbc + SQLAlchemy async)
- **ORM**: SQLAlchemy 2.0 (async)
- **Migration**: Alembic
- **AI/ML**: 
  - YOLOv11 (Ultralytics) - Object detection
  - MediaPipe - Face mesh, drowsiness detection
  - OpenCV - Video processing, lane detection
- **Background Jobs**: ThreadPoolExecutor + asyncio
- **WebSocket**: FastAPI WebSocket
- **Authentication**: JWT (dummy implementation)
- **Logging**: Python logging (JSON format)

---

## 3. CẤU TRÚC THƯ MỤC DỰ ÁN

```
backend-python/
├── backend/
│   ├── app/                          # FastAPI application
│   │   ├── main.py                   # Entry point
│   │   ├── models.py                 # Pydantic models (in-memory)
│   │   ├── api/                      # API endpoints (15 routers)
│   │   │   ├── video.py              # Upload/process video
│   │   │   ├── auth.py               # Login/logout
│   │   │   ├── events_alerts.py      # Safety events
│   │   │   ├── trips_stats.py        # Trip management
│   │   │   ├── streaming.py          # Real-time streaming
│   │   │   ├── websocket_alerts.py   # WebSocket alerts
│   │   │   ├── ai_chat.py            # AI chatbot
│   │   │   ├── driver_monitor.py     # Driver status
│   │   │   ├── models_api.py         # AI model management
│   │   │   ├── dataset.py            # Dataset management
│   │   │   ├── detections.py         # Detection results
│   │   │   ├── videos_api.py         # Video CRUD
│   │   │   ├── upload_storage.py     # File upload
│   │   │   └── settings.py           # System settings
│   │   ├── core/                     # Core utilities
│   │   │   ├── config.py             # Environment config
│   │   │   ├── logging.py            # Logging setup
│   │   │   └── exceptions.py         # Custom exceptions
│   │   ├── db/                       # Database layer
│   │   │   ├── session.py            # DB connection
│   │   │   ├── base.py               # SQLAlchemy base
│   │   │   ├── models/               # SQLAlchemy models (10 files)
│   │   │   │   ├── video_job.py      # Video processing jobs
│   │   │   │   ├── safety_event.py   # Safety events
│   │   │   │   ├── trip.py           # Trip records
│   │   │   │   ├── user.py           # User accounts
│   │   │   │   ├── driver_state.py   # Driver monitoring
│   │   │   │   ├── alert.py          # Alert notifications
│   │   │   │   └── ...
│   │   │   └── repositories/         # Data access layer (6 repos)
│   │   │       ├── video_job_repo.py
│   │   │       ├── safety_event_repo.py
│   │   │       └── ...
│   │   ├── services/                 # Business logic
│   │   │   ├── job_service.py        # Background job processing
│   │   │   ├── video_service.py      # Video validation/storage
│   │   │   ├── risk_engine.py        # Risk assessment
│   │   │   ├── context_engine.py     # AI context management
│   │   │   ├── analysis_service.py   # Data analysis
│   │   │   └── tts_service.py        # Text-to-speech
│   │   ├── schemas/                  # Pydantic request/response
│   │   │   ├── video.py
│   │   │   ├── event.py
│   │   │   └── ...
│   │   └── storage/                  # File storage
│   │       ├── raw/                  # Uploaded videos
│   │       ├── result/               # Processed videos
│   │       └── audio_cache/          # TTS cache
│   └── perception/                   # AI Perception modules
│       ├── pipeline/
│       │   └── video_pipeline_v11.py # MAIN AI PIPELINE
│       ├── object/
│       │   ├── object_detector_v11.py # YOLOv11 detector
│       │   └── object_tracker.py      # Object tracking
│       ├── lane/
│       │   └── lane_detector_v11.py   # Lane detection
│       ├── distance/
│       │   └── distance_estimator.py  # Distance estimation
│       ├── driver/
│       │   └── driver_monitor_v11.py  # Drowsiness detection
│       ├── traffic/
│       │   └── traffic_sign_v11.py    # Traffic sign recognition
│       └── risk/
│           └── risk_assessor.py       # Risk calculation
├── alembic/                          # Database migrations
├── requirements.txt                  # Python dependencies
├── run.py                            # Production runner
├── .env                              # Environment variables
└── README.md                         # Documentation
```

---

## 4. TỔNG QUAN API

### 4.1 Nhóm API Chính

| Nhóm API | Prefix | Mục Đích |
|----------|--------|----------|
| **Video Processing** | `/api/video` | Upload, xử lý, tải video |
| **Authentication** | `/api/auth` | Login, logout, user management |
| **Events & Alerts** | `/api/events`, `/api/alerts` | Quản lý sự kiện an toàn |
| **Trips & Stats** | `/api/trips`, `/api/statistics` | Quản lý chuyến đi, thống kê |
| **Streaming** | `/api/streaming` | Real-time video streaming |
| **WebSocket** | `/ws/alerts` | Cảnh báo real-time |
| **AI Chat** | `/api/chat` | Chatbot AI |
| **Driver Monitor** | `/api/driver` | Giám sát tài xế |
| **Models** | `/api/models` | Quản lý AI models |
| **Dataset** | `/api/dataset` | Quản lý dataset |
| **Detections** | `/api/detections` | Kết quả phát hiện |
| **Settings** | `/api/settings` | Cấu hình hệ thống |
| **Upload/Storage** | `/api/upload`, `/api/storage` | Upload file, quản lý storage |

### 4.2 API Endpoints Chi Tiết

#### 4.2.1 Video Processing (`/api/video`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| POST | `/api/video/upload` | ✅ **SỬ DỤNG ĐƯỢC** | Upload video để xử lý AI |
| GET | `/api/video/result/{job_id}` | ✅ **SỬ DỤNG ĐƯỢC** | Lấy kết quả xử lý |
| GET | `/api/video/download/{job_id}/{filename}` | ✅ **SỬ DỤNG ĐƯỢC** | Tải video đã xử lý |
| DELETE | `/api/video/job/{job_id}` | ✅ **SỬ DỤNG ĐƯỢC** | Xóa job và file |
| GET | `/api/video/health` | ✅ **SỬ DỤNG ĐƯỢC** | Health check |

**Cách sử dụng:**
```bash
# Upload video
curl -X POST https://adas-api.aiotlab.edu.vn:52000/api/video/upload \
  -F "file=@video.mp4" \
  -F "video_type=dashcam" \
  -F "device=cpu"

# Response: {"job_id": "abc-123", "status": "pending"}

# Kiểm tra kết quả
curl https://adas-api.aiotlab.edu.vn:52000/api/video/result/abc-123
```

#### 4.2.2 Authentication (`/api/auth`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| POST | `/api/auth/login` | ✅ **SỬ DỤNG ĐƯỢC** | Đăng nhập (dummy) |
| POST | `/api/auth/logout` | ✅ **SỬ DỤNG ĐƯỢC** | Đăng xuất |
| GET | `/api/auth/me` | ✅ **SỬ DỤNG ĐƯỢC** | Lấy thông tin user hiện tại |
| GET | `/api/auth/users` | ✅ **SỬ DỤNG ĐƯỢC** | Danh sách users (admin only) |
| POST | `/api/auth/users` | ✅ **SỬ DỤNG ĐƯỢC** | Tạo user mới (admin only) |

**Tài khoản test:**
- `admin / admin123` (role: admin)
- `driver1 / driver123` (role: driver)
- `analyst / analyst123` (role: analyst)

#### 4.2.3 Events & Alerts (`/api/events`, `/api/alerts`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| POST | `/api/events` | ✅ **SỬ DỤNG ĐƯỢC** | Tạo sự kiện an toàn |
| GET | `/api/events/list` | ✅ **SỬ DỤNG ĐƯỢC** | Danh sách events (filter, phân trang) |
| PUT | `/api/events/{id}/acknowledge` | ✅ **SỬ DỤNG ĐƯỢC** | Xác nhận đã xem event |
| DELETE | `/api/events/{id}` | ✅ **SỬ DỤNG ĐƯỢC** | Xóa event |
| GET | `/api/alerts/latest` | ✅ **SỬ DỤNG ĐƯỢC** | Lấy alerts mới nhất |
| GET | `/api/alerts/stats` | ✅ **SỬ DỤNG ĐƯỢC** | Thống kê alerts |
| PUT | `/api/alerts/{id}/played` | ✅ **SỬ DỤNG ĐƯỢC** | Đánh dấu đã phát cảnh báo |

#### 4.2.4 Trips & Statistics (`/api/trips`, `/api/statistics`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| POST | `/api/trips` | ✅ **SỬ DỤNG ĐƯỢC** | Tạo chuyến đi mới |
| GET | `/api/trips/list` | ✅ **SỬ DỤNG ĐƯỢC** | Danh sách trips |
| GET | `/api/trips/{id}` | ✅ **SỬ DỤNG ĐƯỢC** | Chi tiết trip |
| PUT | `/api/trips/{id}/complete` | ✅ **SỬ DỤNG ĐƯỢC** | Kết thúc trip |
| GET | `/api/trips/analytics` | ✅ **SỬ DỤNG ĐƯỢC** | Phân tích trips |
| GET | `/api/statistics/summary` | ✅ **SỬ DỤNG ĐƯỢC** | Tổng quan thống kê |
| GET | `/api/statistics/detections-by-class` | ✅ **SỬ DỤNG ĐƯỢC** | Thống kê theo loại đối tượng |
| GET | `/api/statistics/events-by-type` | ✅ **SỬ DỤNG ĐƯỢC** | Thống kê theo loại sự kiện |
| GET | `/api/statistics/performance` | ✅ **SỬ DỤNG ĐƯỢC** | Hiệu suất hệ thống |

#### 4.2.5 Real-time Streaming (`/api/streaming`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| POST | `/api/streaming/start` | ✅ **SỬ DỤNG ĐƯỢC** | Bắt đầu streaming session |
| GET | `/api/streaming/poll/{session_id}` | ✅ **SỬ DỤNG ĐƯỢC** | Lấy frame đã xử lý |
| POST | `/api/streaming/frame` | ✅ **SỬ DỤNG ĐƯỢC** | Gửi frame để xử lý |
| POST | `/api/streaming/stop` | ✅ **SỬ DỤNG ĐƯỢC** | Dừng streaming |

#### 4.2.6 WebSocket Alerts (`/ws/alerts`)

| Type | Endpoint | Trạng Thái | Mô Tả |
|------|----------|------------|-------|
| WebSocket | `/ws/alerts` | ✅ **SỬ DỤNG ĐƯỢC** | Nhận cảnh báo real-time |

**Cách sử dụng:**
```javascript
const ws = new WebSocket('wss://adas-api.aiotlab.edu.vn:52000/ws/alerts');
ws.onmessage = (event) => {
  const alert = JSON.parse(event.data);
  console.log('Alert:', alert);
};
```

#### 4.2.7 AI Chat (`/api/chat`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| POST | `/api/chat` | ✅ **SỬ DỤNG ĐƯỢC** | Gửi tin nhắn cho AI |
| GET | `/api/chat/history` | ✅ **SỬ DỤNG ĐƯỢC** | Lịch sử chat |
| DELETE | `/api/chat/session/{id}` | ✅ **SỬ DỤNG ĐƯỢC** | Xóa session chat |

#### 4.2.8 Driver Monitor (`/api/driver`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| POST | `/api/driver/status` | ✅ **SỬ DỤNG ĐƯỢC** | Cập nhật trạng thái tài xế |
| GET | `/api/driver/current` | ✅ **SỬ DỤNG ĐƯỢC** | Trạng thái hiện tại |
| GET | `/api/driver/history` | ✅ **SỬ DỤNG ĐƯỢC** | Lịch sử trạng thái |
| GET | `/api/driver/stats` | ✅ **SỬ DỤNG ĐƯỢC** | Thống kê tài xế |

#### 4.2.9 AI Models (`/api/models`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| GET | `/api/models/available` | ✅ **SỬ DỤNG ĐƯỢC** | Danh sách models |
| POST | `/api/models/download/{id}` | ⚠️ **CHƯA HOÀN CHỈNH** | Download model (mock) |
| GET | `/api/models/info/{id}` | ✅ **SỬ DỤNG ĐƯỢC** | Thông tin model |
| DELETE | `/api/models/delete/{id}` | ⚠️ **CHƯA HOÀN CHỈNH** | Xóa model (mock) |

#### 4.2.10 Dataset (`/api/dataset`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| GET | `/api/dataset` | ✅ **SỬ DỤNG ĐƯỢC** | Danh sách dataset (in-memory) |
| POST | `/api/dataset` | ⚠️ **MOCK DATA** | Upload dataset (mock) |
| GET | `/api/dataset/{id}` | ✅ **SỬ DỤNG ĐƯỢC** | Chi tiết dataset |
| DELETE | `/api/dataset/{id}` | ⚠️ **MOCK DATA** | Xóa dataset (mock) |

#### 4.2.11 Detections (`/api/detections`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| POST | `/api/detections/save` | ✅ **SỬ DỤNG ĐƯỢC** | Lưu detection results (in-memory) |
| GET | `/api/detections/recent` | ✅ **SỬ DỤNG ĐƯỢC** | Detections gần đây |
| GET | `/api/detections/stats` | ✅ **SỬ DỤNG ĐƯỢC** | Thống kê detections |

#### 4.2.12 Settings (`/api/settings`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| GET | `/api/settings` | ✅ **SỬ DỤNG ĐƯỢC** | Lấy cấu hình (mock) |
| PUT | `/api/settings` | ✅ **SỬ DỤNG ĐƯỢC** | Cập nhật cấu hình (mock) |
| GET | `/api/settings/cameras` | ✅ **SỬ DỤNG ĐƯỢC** | Danh sách cameras |
| POST | `/api/settings/cameras` | ✅ **SỬ DỤNG ĐƯỢC** | Thêm camera |
| PUT | `/api/settings/cameras/{id}` | ✅ **SỬ DỤNG ĐƯỢC** | Cập nhật camera |
| DELETE | `/api/settings/cameras/{id}` | ✅ **SỬ DỤNG ĐƯỢC** | Xóa camera |

#### 4.2.13 Upload/Storage (`/api/upload`, `/api/storage`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| POST | `/api/upload/image` | ✅ **SỬ DỤNG ĐƯỢC** | Upload ảnh |
| POST | `/api/upload/batch` | ✅ **SỬ DỤNG ĐƯỢC** | Upload nhiều file |
| GET | `/api/storage/info` | ✅ **SỬ DỤNG ĐƯỢC** | Thông tin storage |
| GET | `/api/storage/files` | ✅ **SỬ DỤNG ĐƯỢC** | Danh sách files |
| DELETE | `/api/storage/cleanup` | ✅ **SỬ DỤNG ĐƯỢC** | Dọn dẹp files cũ |

#### 4.2.14 Videos API (`/api/videos`)

| Method | Endpoint | Trạng Thái | Mô Tả |
|--------|----------|------------|-------|
| GET | `/api/videos` | ✅ **SỬ DỤNG ĐƯỢC** | Danh sách videos (in-memory) |
| GET | `/api/videos/{id}` | ✅ **SỬ DỤNG ĐƯỢC** | Chi tiết video |
| POST | `/api/videos/{id}/process` | ⚠️ **MOCK** | Xử lý lại video |
| DELETE | `/api/videos/{id}` | ✅ **SỬ DỤNG ĐƯỢC** | Xóa video |

### 4.3 Tóm Tắt Trạng Thái API

| Trạng Thái | Ý Nghĩa | Số Lượng |
|------------|---------|----------|
| ✅ **SỬ DỤNG ĐƯỢC** | API hoạt động đầy đủ, có thể dùng ngay | ~85% |
| ⚠️ **MOCK DATA** | API hoạt động nhưng dùng in-memory, không lưu DB | ~10% |
| ⚠️ **CHƯA HOÀN CHỈNH** | API có nhưng chưa implement đầy đủ | ~5% |
| ❌ **KHÔNG DÙNG** | Không có API này | 0% |

---

## 5. LUỒNG XỬ LÝ AI & VIDEO (QUAN TRỌNG)

### 5.1 Quy Trình Upload và Xử Lý Video

```
┌─────────────────────────────────────────────────────────────┐
│ 1. CLIENT UPLOAD VIDEO                                       │
│    POST /api/video/upload                                    │
│    - file: video.mp4                                         │
│    - video_type: "dashcam" hoặc "in_cabin"                  │
│    - device: "cpu" hoặc "cuda"                              │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. VIDEO ROUTER (video.py)                                   │
│    - Validate file (size, format)                           │
│    - Tạo VideoJob trong database (status: pending)          │
│    - Lưu file vào storage/raw/{job_id}/                     │
│    - Trả về job_id ngay lập tức (NON-BLOCKING)              │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. JOB SERVICE (job_service.py)                              │
│    - Submit job vào ThreadPoolExecutor                       │
│    - Chạy background (không block API)                       │
│    - Update status: "processing"                             │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. AI PIPELINE (perception/pipeline/video_pipeline_v11.py)   │
│    ┌──────────────────────────────────────────────────┐    │
│    │ 4.1 Đọc video frame-by-frame                      │    │
│    │ 4.2 Phát hiện loại video (dashcam/in-cabin)      │    │
│    │ 4.3 Xử lý từng frame:                             │    │
│    │     - YOLOv11: Detect objects (car, person, ...)  │    │
│    │     - Lane Detector: Phát hiện làn đường          │    │
│    │     - Distance Estimator: Tính khoảng cách        │    │
│    │     - Risk Assessor: Đánh giá nguy hiểm           │    │
│    │     - Traffic Sign: Nhận diện biển báo            │    │
│    │     - Driver Monitor: Phát hiện mệt mỏi (in-cabin)│    │
│    │ 4.4 Vẽ annotations lên frame                      │    │
│    │ 4.5 Ghi frame vào video output                    │    │
│    │ 4.6 Thu thập events (collision, lane departure)   │    │
│    └──────────────────────────────────────────────────┘    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. LƯU KẾT QUẢ                                               │
│    - Lưu processed video vào storage/result/{job_id}/       │
│    - Lưu safety_events vào database                         │
│    - Update VideoJob: status="completed"                    │
│    - Tính processing_time_seconds                           │
└─────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. CLIENT LẤY KẾT QUẢ                                        │
│    GET /api/video/result/{job_id}                           │
│    - Trả về: status, result_path, events, stats            │
│    GET /api/video/download/{job_id}/{filename}              │
│    - Download video đã xử lý                                │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Chi Tiết AI Pipeline

**File chính:** `backend/perception/pipeline/video_pipeline_v11.py`

**Hàm entry point:**
```python
def process_video(
    input_path: str,
    output_path: str,
    video_type: str = "dashcam",
    device: str = "cpu"
) -> Dict[str, Any]
```

**Các module AI được sử dụng:**

| Module | File | Chức Năng |
|--------|------|-----------|
| **ObjectDetectorV11** | `perception/object/object_detector_v11.py` | YOLOv11 - Phát hiện xe, người, xe máy |
| **LaneDetectorV11** | `perception/lane/lane_detector_v11.py` | Geometry-based lane detection |
| **DistanceEstimator** | `perception/distance/distance_estimator.py` | Ước lượng khoảng cách monocular |
| **RiskAssessor** | `perception/risk/risk_assessor.py` | TTC, LDW, FCW calculation |
| **TrafficSignV11** | `perception/traffic/traffic_sign_v11.py` | Nhận diện biển báo |
| **DriverMonitorV11** | `perception/driver/driver_monitor_v11.py` | MediaPipe Face Mesh, drowsiness |

### 5.3 Background vs Synchronous

| Loại | API | Hành Vi |
|------|-----|---------|
| **Background** | `/api/video/upload` | Trả về ngay, xử lý sau |
| **Synchronous** | `/api/streaming/frame` | Đợi xử lý xong mới trả về |
| **WebSocket** | `/ws/alerts` | Push real-time khi có event |

### 5.4 Cách AI Jobs Được Tạo

1. **Upload video** → Tạo `VideoJob` (status: pending)
2. **JobService.submit_job()** → Submit vào ThreadPoolExecutor
3. **Thread pool** → Gọi `process_video()` từ AI pipeline
4. **Callback** → Update database khi xong

---

## 6. DATA MODELS & DATABASE

### 6.1 Core Entities (SQLAlchemy Models)

| Model | File | Mục Đích |
|-------|------|----------|
| **VideoJob** | `db/models/video_job.py` | Lưu thông tin video processing jobs |
| **SafetyEvent** | `db/models/safety_event.py` | Sự kiện an toàn (collision, LDW, ...) |
| **Trip** | `db/models/trip.py` | Chuyến đi của tài xế |
| **User** | `db/models/user.py` | Tài khoản người dùng |
| **DriverState** | `db/models/driver_state.py` | Trạng thái tài xế (fatigue, distraction) |
| **Alert** | `db/models/alert.py` | Cảnh báo cần phát cho tài xế |
| **Vehicle** | `db/models/vehicle.py` | Thông tin xe |
| **TrafficSign** | `db/models/traffic_sign.py` | Biển báo phát hiện được |
| **ModelVersion** | `db/models/model_version.py` | Phiên bản AI models |

### 6.2 Quan Hệ Giữa Các Models

```
User (1) ──────── (N) Trip
                       │
                       │ (1)
                       │
                       ▼
                   VideoJob (N)
                       │
                       │ (1)
                       │
                       ▼
                   SafetyEvent (N)

Trip (1) ──────── (N) DriverState
Trip (1) ──────── (N) Alert
```

### 6.3 Enum Usage

**JobStatus** (`video_job.py`):
- `pending`: Chờ xử lý
- `processing`: Đang xử lý
- `completed`: Hoàn thành
- `failed`: Lỗi

**EventType** (`models.py`):
- `collision`: Va chạm
- `lane_departure`: Lệch làn
- `fatigue`: Mệt mỏi
- `distraction`: Mất tập trung
- `speed`: Vượt tốc độ

**EventSeverity**:
- `critical`: Nghiêm trọng
- `warning`: Cảnh báo
- `info`: Thông tin

---

## 7. SERVICE LAYER

### 7.1 Trách Nhiệm Từng Service

| Service | File | Trách Nhiệm |
|---------|------|-------------|
| **JobService** | `services/job_service.py` | Quản lý background jobs, ThreadPoolExecutor |
| **VideoService** | `services/video_service.py` | Validate video, lưu file, tạo job |
| **RiskEngine** | `services/risk_engine.py` | Đánh giá mức độ nguy hiểm, tính safety score |
| **ContextEngine** | `services/context_engine.py` | Quản lý context cho AI chatbot |
| **AnalysisService** | `services/analysis_service.py` | Phân tích dữ liệu, tạo báo cáo |
| **TTSService** | `services/tts_service.py` | Text-to-speech cho cảnh báo |

### 7.2 Dependency Injection

Services được inject qua FastAPI `Depends()`:

```python
from app.db.session import get_db

@router.post("/upload")
async def upload_video(
    file: UploadFile,
    db: AsyncSession = Depends(get_db)  # ← Inject DB session
):
    video_service = VideoService(db)  # ← Tạo service với DB
    ...
```

### 7.3 Service Interaction

```
Router → VideoService → VideoJobRepository → Database
              ↓
         JobService → AI Pipeline → Perception Modules
              ↓
         SafetyEventRepository → Database
```

---

## 8. XỬ LÝ LỖI & VALIDATION

### 8.1 Global Error Handling

- **HTTPException**: FastAPI tự động bắt và trả về JSON error
- **Custom Exceptions**: `app/core/exceptions.py`
  - `ValidationError`: Lỗi validate input
  - `JobNotFoundError`: Không tìm thấy job
  - `ProcessingError`: Lỗi xử lý AI

### 8.2 Validation Strategy

- **Pydantic Models**: Validate request body tự động
- **File Validation**: Kiểm tra size, format trong `VideoService`
- **Database Constraints**: Unique, foreign key, not null

### 8.3 Typical Error Responses

```json
{
  "detail": "Video file too large. Max: 500MB"
}
```

```json
{
  "detail": "Job abc-123 not found"
}
```

---

## 9. BẢO MẬT & AN TOÀN

### 9.1 Authentication

- **Phương thức**: JWT-like tokens (dummy implementation)
- **Endpoints**: `/api/auth/login`, `/api/auth/logout`
- **Roles**: admin, driver, analyst
- **Lưu ý**: Đây là **mock authentication** cho testing, KHÔNG dùng production

### 9.2 Input Validation

- **File size**: Max 500MB (config: `MAX_VIDEO_SIZE_MB`)
- **File format**: mp4, avi, mov
- **SQL Injection**: SQLAlchemy ORM tự động escape
- **XSS**: FastAPI tự động escape JSON

### 9.3 Rate Limiting

- **Hiện tại**: KHÔNG có rate limiting
- **Khuyến nghị**: Thêm middleware rate limit cho production

### 9.4 CORS

- **Allowed Origins**: Cấu hình trong `.env` (`CORS_ORIGINS`)
- **Default**: `localhost:3000`, `adas-api.aiotlab.edu.vn`

---

## 10. CẤU HÌNH & ENVIRONMENT

### 10.1 Environment Variables

File: `.env`

```bash
# Database
DB_HOST=localhost
DB_PORT=1433
DB_NAME=adas_production
DB_USER=sa
DB_PASSWORD=YourStrong@Passw0rd
DB_DRIVER=ODBC Driver 17 for SQL Server

# API
API_BASE_URL=https://adas-api.aiotlab.edu.vn:52000
HOST=0.0.0.0
PORT=52000
ENVIRONMENT=production

# Security
SECRET_KEY=your-secret-key-min-32-characters
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Storage
STORAGE_ROOT=./backend/storage
RAW_VIDEO_DIR=./backend/storage/raw
PROCESSED_VIDEO_DIR=./backend/storage/result

# AI
YOLO_MODEL_PATH=./backend/models/yolov11n.pt
DEFAULT_DEVICE=cpu  # hoặc cuda

# Processing
MAX_VIDEO_SIZE_MB=500
MAX_CONCURRENT_JOBS=2

# CORS
CORS_ORIGINS=https://adas-api.aiotlab.edu.vn,http://localhost:3000
```

### 10.2 Runtime Modes

- **Development**: `ENVIRONMENT=development` → Debug logging, auto-reload
- **Production**: `ENVIRONMENT=production` → INFO logging, no reload

---

## 11. CÁCH CHẠY HỆ THỐNG

### 11.1 Startup Commands

```bash
# 1. Cài đặt dependencies
pip install -r requirements.txt

# 2. Cấu hình .env
cp .env.example .env
# Chỉnh sửa .env với thông tin database

# 3. Chạy migrations
alembic upgrade head

# 4. Khởi động server
python run.py

# Hoặc dùng uvicorn trực tiếp
uvicorn app.main:app --host 0.0.0.0 --port 52000 --reload
```

### 11.2 Required Services

1. **Microsoft SQL Server** (port 1433)
   - Database: `adas_production`
   - User có quyền CREATE TABLE, INSERT, UPDATE, DELETE

2. **Python 3.10+**

3. **AI Models**:
   - YOLOv11: `backend/models/yolov11n.pt`
   - MediaPipe: Tự động download

4. **Storage Directories**:
   - `backend/storage/raw/`
   - `backend/storage/result/`
   - `backend/storage/audio_cache/`

### 11.3 Docker Deployment

```bash
# Build image
docker build -t adas-backend .

# Run container
docker run -d \
  -p 52000:52000 \
  -v $(pwd)/backend/storage:/app/backend/storage \
  -e DB_HOST=host.docker.internal \
  adas-backend
```

---

## 12. CÁCH MỞ RỘNG HỆ THỐNG AN TOÀN

### 12.1 Thêm API Mới

**Bước 1**: Tạo router mới trong `app/api/`

```python
# app/api/my_feature.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/my-feature", tags=["my-feature"])

@router.get("/")
async def get_data():
    return {"message": "Hello"}
```

**Bước 2**: Register router trong `app/main.py`

```python
from app.api.my_feature import router as my_feature_router

app.include_router(my_feature_router)
```

### 12.2 Thêm AI Logic Mới

**Bước 1**: Tạo module trong `backend/perception/`

```python
# backend/perception/my_module/my_detector.py
class MyDetector:
    def detect(self, frame):
        # AI logic
        return results
```

**Bước 2**: Tích hợp vào pipeline

```python
# backend/perception/pipeline/video_pipeline_v11.py
from ..my_module.my_detector import MyDetector

class VideoPipelineV11:
    def __init__(self):
        self.my_detector = MyDetector()
    
    def process_dashcam_frame(self, frame):
        results = self.my_detector.detect(frame)
        # Xử lý results
```

### 12.3 Thêm Database Model Mới

**Bước 1**: Tạo model trong `app/db/models/`

```python
# app/db/models/my_model.py
from sqlalchemy import Column, Integer, String
from ..base import Base

class MyModel(Base):
    __tablename__ = "my_table"
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
```

**Bước 2**: Tạo migration

```bash
alembic revision --autogenerate -m "Add my_table"
alembic upgrade head
```

**Bước 3**: Tạo repository

```python
# app/db/repositories/my_repo.py
from .base_repo import BaseRepository
from ..models.my_model import MyModel

class MyRepository(BaseRepository[MyModel]):
    pass
```

### 12.4 KHÔNG NÊN CHẠM VÀO

⚠️ **Để tránh phá vỡ AI workflow, KHÔNG sửa:**

1. **`perception/pipeline/video_pipeline_v11.py`** - Core AI pipeline
2. **`services/job_service.py`** - Background job orchestration
3. **`db/session.py`** - Database connection pool
4. **Enum values** trong `models.py` - Frontend đang dùng

✅ **An toàn để sửa:**

1. Thêm router mới trong `app/api/`
2. Thêm service mới trong `app/services/`
3. Thêm model mới trong `app/db/models/`
4. Cấu hình trong `.env`

---

## 13. HẠN CHẾ HIỆN TẠI

### 13.1 Constraints

1. **Video size**: Max 500MB
2. **Concurrent jobs**: Max 2 jobs cùng lúc (config: `MAX_CONCURRENT_JOBS`)
3. **GPU**: Chỉ hỗ trợ CUDA, không hỗ trợ ROCm/MPS
4. **Database**: Chỉ hỗ trợ MS SQL Server

### 13.2 Non-Goals

Hệ thống KHÔNG hỗ trợ:

- ❌ Real-time video streaming từ camera (chỉ hỗ trợ upload file)
- ❌ Multi-tenancy (nhiều tổ chức dùng chung)
- ❌ Distributed processing (chỉ chạy trên 1 server)
- ❌ Video transcoding (không đổi format)
- ❌ Production-grade authentication (chỉ có dummy auth)

### 13.3 Known Issues

1. **In-memory storage**: Một số API dùng in-memory (dataset, detections) → Mất data khi restart
2. **No retry logic**: Job failed không tự động retry
3. **No queue system**: Dùng ThreadPoolExecutor thay vì RabbitMQ/Celery
4. **Limited error recovery**: Crash giữa chừng không tự phục hồi

---

## 14. KIẾN TRÚC TỔNG KẾT

### 14.1 Điểm Mạnh

✅ **Separation of Concerns**: Router → Service → Repository → Database  
✅ **Async/Await**: Non-blocking I/O với SQLAlchemy async  
✅ **Background Processing**: ThreadPoolExecutor cho AI jobs  
✅ **Type Safety**: Pydantic schemas cho validation  
✅ **Modular AI**: Perception modules độc lập, dễ test  
✅ **Production Database**: MS SQL Server với connection pooling  

### 14.2 Điểm Cần Cải Thiện

⚠️ **Authentication**: Cần implement JWT thật  
⚠️ **Rate Limiting**: Cần thêm middleware  
⚠️ **Monitoring**: Cần Prometheus/Grafana  
⚠️ **Logging**: Cần centralized logging (ELK stack)  
⚠️ **Testing**: Cần thêm unit tests, integration tests  
⚠️ **Documentation**: Cần OpenAPI examples chi tiết hơn  

---

## 15. WORKFLOW ĐIỂN HÌNH

### 15.1 Upload và Xử Lý Video

```
1. POST /api/video/upload → job_id
2. Đợi 30s - 5 phút (tùy video)
3. GET /api/video/result/{job_id} → status="completed"
4. GET /api/video/download/{job_id}/result.mp4
```

### 15.2 Quản Lý Chuyến Đi

```
1. POST /api/trips → trip_id
2. POST /api/video/upload (với trip_id)
3. Hệ thống tự động ghi events vào trip
4. PUT /api/trips/{trip_id}/complete
5. GET /api/trips/{trip_id} → Xem safety_score, events
```

### 15.3 Real-time Streaming

```
1. POST /api/streaming/start → session_id
2. Loop:
   - POST /api/streaming/frame (gửi frame)
   - GET /api/streaming/poll/{session_id} (nhận kết quả)
3. POST /api/streaming/stop
```

---

## 16. TÀI LIỆU THAM KHẢO

- **API Docs**: https://adas-api.aiotlab.edu.vn:52000/docs
- **ReDoc**: https://adas-api.aiotlab.edu.vn:52000/redoc
- **GitHub**: https://github.com/buivanchuong9/BE-ADAS.git
- **README**: [README.md](README.md)
- **Deployment Guide**: [WINDOWS_SERVER_DEPLOYMENT.md](WINDOWS_SERVER_DEPLOYMENT.md)

---

## 17. LIÊN HỆ & HỖ TRỢ

**Team**: NCKH ADAS Development Team  
**Repository**: https://github.com/buivanchuong9/BE-ADAS.git  
**Date**: December 2025

---

## PHỤ LỤC: DANH SÁCH API ĐẦY ĐỦ

### A. APIs Sử Dụng Được (Production Ready)

```
✅ POST   /api/video/upload
✅ GET    /api/video/result/{job_id}
✅ GET    /api/video/download/{job_id}/{filename}
✅ DELETE /api/video/job/{job_id}
✅ GET    /api/video/health

✅ POST   /api/auth/login
✅ POST   /api/auth/logout
✅ GET    /api/auth/me
✅ GET    /api/auth/users
✅ POST   /api/auth/users

✅ POST   /api/events
✅ GET    /api/events/list
✅ PUT    /api/events/{id}/acknowledge
✅ DELETE /api/events/{id}
✅ GET    /api/alerts/latest
✅ GET    /api/alerts/stats
✅ PUT    /api/alerts/{id}/played

✅ POST   /api/trips
✅ GET    /api/trips/list
✅ GET    /api/trips/{id}
✅ PUT    /api/trips/{id}/complete
✅ GET    /api/trips/analytics
✅ GET    /api/statistics/summary
✅ GET    /api/statistics/detections-by-class
✅ GET    /api/statistics/events-by-type
✅ GET    /api/statistics/performance

✅ POST   /api/streaming/start
✅ GET    /api/streaming/poll/{session_id}
✅ POST   /api/streaming/frame
✅ POST   /api/streaming/stop

✅ WS     /ws/alerts

✅ POST   /api/chat
✅ GET    /api/chat/history
✅ DELETE /api/chat/session/{id}

✅ POST   /api/driver/status
✅ GET    /api/driver/current
✅ GET    /api/driver/history
✅ GET    /api/driver/stats

✅ GET    /api/models/available
✅ GET    /api/models/info/{id}

✅ POST   /api/upload/image
✅ POST   /api/upload/batch
✅ GET    /api/storage/info
✅ GET    /api/storage/files
✅ DELETE /api/storage/cleanup

✅ GET    /api/settings
✅ PUT    /api/settings
✅ GET    /api/settings/cameras
✅ POST   /api/settings/cameras
✅ PUT    /api/settings/cameras/{id}
✅ DELETE /api/settings/cameras/{id}
```

### B. APIs Mock/In-Memory (Cần Cẩn Thận)

```
⚠️ GET    /api/dataset
⚠️ POST   /api/dataset
⚠️ GET    /api/dataset/{id}
⚠️ DELETE /api/dataset/{id}

⚠️ POST   /api/detections/save
⚠️ GET    /api/detections/recent
⚠️ GET    /api/detections/stats

⚠️ GET    /api/videos
⚠️ GET    /api/videos/{id}
⚠️ POST   /api/videos/{id}/process
⚠️ DELETE /api/videos/{id}

⚠️ POST   /api/models/download/{id}
⚠️ DELETE /api/models/delete/{id}
```

### C. APIs Không Khả Dụng

```
❌ KHÔNG CÓ
```

---

**KẾT THÚC TÀI LIỆU**

Tài liệu này cung cấp đầy đủ thông tin để:
- ✅ Hiểu rõ hệ thống backend ADAS
- ✅ Tích hợp API vào frontend/mobile
- ✅ Mở rộng tính năng mới
- ✅ Debug và maintain hệ thống
- ✅ Onboard developer mới
- ✅ Cung cấp context cho AI assistant
