# ADAS Backend - Changelog & Architecture

> **De tai #138:** Phat trien ung dung canh bao thong minh cho o to chay tren dien thoai Android
> **Server:** `phonglv@adas-api.aiotlab.edu.vn` - NVIDIA A30 24GB, CUDA 12.2
> **Repo:** https://github.com/buivanchuong9/BE-ADAS
> **Cap nhat:** 2026-02-27

---

## Kien truc he thong

```
+---------------+     +------------------+     +----------------------+
|  Mobile App   |---->|  FastAPI Backend  |---->|  PostgreSQL Database |
|  (Android)    |<----|  (port 52000)     |<----|  (Supabase)          |
+---------------+     +--------+---------+     +----------+-----------+
                               |                          |
                               |  pg_notify()             | SELECT FOR UPDATE
                               |                          | SKIP LOCKED
                               v                          |
                     +-----------------+                   |
                     |  GPU Worker     |<------------------+
                     |  (CUDA A30)     |
                     |                 |
                     |  +-----------+  |
                     |  | YOLOv11x  |  |  <- Object Detection
                     |  | UFLD v2   |  |  <- Lane Detection
                     |  | Pose Est. |  |  <- Driver Monitor
                     |  | Distance  |  |  <- Monocular Depth
                     |  | Risk Eng. |  |  <- Risk Assessment
                     |  +-----------+  |
                     +-----------------+
```

**Job Queue:** PostgreSQL-native (`SELECT FOR UPDATE SKIP LOCKED` + `pg_notify`) - **Khong dung Redis/Celery.**

---

## AI Perception Pipeline

| # | Module | File | Dong code | Mo ta |
|---|--------|------|-----------|-------|
| 1 | **Object Detection** | `object_detector_v11.py` | 344 | YOLOv11x / YOLOv8n - nhan dien xe, nguoi, xe may |
| 2 | **Lane Detection** | `lane_detector_ufld.py` | 865 | **UFLD v2** (Ultra Fast Lane Detection) - ~300 FPS |
| 3 | **Driver Monitor** | `driver_monitor_v11.py` | 454 | YOLOv11x-pose - phat hien ngu gat, dung dien thoai |
| 4 | **Distance Estimation** | `distance_estimator.py` | 519 | Monocular pinhole camera - uoc luong khoang cach |
| 5 | **Risk Engine** | `risk_engine_v4.py` | 626 | TTC + ego danger zone - danh gia rui ro va cham |
| 6 | **TensorRT Optimizer** | `tensorrt_optimizer.py` | 328 | Auto-export .pt -> FP16 .engine (2-3x speedup) |
| 7 | **Vietnamese Overlay** | `vietnamese_overlay.py` | 583 | PIL-based HUD voi dau tieng Viet |
| 8 | **Lane V4 (legacy)** | `lane_detector_v4.py` | 781 | BEV classical + sliding window (backup) |
| 9 | **GPU Worker** | `gpu_worker_simple.py` | 1414 | Main processor - orchestrate toan bo pipeline |

**Tong:** ~5,900 dong code AI perception

---

## 3 Model AI chinh

### Model 1: YOLOv11x - Object Detection
- **Nhiem vu:** Phat hien xe co, nguoi di bo, xe may, xe bus, xe tai
- **File:** `backend/perception/object/object_detector_v11.py`
- **Weight:** `backend/models/yolo11x.pt` (cloud) / `yolov8n.pt` (edge)
- **Input:** 416x416 (cloud) / 320x320 (edge)
- **Output:** Bounding boxes + class name + confidence
- **FPS:** ~45 FPS tren A30

### Model 2: UFLD v2 - Ultra Fast Lane Detection
- **Nhiem vu:** Phat hien lan duong (4 lanes) cuc nhanh
- **File:** `backend/perception/lane/lane_detector_ufld.py`
- **Architecture:** ResNet-18 backbone -> Row Classification Head
  - 72 row anchors x 200 column cells x 4 lanes
  - Sub-pixel refinement + EMA smoothing
- **Weight:** `backend/models/ufld_tusimple.pth`
- **FPS:** ~300 FPS tren A30 (nhanh hon 10-50x so voi segmentation)
- **Output:** Lane points (N,2), lane offset [-1,+1], offset level (SAFE/WARNING/CRITICAL)

### Model 3: YOLOv11x-pose - Driver Monitoring
- **Nhiem vu:** Phat hien tu the lai xe, ngu gat, dung dien thoai
- **File:** `backend/perception/driver/driver_monitor_v11.py`
- **Weight:** `backend/models/yolo11x-pose.pt` (cloud) / `yolov8n-pose.pt` (edge)
- **Output:** Driver state (NORMAL/DROWSY/PHONE/DRINKING)

---

## Model Profile System

Worker ho tro 2 profile, chon khi khoi dong:

| Profile | Object Det. | Lane Det. | Pose Est. | imgsz | Muc dich |
|---------|-------------|-----------|-----------|-------|----------|
| `cloud` | YOLOv11x | UFLD v2 | YOLOv11x-pose | 416 | Server GPU (A30/A100) - do chinh xac cao |
| `edge` | YOLOv8n | UFLD v2 | YOLOv8n-pose | 320 | Thiet bi nho (Jetson/mobile) - real-time |

```bash
# Cloud profile (default)
python3 workers/gpu_worker_simple.py --profile cloud --device cuda

# Edge profile
python3 workers/gpu_worker_simple.py --profile edge --device cuda

# Tat TensorRT
python3 workers/gpu_worker_simple.py --no-tensorrt
```

---

## API Endpoints (FastAPI)

| Method | Endpoint | Mo ta |
|--------|----------|-------|
| `POST` | `/api/video/upload` | Upload video -> tra `job_id` ngay lap tuc |
| `GET` | `/api/video/progress/{job_id}` | Xem tien do xu ly (%) |
| `GET` | `/api/video/result/{job_id}` | Lay ket qua phan tich |
| `GET` | `/api/video/download/{job_id}` | Tai video da phan tich |
| `POST` | `/api/auth/login` | Dang nhap (Supabase) |
| `GET` | `/api/auth/me` | Thong tin user |
| `GET` | `/health` | Health check |
| `WS` | `/ws/video-progress/{job_id}` | WebSocket progress real-time |
| `GET` | `/api/video/sse/{job_id}` | SSE progress stream |

**Tong:** 30+ endpoints, 16 routers

---

## Lich su thay doi (Git Commits)

### `37933ed` - UFLD v2 Lane Detection
- Tao moi `lane_detector_ufld.py` - full UFLD v2 architecture
- Thay the BEV classical lane detector bang deep learning
- ResNet-18 backbone + Row classification: ~300 FPS
- Drop-in replacement (cung interface `process_frame()`)

### `0637360` - Complete Model Profile System
- `MODEL_PROFILES` chua du: obj_model, pose_model, seg_model, ufld_model
- dashcam pipeline: profile-based object detection + TensorRT auto-export
- in_cabin pipeline: profile-based DriverMonitorV11 (obj + pose)
- TensorRT optimizer: auto-export .pt -> FP16 .engine voi caching
- Fix `config.py`: default model path `yolov11n.pt` -> `yolo11x.pt`
- Xoa dependencies `celery`, `redis`, `kombu` (khong dung)

### `f8ce69d` - Vietnamese Overlay (PIL)
- Thay toan bo `cv2.putText` bang PIL rendering
- Ho tro dau tieng Viet day du: "HE THONG CANH BAO THONG MINH"
- Font Roboto-Bold, professional HUD layout

### `74bf888` - Fix 6 Critical Pipeline Bugs
1. Object detector tra Vietnamese class names -> downstream expect English
2. Worker doc sai lane result keys
3. Distance estimation type mismatch
4. TTC goi method khong ton tai + velocity luon = 0
5. Risk assessment type mismatch
6. Lane overlay double-blended

### `05ed0c7` - Performance: NOTIFY/LISTEN + FP16
- PostgreSQL `pg_notify` -> worker nhan job tuc thi (khong polling)
- YOLO FP16 inference (half precision)
- Stride-2 lane cache -> giam 50% lane inference
- Ket qua: < 60s cho video 50MB

### `211f48c` - GPU Acceleration
- `cv2.cuda` cho toan bo image processing
- Dual CUDA streams: Object + Lane chay song song
- ThreadPoolExecutor parallel inference

### `0f03d39` - V4 ADAS Pipeline
- BEV lane detection + ByteTrack object tracking
- RiskEngineV4: TTC-based collision warning
- Vietnamese overlay system

---

## Hieu nang (NVIDIA A30 24GB)

| Metric | Gia tri |
|--------|---------|
| Processing speed | **40-60 FPS** (1.5-2x realtime) |
| VRAM usage | ~4-5 GB per worker |
| Video 60s | < 30 giay xu ly |
| Video 50MB | < 60 giay xu ly |
| Lane detection (UFLD) | ~300 FPS |
| Object detection (YOLO) | ~45 FPS |
| TensorRT speedup | 2-3x so voi PyTorch |

---

## Cau truc thu muc chinh

```
BE-ADAS/
  backend/
    app/                    # FastAPI application
      api/                  # 16 routers, 30+ endpoints
      core/                 # Config, auth, middleware
      db/                   # Database models, repositories
      schemas/              # Pydantic schemas
      services/             # Business logic
    perception/             # AI Pipeline (5,900 LOC)
      object/               # YOLOv11x object detection
      lane/                 # UFLD v2 + V4 backup
      driver/               # Driver monitoring (pose)
      distance/             # Monocular distance estimation
      risk/                 # Risk engine (TTC-based)
      engine/               # TensorRT optimizer
      overlay/              # Vietnamese text rendering
      pipeline/             # Full ADAS pipeline
      traffic/              # Traffic sign recognition
    models/                 # AI model weights (.pt, .pth)
    assets/fonts/           # Roboto-Bold.ttf (Vietnamese)
  workers/
    gpu_worker_simple.py    # Main GPU worker (1,414 LOC)
  UBUNTU_DEPLOYMENT.md      # Huong dan deploy
  CHANGELOG.md              # File nay
```

---

## Luu y cho team

1. **UFLD model weight** (`ufld_tusimple.pth`) can train hoac tai pretrained TuSimple. Neu chua co file -> he thong tu fallback dung untrained weights (development mode).

2. **Edge models** (`yolov8n.pt`, `yolov8n-pose.pt`) can tai them neu muon dung `--profile edge`.

3. **Khong dung Redis** - Job queue hoan toan tren PostgreSQL (`pg_notify` + `SELECT FOR UPDATE SKIP LOCKED`).

4. **TensorRT** tu dong export `.pt` -> `.engine` lan dau chay (mat ~2-3 phut). Sau do cache va dung lai.

5. **Font tieng Viet:** `backend/assets/fonts/Roboto-Bold.ttf` - can co de overlay hien thi dung dau.
