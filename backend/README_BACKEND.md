# ADAS Video Analysis System - Scientific Demo

## 🎯 System Goal

A **scientific ADAS demonstration system** for research council evaluation that analyzes REAL driving video content with:

- ✅ Curved lane detection (follows actual road geometry)
- ✅ Object detection (vehicles, pedestrians)
- ✅ Distance estimation to front vehicles
- ✅ Lane departure warning (LDW)
- ✅ Forward collision warning (FCW)
- ✅ Traffic sign recognition (TSR)
- ✅ Driver monitoring (drowsiness detection)

**NO fixed overlays, NO fake lanes, NO hardcoded geometry!**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  - Upload video                                              │
│  - Poll for results                                          │
│  - Play annotated video                                      │
│  - Display warnings synced to timestamp                      │
└─────────────────────────────────────────────────────────────┘
                           │
                    REST API (HTTP)
                           │
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                         │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  API Layer (app/api/video.py)                        │   │
│  │  - POST /api/video/upload                            │   │
│  │  - GET /api/video/result/{job_id}                    │   │
│  │  - GET /api/video/download/{job_id}/{filename}       │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Service Layer (app/services/analysis_service.py)    │   │
│  │  - Job management                                    │   │
│  │  - Background processing                             │   │
│  │  - Calls AI pipeline (ONE ENTRY POINT)               │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                   │
│                    SINGLE CALL                                │
│                           │                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Perception Layer (perception/pipeline/)             │   │
│  │  - process_video(input, output, type, device)        │   │
│  │  - NO FastAPI dependency                             │   │
│  │  - Pure AI/CV logic                                  │   │
│  └──────────────────────────────────────────────────────┘   │
│         │           │           │           │                 │
│    ┌────┴────┐ ┌────┴────┐ ┌───┴────┐ ┌────┴────┐           │
│    │  Lane   │ │ Object  │ │Distance│ │ Driver  │           │
│    │Detector │ │Detector │ │Estimator│ │ Monitor │           │
│    └─────────┘ └─────────┘ └────────┘ └─────────┘           │
└─────────────────────────────────────────────────────────────┘
```

---

## 📂 Folder Structure

```
backend/
├── app/
│   ├── main.py                    # FastAPI application
│   ├── api/
│   │   └── video.py               # REST endpoints
│   ├── services/
│   │   └── analysis_service.py    # Job orchestration
│   └── storage/
│       ├── raw/                   # Uploaded videos
│       └── result/                # Processed videos
│
├── perception/                    # AI PERCEPTION ONLY
│   ├── lane/
│   │   └── lane_detector_v11.py   # Real curved lane detection
│   ├── object/
│   │   └── object_detector_v11.py # YOLOv11 object detection
│   ├── distance/
│   │   └── distance_estimator.py  # Distance & risk estimation
│   ├── driver/
│   │   └── driver_monitor_v11.py  # Driver drowsiness detection
│   ├── traffic/
│   │   └── traffic_sign_v11.py    # Traffic sign recognition
│   └── pipeline/
│       └── video_pipeline_v11.py  # SINGLE ENTRY POINT
│
├── models/                        # YOLOv11 weights
│   └── yolo11n.pt
│
├── requirements.txt
└── README_BACKEND.md
```

---

## 🚀 Installation

### Prerequisites
- Python 3.8+
- pip

### Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Download YOLOv11 model (automatic on first run)
# Or manually:
# wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolo11n.pt -P models/
```

---

## 🎬 Usage

### 1. Start Backend Server

**Windows Server:**
```bash
cd backend/app
python main.py
```

**Or with uvicorn directly:**
```bash
cd backend/app
python -m uvicorn main:app --reload --host 0.0.0.0 --port 52000
```

Server starts at: `https://adas-api.aiotlab.edu.vn/`

API Docs: `https://adas-api.aiotlab.edu.vn/docs`

### 2. Upload Video (Frontend or CLI)

**Using cURL:**

```bash
curl -X POST "https://adas-api.aiotlab.edu.vn/api/video/upload" \
  -F "file=@/path/to/dashcam_video.mp4" \
  -F "video_type=dashcam" \
  -F "device=cpu"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "Video uploaded successfully. Processing started."
}
```

### 3. Check Status

```bash
curl "https://adas-api.aiotlab.edu.vn/api/video/result/{job_id}"
```

**Response (processing):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "created_at": "2025-12-21T10:30:00",
  "updated_at": "2025-12-21T10:30:15"
}
```

**Response (completed):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result_video_url": "/api/video/download/{job_id}/result.mp4",
  "events": [
    {
      "frame": 120,
      "time": 4.0,
      "type": "lane_departure",
      "level": "warning",
      "data": {"direction": "LEFT", "offset": -0.35}
    },
    {
      "frame": 240,
      "time": 8.0,
      "type": "collision_risk",
      "level": "danger",
      "data": {"distance": 12.5, "ttc": 2.1, "vehicle_type": "car"}
    }
  ],
  "stats": {
    "total_frames": 1200,
    "processed_frames": 1200,
    "fps": 30.0,
    "processing_time_seconds": 45.2,
    "processing_fps": 26.5,
    "video_duration_seconds": 40.0,
    "event_count": 2
  }
}
```

### 4. Download Result Video

```bash
curl -O "https://adas-api.aiotlab.edu.vn/api/video/download/{job_id}/result.mp4"
```

---

## 🔬 AI Modules

### 1. Lane Detection
**File:** `perception/lane/lane_detector_v11.py`

**Features:**
- Edge-based lane detection
- Hough transform for line detection
- 2nd order polynomial fitting (y = ax² + bx + c)
- Supports curved roads
- Lane departure warning (offset > 30%)
- Temporal smoothing

**Output:**
- Curved lane overlay (green)
- Lane fill (semi-transparent)
- Departure warning text

### 2. Object Detection
**File:** `perception/object/object_detector_v11.py`

**Model:** YOLOv11n (lightweight, CPU-friendly)

**Classes:**
- car, truck, bus
- motorcycle, bicycle
- person

**Output:**
- Bounding boxes (color-coded)
- Class labels + confidence
- Vehicle/pedestrian counts

### 3. Distance Estimation
**File:** `perception/distance/distance_estimator.py`

**Method:**
- Pinhole camera model
- Bounding box height-based estimation
- Perspective geometry

**Risk Levels:**
- SAFE: > 30m (green)
- CAUTION: 15-30m (orange)
- DANGER: < 15m (red)

**Output:**
- Distance overlay
- Risk classification
- TTC (Time-to-Collision)

### 4. Driver Monitoring
**File:** `perception/driver/driver_monitor_v11.py`

**Technology:** MediaPipe Face Mesh

**Metrics:**
- **EAR** (Eye Aspect Ratio) - eye closure
- **MAR** (Mouth Aspect Ratio) - yawning
- **Head Pose** - pitch, yaw, roll

**Drowsiness Detection:**
- Eyes closed > 20 frames → DROWSY
- Yawning detected → DROWSY
- Head down (pitch < -20°) → DROWSY
- Looking away (|yaw| > 30°) → DISTRACTED

**Output:**
- Facial landmarks overlay
- EAR/MAR metrics
- Drowsiness warning (red)

### 5. Traffic Sign Recognition
**File:** `perception/traffic/traffic_sign_v11.py`

**Model:** YOLOv11n (COCO pretrained)

**Detected Signs:**
- Stop sign
- Traffic light
- (Extensible with custom-trained model for speed limits)

**Output:**
- Sign bounding boxes
- Sign type labels
- Recommended actions

---

## 🎥 Video Types

### Dashcam Video
**Set:** `video_type=dashcam`

**Features:**
- Lane detection
- Object detection
- Distance estimation
- Lane departure warning
- Forward collision warning
- Traffic sign recognition

### In-Cabin Video
**Set:** `video_type=in_cabin`

**Features:**
- Driver face detection
- Eye closure monitoring
- Yawn detection
- Head pose estimation
- Drowsiness alerts

---

## 🔧 Configuration

### Device Selection

**CPU (default):**
```python
device = "cpu"
```

**GPU (if available):**
```python
device = "cuda"
```

### Model Paths

Edit in respective modules or use defaults:
- YOLOv11: Auto-downloads on first run
- MediaPipe: Bundled with package

---

## 📊 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/video/upload` | Upload video for analysis |
| GET | `/api/video/result/{job_id}` | Get processing status and results |
| GET | `/api/video/download/{job_id}/{filename}` | Download processed video |
| DELETE | `/api/video/job/{job_id}` | Delete job and cleanup files |
| GET | `/api/video/health` | Health check |
| GET | `/health` | Global health check |
| GET | `/docs` | Interactive API documentation |

---

## 🧪 Testing

### Test Individual Modules

```bash
cd backend/perception/lane
python lane_detector_v11.py

cd backend/perception/object
python object_detector_v11.py

cd backend/perception/driver
python driver_monitor_v11.py
```

### Test Pipeline

```python
from perception.pipeline.video_pipeline_v11 import process_video

result = process_video(
    input_path="test_video.mp4",
    output_path="result.mp4",
    video_type="dashcam",
    device="cpu"
)

print(result)
```

---

## 📝 Important Notes

### Scientific Constraints
- ✅ If road is curved → lane MUST be curved
- ✅ If video has no lane → system handles gracefully
- ✅ If vehicle moves closer → distance MUST decrease
- ✅ NO fake demo logic
- ✅ All outputs driven by REAL video data

### Architecture Rules
- ✅ Frontend NEVER calls AI modules directly
- ✅ Frontend ONLY communicates with Backend REST API
- ✅ Backend orchestrates AI internally
- ✅ AI perception code is FULLY ISOLATED
- ✅ Backend = FastAPI (REST only, NO WebSocket)
- ✅ AI runs on CPU now, GPU later WITHOUT refactor

---

## 🎓 For Research Council Evaluation

### What to Demonstrate

1. **Upload ANY dashcam video** (not pre-processed)
2. **Show real-time processing** (via polling)
3. **Play annotated result video** with:
   - Curved lanes matching road
   - Object bounding boxes
   - Distance + risk levels
   - Warning overlays
4. **Show event log** synced to video timestamp
5. **Explain architecture** (clean separation)

### Key Points to Emphasize

- **Real Analysis**: No hardcoded geometry, all detections are data-driven
- **Modular Design**: Each AI component is independent
- **Scalable Architecture**: Backend/AI separation allows easy GPU upgrade
- **Scientific Rigor**: Polynomial lane fitting, perspective geometry, facial metrics
- **Production-Ready**: REST API, job management, error handling

---

## 🐛 Troubleshooting

### Issue: YOLOv11 model download fails
**Solution:** Manually download `yolo11n.pt` from Ultralytics GitHub

### Issue: MediaPipe not detecting face
**Solution:** Ensure in-cabin video has clear frontal face view

### Issue: Lane detection poor
**Solution:** 
- Check video quality (resolution, lighting)
- Adjust Canny edge thresholds in `lane_detector_v11.py`

### Issue: Slow processing
**Solution:**
- Use smaller video resolution
- Enable GPU (device="cuda")
- Use lighter model (yolo11n instead of yolo11m)

---

## 📞 Support

For questions or issues:
- Email: adas@research.org
- GitHub: [repo-link]

---

## 📄 License

For research and evaluation purposes only.

---

**Built for ADAS Research Council Evaluation - December 2025**
