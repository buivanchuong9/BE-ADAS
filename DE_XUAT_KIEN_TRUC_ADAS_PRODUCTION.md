# ĐỀ XUẤT KIẾN TRÚC HỆ THỐNG ADAS PRODUCTION-READY
## Hệ thống ADAS Backend Cấp Doanh Nghiệp - Triển khai Windows Server

**Ngày:** 26/12/2025  
**Phiên bản:** 1.0  
**Mục đích:** Nâng cấp từ hệ thống demo sang hệ thống sản xuất thương mại

---

## MỤC LỤC

1. [Phân tích hệ thống hiện tại](#1-phân-tích-hệ-thống-hiện-tại)
2. [Kiến trúc mới đề xuất](#2-kiến-trúc-mới-đề-xuất)
3. [Database Schema - SQL Server](#3-database-schema---sql-server)
4. [Cấu trúc thư mục mới](#4-cấu-trúc-thư-mục-mới)
5. [Module responsibilities](#5-module-responsibilities)
6. [Pipeline xử lý video](#6-pipeline-xử-lý-video)
7. [Context-aware Intelligence](#7-context-aware-intelligence)
8. [Real-time communication](#8-real-time-communication)
9. [Roadmap triển khai](#9-roadmap-triển-khai)
10. [Considerations cho production](#10-considerations-cho-production)

---

## 1. PHÂN TÍCH HỆ THỐNG HIỆN TẠI

### 1.1 Điểm mạnh
✅ **Kiến trúc phân tầng rõ ràng:**
- API layer (FastAPI) tách biệt khỏi AI logic
- Perception modules được tổ chức riêng biệt
- Service layer để orchestration

✅ **AI/CV modules hoạt động:**
- Lane detection với polynomial fitting
- Object detection dùng YOLOv11
- Distance estimation
- Driver monitoring với MediaPipe
- Traffic sign detection

✅ **API đã có structure cơ bản:**
- Video upload/processing
- Events/alerts
- Trips/stats
- Authentication (basic)
- WebSocket streaming

### 1.2 Hạn chế nghiêm trọng (CẦN SỬA GẤP)

❌ **Database - CRITICAL:**
- **KHÔNG CÓ database thật** - Chỉ có in-memory storage (`models.py`)
- Tất cả data mất khi restart
- Không phù hợp cho production
- Không có migrations, không có relationships

❌ **Video Processing - BLOCKING:**
- Xử lý video ĐỒNG BỘ, block API request
- Không có background jobs thật sự
- Không có queue system
- Không scale được

❌ **AI Modules - KHÔNG ỔN ĐỊNH:**
- **Lane detection:** xử lý từng frame độc lập → jitter, flickering
- **Không có temporal tracking** → quyết định thiếu context
- **Không có lane memory** → mất lanes khi bị che khuất
- Threshold cứng nhắc, không adaptive

❌ **Thiếu Context Engine:**
- Quyết định theo từng frame, không có cửa sổ thời gian
- Không đánh giá traffic density, road conditions
- Dễ false alarms

❌ **Không có Alert Management:**
- WebSocket chỉ stream frames, không stream alerts thông minh
- Không có prioritization
- Không có text-to-speech
- Không có alert history

❌ **Không production-ready:**
- Không có structured logging với request_id
- Không có error handling đúng chuẩn
- Không có monitoring/metrics
- Không có rate limiting, authentication nghiêm túc
- Hardcoded paths, configs

---

## 2. KIẾN TRÚC MỚI ĐỀ XUẤT

### 2.1 Tổng quan Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                              │
│  - Web Dashboard (React/Vue)                                     │
│  - Mobile App                                                    │
│  - Third-party integrations                                      │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                      API GATEWAY LAYER                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  FastAPI Application (main.py)                           │   │
│  │  - CORS, Rate Limiting, Authentication Middleware        │   │
│  │  - Request Validation, Error Handling                    │   │
│  │  - Structured Logging (request_id, job_id)               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  API Endpoints:                                                  │
│  ├── /api/v1/auth          (JWT Authentication)                 │
│  ├── /api/v1/videos        (Upload, Status, Results)            │
│  ├── /api/v1/jobs          (Job Management)                     │
│  ├── /api/v1/trips         (Trip Analytics)                     │
│  ├── /api/v1/events        (Safety Events)                      │
│  ├── /api/v1/alerts        (Alert Management)                   │
│  ├── /api/v1/analytics     (Dashboard Statistics)               │
│  └── /ws/alerts            (WebSocket Real-time Alerts)         │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                   BUSINESS LOGIC LAYER                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Service Layer (services/)                               │   │
│  │  ├── video_service.py      - Video upload, validation    │   │
│  │  ├── job_service.py        - Job lifecycle management    │   │
│  │  ├── event_service.py      - Event logging, querying     │   │
│  │  ├── alert_service.py      - Alert generation, priority  │   │
│  │  ├── trip_service.py       - Trip analytics              │   │
│  │  └── notification_service.py - WebSocket, TTS            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Job Queue & Async Processing                            │   │
│  │  ├── AsyncIO Event Loop                                  │   │
│  │  ├── Thread Pool for CPU-bound tasks                     │   │
│  │  └── Future: Redis/Celery integration ready              │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                 AI INFERENCE LAYER                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Perception Pipeline (perception/)                       │   │
│  │  ├── pipeline_orchestrator.py - Main coordinator         │   │
│  │  ├── lane/                                               │   │
│  │  │   ├── lane_detector.py                                │   │
│  │  │   └── lane_tracker.py       (NEW - Temporal tracking) │   │
│  │  ├── object/                                             │   │
│  │  │   ├── object_detector.py                              │   │
│  │  │   └── object_tracker.py      (NEW - Multi-object)     │   │
│  │  ├── traffic/                                            │   │
│  │  │   └── traffic_sign_detector.py                        │   │
│  │  ├── driver/                                             │   │
│  │  │   └── driver_monitor.py                               │   │
│  │  └── distance/                                           │   │
│  │      └── distance_estimator.py                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Context Engine (NEW)                                    │   │
│  │  ├── context_analyzer.py - Temporal window analysis      │   │
│  │  ├── scene_understanding.py - Traffic density, quality   │   │
│  │  └── risk_predictor.py   - Proactive risk assessment     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Decision Engine (NEW)                                   │   │
│  │  ├── alert_generator.py   - Generate alerts with context │   │
│  │  ├── risk_scorer.py       - Calculate risk levels        │   │
│  │  └── explanation_engine.py - Explain decisions           │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                    DATA LAYER                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Database (SQL Server)                                   │   │
│  │  ├── SQLAlchemy Async ORM                                │   │
│  │  ├── PyODBC Driver                                       │   │
│  │  └── Alembic Migrations                                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  Tables:                                                         │
│  ├── users                                                       │
│  ├── vehicles                                                    │
│  ├── trips                                                       │
│  ├── video_jobs                                                  │
│  ├── safety_events                                               │
│  ├── traffic_signs                                               │
│  ├── driver_states                                               │
│  ├── alerts                                                      │
│  └── alert_history                                               │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  File Storage                                            │   │
│  │  ├── Raw videos                                          │   │
│  │  ├── Processed videos                                    │   │
│  │  ├── Frame snapshots                                     │   │
│  │  └── Logs                                                │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Technology Stack

**Backend Framework:**
- FastAPI 0.115+ (async support)
- Uvicorn (ASGI server)
- Pydantic v2 (data validation)

**Database:**
- Microsoft SQL Server 2019+
- SQLAlchemy 2.0+ (async mode)
- PyODBC 5.0+
- Alembic (migrations)

**AI/CV:**
- YOLOv11 (Ultralytics)
- MediaPipe (driver monitoring)
- OpenCV (video processing)
- NumPy (numerical operations)

**Async/Concurrency:**
- asyncio (async I/O)
- ThreadPoolExecutor (CPU-bound tasks)
- Future support: Redis + Celery

**Real-time Communication:**
- WebSocket (FastAPI native)
- Server-Sent Events (fallback)

**Monitoring & Logging:**
- Structured logging (JSON format)
- Request ID tracking
- Performance metrics

**Security:**
- JWT authentication
- RBAC (Role-Based Access Control)
- API rate limiting
- Input validation

---

## 3. DATABASE SCHEMA - SQL SERVER

### 3.1 Entity Relationship Diagram

```
┌──────────────┐         ┌──────────────┐
│    users     │         │   vehicles   │
│──────────────│         │──────────────│
│ id (PK)      │         │ id (PK)      │
│ username     │         │ plate_number │
│ password_hash│         │ model        │
│ role         │         │ user_id (FK) │───┐
│ email        │         │ created_at   │   │
│ created_at   │         └──────────────┘   │
└──────┬───────┘                            │
       │                                     │
       │ 1                                   │
       │                                     │
       │ N                                   │
       ↓                                     │
┌──────────────┐                            │
│    trips     │                            │
│──────────────│                            │
│ id (PK)      │                            │
│ driver_id(FK)│────────────────────────────┘
│ vehicle_id(FK)──────────────────────────┐
│ start_time   │                          │
│ end_time     │                          │
│ distance_km  │                          │
│ duration_min │                          │
│ safety_score │                          │
│ status       │                          │
│ created_at   │                          │
└──────┬───────┘                          │
       │                                   │
       │ 1                                 │
       │                                   │
       │ N                                 │
       ↓                                   │
┌──────────────┐                          │
│  video_jobs  │                          │
│──────────────│                          │
│ id (PK)      │                          │
│ job_id (UUID)│                          │
│ trip_id (FK) │                          │
│ filename     │                          │
│ video_type   │                          │
│ status       │                          │
│ input_path   │                          │
│ output_path  │                          │
│ device       │                          │
│ created_at   │                          │
│ started_at   │                          │
│ completed_at │                          │
│ error_msg    │                          │
└──────┬───────┘                          │
       │                                   │
       │ 1                                 │
       │                                   │
       │ N                                 │
       ↓                                   │
┌──────────────────┐                      │
│  safety_events   │                      │
│──────────────────│                      │
│ id (PK)          │                      │
│ trip_id (FK)     │                      │
│ video_job_id (FK)│                      │
│ vehicle_id (FK)  │──────────────────────┘
│ event_type       │ (lane_departure, collision_warning, etc.)
│ severity         │ (info, warning, critical)
│ risk_score       │ (0.0-1.0)
│ timestamp        │
│ frame_number     │
│ time_to_event    │ (seconds, for predictions)
│ description      │
│ context_data     │ (JSON: lane quality, traffic, etc.)
│ snapshot_path    │
│ created_at       │
└──────────────────┘

┌──────────────────┐
│  traffic_signs   │
│──────────────────│
│ id (PK)          │
│ trip_id (FK)     │
│ video_job_id (FK)│
│ sign_type        │ (speed_limit, stop, warning, etc.)
│ sign_value       │ (e.g., "50" for speed limit 50)
│ confidence       │
│ timestamp        │
│ frame_number     │
│ bbox_x1, y1, x2, y2 │
│ created_at       │
└──────────────────┘

┌──────────────────┐
│  driver_states   │
│──────────────────│
│ id (PK)          │
│ trip_id (FK)     │
│ video_job_id (FK)│
│ timestamp        │
│ frame_number     │
│ fatigue_score    │ (0.0-1.0)
│ distraction_score│ (0.0-1.0)
│ eyes_closed      │ (boolean)
│ yawning          │ (boolean)
│ head_pose_yaw    │
│ head_pose_pitch  │
│ head_pose_roll   │
│ created_at       │
└──────────────────┘

┌──────────────────┐
│     alerts       │
│──────────────────│
│ id (PK)          │
│ trip_id (FK)     │
│ safety_event_id (FK)│
│ alert_type       │
│ severity         │ (info, warning, critical)
│ message          │
│ tts_text         │ (text for speech)
│ timestamp        │
│ acknowledged     │ (boolean)
│ acknowledged_at  │
│ delivered        │ (sent via WebSocket)
│ played           │ (TTS played)
│ created_at       │
└──────────────────┘
```

### 3.2 Database Migration Strategy

**Phase 1: Setup Infrastructure**
1. Install SQL Server drivers (PyODBC)
2. Configure connection strings
3. Setup Alembic
4. Create initial migration

**Phase 2: Schema Creation**
1. Create tables với proper constraints
2. Add indexes for performance
3. Add foreign keys
4. Add check constraints

**Phase 3: Data Migration**
- Không có data cũ (in-memory only)
- Seed initial data (admin user, test vehicles)

### 3.3 Connection Configuration

```python
# config/database.py
DATABASE_URL = "mssql+pyodbc://username:password@server/database?driver=ODBC+Driver+17+for+SQL+Server"

# Environment variables
DB_HOST=localhost
DB_PORT=1433
DB_NAME=adas_production
DB_USER=adas_user
DB_PASSWORD=secure_password
DB_DRIVER=ODBC Driver 17 for SQL Server
```

### 3.4 Key Indexes

```sql
-- Performance critical indexes
CREATE INDEX idx_trips_driver_vehicle ON trips(driver_id, vehicle_id);
CREATE INDEX idx_trips_start_time ON trips(start_time DESC);
CREATE INDEX idx_safety_events_trip ON safety_events(trip_id, timestamp);
CREATE INDEX idx_safety_events_severity ON safety_events(severity, timestamp DESC);
CREATE INDEX idx_video_jobs_status ON video_jobs(status, created_at);
CREATE INDEX idx_alerts_trip_severity ON alerts(trip_id, severity, timestamp DESC);
```

---

## 4. CẤU TRÚC THƯ MỤC MỚI

```
backend-python/
├── alembic/                          # Database migrations
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app entry point
│   │   │
│   │   ├── api/                      # API endpoints (v1)
│   │   │   ├── __init__.py
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py           # JWT authentication
│   │   │   │   ├── videos.py         # Video upload/management
│   │   │   │   ├── jobs.py           # Job status/control
│   │   │   │   ├── trips.py          # Trip CRUD
│   │   │   │   ├── events.py         # Safety events
│   │   │   │   ├── alerts.py         # Alert management
│   │   │   │   ├── analytics.py      # Dashboard stats
│   │   │   │   └── websocket.py      # WebSocket alerts
│   │   │   │
│   │   │   └── dependencies.py       # Shared dependencies
│   │   │
│   │   ├── core/                     # Core configuration
│   │   │   ├── __init__.py
│   │   │   ├── config.py             # Settings (Pydantic BaseSettings)
│   │   │   ├── security.py           # JWT, hashing
│   │   │   ├── logging.py            # Structured logging
│   │   │   └── exceptions.py         # Custom exceptions
│   │   │
│   │   ├── db/                       # Database layer
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # SQLAlchemy base
│   │   │   ├── session.py            # Async session
│   │   │   ├── models/               # SQLAlchemy models
│   │   │   │   ├── __init__.py
│   │   │   │   ├── user.py
│   │   │   │   ├── vehicle.py
│   │   │   │   ├── trip.py
│   │   │   │   ├── video_job.py
│   │   │   │   ├── safety_event.py
│   │   │   │   ├── traffic_sign.py
│   │   │   │   ├── driver_state.py
│   │   │   │   └── alert.py
│   │   │   │
│   │   │   └── repositories/         # Data access layer
│   │   │       ├── __init__.py
│   │   │       ├── base.py
│   │   │       ├── trip_repo.py
│   │   │       ├── event_repo.py
│   │   │       └── job_repo.py
│   │   │
│   │   ├── schemas/                  # Pydantic schemas
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── trip.py
│   │   │   ├── video.py
│   │   │   ├── event.py
│   │   │   └── alert.py
│   │   │
│   │   ├── services/                 # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── video_service.py      # Video validation, storage
│   │   │   ├── job_service.py        # Job lifecycle
│   │   │   ├── event_service.py      # Event logging
│   │   │   ├── alert_service.py      # Alert generation
│   │   │   ├── trip_service.py       # Trip analytics
│   │   │   ├── notification_service.py # WebSocket, TTS
│   │   │   └── ai_orchestrator.py    # AI pipeline coordinator
│   │   │
│   │   └── utils/                    # Utilities
│   │       ├── __init__.py
│   │       ├── video.py              # Video utilities
│   │       ├── validators.py
│   │       └── helpers.py
│   │
│   ├── perception/                   # AI/CV modules (unchanged structure)
│   │   ├── __init__.py
│   │   │
│   │   ├── core/                     # NEW - Core AI abstractions
│   │   │   ├── __init__.py
│   │   │   ├── base_detector.py      # Abstract base class
│   │   │   ├── model_loader.py       # Model management
│   │   │   └── inference_engine.py   # CPU/GPU abstraction
│   │   │
│   │   ├── lane/
│   │   │   ├── __init__.py
│   │   │   ├── lane_detector.py      # REFACTORED
│   │   │   └── lane_tracker.py       # NEW - Temporal tracking
│   │   │
│   │   ├── object/
│   │   │   ├── __init__.py
│   │   │   ├── object_detector.py    # REFACTORED
│   │   │   └── object_tracker.py     # NEW - SORT/DeepSORT
│   │   │
│   │   ├── traffic/
│   │   │   ├── __init__.py
│   │   │   └── traffic_sign_detector.py # IMPROVED
│   │   │
│   │   ├── driver/
│   │   │   ├── __init__.py
│   │   │   └── driver_monitor.py     # IMPROVED - Temporal
│   │   │
│   │   ├── distance/
│   │   │   ├── __init__.py
│   │   │   └── distance_estimator.py
│   │   │
│   │   ├── context/                  # NEW - Context Engine
│   │   │   ├── __init__.py
│   │   │   ├── context_analyzer.py   # Time window analysis
│   │   │   ├── scene_understanding.py # Traffic density, etc.
│   │   │   └── temporal_buffer.py    # Sliding window buffer
│   │   │
│   │   ├── decision/                 # NEW - Decision Engine
│   │   │   ├── __init__.py
│   │   │   ├── risk_predictor.py     # Risk scoring
│   │   │   ├── alert_generator.py    # Alert logic
│   │   │   └── explanation_engine.py # Explain decisions
│   │   │
│   │   └── pipeline/
│   │       ├── __init__.py
│   │       ├── video_pipeline.py     # REFACTORED - Main orchestrator
│   │       └── frame_processor.py    # NEW - Frame-level processing
│   │
│   ├── tests/                        # Unit & integration tests
│   │   ├── __init__.py
│   │   ├── test_api/
│   │   ├── test_services/
│   │   ├── test_perception/
│   │   └── conftest.py
│   │
│   └── scripts/                      # Utility scripts
│       ├── init_db.py
│       ├── seed_data.py
│       └── migrate_db.py
│
├── config/                           # Configuration files
│   ├── development.env
│   ├── production.env
│   └── logging.yaml
│
├── storage/                          # File storage
│   ├── videos/
│   │   ├── raw/
│   │   └── processed/
│   ├── snapshots/
│   └── logs/
│
├── models/                           # AI model weights
│   ├── yolo11n.pt
│   ├── yolo11s-seg.pt
│   └── README.md
│
├── docs/                             # Documentation
│   ├── API.md
│   ├── DEPLOYMENT.md
│   └── ARCHITECTURE.md
│
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
└── README.md
```

---

## 5. MODULE RESPONSIBILITIES

### 5.1 API Layer (`app/api/`)

**Nhiệm vụ:**
- Nhận HTTP requests
- Validate input (Pydantic)
- Authentication/Authorization
- Call service layer
- Return responses
- Error handling

**KHÔNG làm:**
- Business logic
- Database access trực tiếp
- AI inference

### 5.2 Service Layer (`app/services/`)

**video_service.py:**
- Validate video format, size, duration
- Generate unique filenames
- Save to storage
- Create video_job record in DB

**job_service.py:**
- Create và manage job lifecycle
- Update job status (PENDING → PROCESSING → COMPLETED/FAILED)
- Orchestrate async video processing
- Retry logic cho failed jobs

**event_service.py:**
- Log safety events to database
- Query events with filters
- Generate event statistics
- Link events to trips

**alert_service.py:**
- Generate alerts from events
- Prioritize alerts (deduplication)
- Store alert history
- Integrate với WebSocket service

**trip_service.py:**
- CRUD operations for trips
- Calculate trip statistics
- Generate safety scores
- Trip analytics

**notification_service.py:**
- Manage WebSocket connections
- Broadcast alerts to connected clients
- Text-to-speech integration
- Alert delivery tracking

**ai_orchestrator.py:**
- Interface between services and AI pipeline
- Submit jobs to AI pipeline
- Handle AI pipeline callbacks
- Manage AI resources

### 5.3 Perception Layer (`perception/`)

**lane/lane_tracker.py (NEW):**
```python
class LaneTracker:
    """
    Temporal lane tracking with memory and smoothing.
    
    Features:
    - Lane memory (remember last known lanes)
    - Confidence scoring
    - Exponential Moving Average smoothing
    - Handle occlusions
    """
    def __init__(self):
        self.left_lane_history = []   # Last N detections
        self.right_lane_history = []
        self.confidence_history = []
        self.ema_alpha = 0.3
        
    def update(self, left_lane, right_lane, confidence):
        """Update with new detection, apply smoothing"""
        
    def get_smoothed_lanes(self):
        """Return temporally smoothed lanes"""
        
    def is_lane_valid(self):
        """Check if current lane estimate is reliable"""
```

**object/object_tracker.py (NEW):**
```python
class ObjectTracker:
    """
    Multi-object tracking across frames.
    
    Features:
    - Assign persistent IDs to objects
    - Track object motion (trajectory)
    - Predict object positions
    - Handle occlusions
    """
    def __init__(self, method='sort'):  # SORT or DeepSORT
        self.trackers = []
        self.next_id = 1
        
    def update(self, detections):
        """Update tracks with new detections"""
        
    def get_tracked_objects(self):
        """Return objects with IDs and trajectories"""
```

**context/context_analyzer.py (NEW):**
```python
class ContextAnalyzer:
    """
    Analyze driving context over time window (3-5 seconds).
    
    Provides:
    - Lane quality assessment
    - Traffic density estimation
    - Relative vehicle motion trends
    - Driver attention state
    - Road type inference
    """
    def __init__(self, window_size=5.0):  # 5 seconds
        self.temporal_buffer = TemporalBuffer(window_size)
        
    def update(self, frame_data):
        """Add new frame data to buffer"""
        
    def analyze_lane_quality(self):
        """Assess lane detection quality over time"""
        return {
            'confidence': 0.85,
            'stability': 0.90,
            'visibility': 'good'
        }
        
    def analyze_traffic_density(self):
        """Estimate traffic density"""
        return {
            'vehicle_count_avg': 5,
            'density': 'medium',
            'closest_vehicle_distance': 15.0
        }
        
    def analyze_driver_state(self):
        """Aggregate driver state over window"""
        return {
            'fatigue_level': 'low',
            'attention': 'focused',
            'alertness_score': 0.92
        }
```

**decision/risk_predictor.py (NEW):**
```python
class RiskPredictor:
    """
    Predict risky situations BEFORE they occur.
    
    Uses context from ContextAnalyzer to make informed decisions.
    """
    def __init__(self):
        self.context_analyzer = ContextAnalyzer()
        
    def predict_collision_risk(self, objects, ego_speed):
        """
        Predict collision risk.
        
        Returns:
        - risk_score: 0.0-1.0
        - time_to_collision: seconds (if applicable)
        - explanation: human-readable reason
        """
        
    def predict_lane_departure_risk(self, lane_data, vehicle_offset):
        """Predict lane departure risk"""
        
    def should_alert(self, event_type, risk_score, context):
        """
        Intelligent alerting decision.
        
        Considers:
        - Risk level
        - Recent alert history (avoid spam)
        - Context quality
        - Driver state
        """
```

### 5.4 Database Layer (`app/db/`)

**models/:** SQLAlchemy ORM models
- Define table structures
- Relationships
- Constraints

**repositories/:** Data access patterns
- Abstract database operations
- Provide clean interface to services
- Handle transactions

**session.py:** Async session management
```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for database sessions"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
```

---

## 6. PIPELINE XỬ LÝ VIDEO

### 6.1 Video Upload Flow

```
Client uploads video
       ↓
API receives file (validate size, format)
       ↓
video_service saves to storage
       ↓
job_service creates VideoJob (status=PENDING)
       ↓
Return job_id to client immediately (non-blocking)
       ↓
Background task: ai_orchestrator.submit_job()
       ↓
Update job status to PROCESSING
       ↓
perception.pipeline.process_video()
       ↓
Frame-by-frame processing with context
       ↓
Log events to database in batches
       ↓
Generate annotated video
       ↓
Update job status to COMPLETED
       ↓
Client polls /api/v1/jobs/{job_id} for status
```

### 6.2 Frame Processing Pipeline

```python
for frame_idx, frame in enumerate(video_frames):
    # 1. Run AI detections
    lanes = lane_tracker.update(lane_detector.detect(frame))
    objects = object_tracker.update(object_detector.detect(frame))
    signs = traffic_sign_detector.detect(frame)
    driver = driver_monitor.analyze(frame) if in_cabin else None
    
    # 2. Update context
    context_analyzer.update({
        'frame_idx': frame_idx,
        'timestamp': frame_idx / fps,
        'lanes': lanes,
        'objects': objects,
        'signs': signs,
        'driver': driver
    })
    
    # 3. Every 3-5 seconds, analyze context and make decisions
    if frame_idx % (fps * 3) == 0:  # Every 3 seconds
        context = context_analyzer.get_context()
        
        # 4. Risk prediction
        risks = risk_predictor.analyze(context)
        
        # 5. Generate alerts if needed
        for risk in risks:
            if risk['score'] > threshold:
                alert = alert_generator.create_alert(risk, context)
                
                # 6. Store event in database
                event_service.log_event(alert)
                
                # 7. Send via WebSocket
                notification_service.broadcast_alert(alert)
                
                # 8. TTS alert
                notification_service.speak(alert['tts_text'])
```

### 6.3 Async Job Processing

```python
# app/services/ai_orchestrator.py

class AIOrchestrator:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.active_jobs = {}
    
    async def submit_job(self, job_id: str, video_path: str):
        """Submit video processing job (async)"""
        
        # Update status to PROCESSING
        await job_service.update_status(job_id, "PROCESSING")
        
        # Run in thread pool (CPU-bound)
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            self.executor,
            self._process_video_sync,
            job_id,
            video_path
        )
        
        # Store future
        self.active_jobs[job_id] = future
        
        # Await completion (non-blocking for API)
        try:
            result = await future
            await job_service.update_status(job_id, "COMPLETED")
            return result
        except Exception as e:
            await job_service.update_status(job_id, "FAILED", error=str(e))
            raise
    
    def _process_video_sync(self, job_id, video_path):
        """Synchronous video processing (runs in thread)"""
        from perception.pipeline.video_pipeline import process_video
        return process_video(video_path, job_id=job_id)
```

---

## 7. CONTEXT-AWARE INTELLIGENCE

### 7.1 Temporal Buffer

```python
class TemporalBuffer:
    """Sliding window buffer for temporal analysis"""
    
    def __init__(self, window_size_seconds: float = 5.0, fps: float = 30):
        self.window_size = window_size_seconds
        self.fps = fps
        self.max_frames = int(window_size_seconds * fps)
        self.buffer = deque(maxlen=self.max_frames)
    
    def add(self, frame_data: dict):
        """Add frame data with timestamp"""
        self.buffer.append(frame_data)
    
    def get_window(self, duration: float = None):
        """Get data from last N seconds"""
        if duration is None:
            return list(self.buffer)
        n_frames = int(duration * self.fps)
        return list(self.buffer)[-n_frames:]
```

### 7.2 Context Metrics

**Lane Quality:**
- Confidence score (average over window)
- Detection stability (variance in lane position)
- Visibility (percentage of frames with detected lanes)

**Traffic Density:**
- Average vehicle count
- Closest vehicle distance
- Traffic flow (vehicles moving vs stationary)

**Driver State:**
- Fatigue trend (increasing/decreasing)
- Attention consistency
- Anomaly detection (sudden head movements)

**Environmental Inference:**
- Road type (highway vs city)
- Day/night (brightness analysis)
- Weather conditions (visibility, lane clarity)

### 7.3 Smart Alerting Logic

```python
def should_generate_alert(event_type, risk_score, context, alert_history):
    """
    Intelligent alert decision.
    
    Avoids:
    - False positives from single-frame detections
    - Alert spam (repeated alerts for same issue)
    - Alerts during low-confidence periods
    """
    
    # Minimum risk threshold
    if risk_score < 0.6:
        return False
    
    # Check context quality
    if context['lane_quality']['confidence'] < 0.5:
        return False  # Don't alert if lane detection is poor
    
    # Check recent alert history (cooldown)
    recent_alerts = get_recent_alerts(event_type, last_n_seconds=10)
    if len(recent_alerts) > 0:
        return False  # Already alerted recently
    
    # Check if risk is escalating
    risk_trend = analyze_risk_trend(event_type, window=5)
    if risk_trend == 'increasing':
        return True  # Alert on escalating risk
    
    # Critical events always alert
    if risk_score > 0.9:
        return True
    
    return False
```

---

## 8. REAL-TIME COMMUNICATION

### 8.1 WebSocket Implementation

```python
# app/api/v1/websocket.py

from fastapi import WebSocket, WebSocketDisconnect
from typing import Set

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast_alert(self, alert: dict):
        """Broadcast alert to all connected clients"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(alert)
            except:
                disconnected.add(connection)
        
        # Clean up disconnected
        for conn in disconnected:
            self.active_connections.remove(conn)

manager = ConnectionManager()

@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

### 8.2 Alert Message Format

```json
{
  "alert_id": "uuid",
  "type": "collision_warning",
  "severity": "critical",
  "timestamp": "2025-12-26T10:30:45.123Z",
  "risk_score": 0.92,
  "time_to_event": 2.5,
  "message": "Collision risk detected - vehicle ahead decelerating",
  "tts_text": "Cảnh báo va chạm phía trước",
  "context": {
    "closest_vehicle_distance": 12.5,
    "relative_speed": -15.0,
    "lane_quality": "good",
    "traffic_density": "medium"
  },
  "actions": ["slow_down", "maintain_lane"],
  "frame_number": 1234,
  "snapshot_url": "/api/v1/snapshots/uuid.jpg"
}
```

### 8.3 Text-to-Speech Integration

```python
# app/services/notification_service.py

import pyttsx3  # Cross-platform TTS

class NotificationService:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 150)  # Speed
        self.engine.setProperty('volume', 0.9)
        
        # Vietnamese voice if available
        voices = self.engine.getProperty('voices')
        for voice in voices:
            if 'vietnamese' in voice.name.lower():
                self.engine.setProperty('voice', voice.id)
                break
    
    def speak(self, text: str):
        """Convert text to speech (non-blocking)"""
        self.engine.say(text)
        self.engine.runAndWait()
    
    async def speak_async(self, text: str):
        """Async TTS"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.speak, text)
```

---

## 9. ROADMAP TRIỂN KHAI

### Phase 1: Database Migration (1 tuần)
**Mục tiêu:** Chuyển từ in-memory sang SQL Server

✅ **Tasks:**
1. Setup SQL Server (local hoặc Docker)
2. Install PyODBC, SQLAlchemy async
3. Create database models (SQLAlchemy)
4. Setup Alembic migrations
5. Create initial migration
6. Test connection
7. Create repositories
8. Migrate API endpoints to use database

**Deliverables:**
- Working SQL Server connection
- All tables created with proper schemas
- CRUD operations working
- Data persists across restarts

---

### Phase 2: Async Job Processing (1 tuần)
**Mục tiêu:** Video processing không block API

✅ **Tasks:**
1. Refactor video processing to background
2. Implement job queue (asyncio + ThreadPool)
3. Job status tracking in database
4. Error handling and retry logic
5. Progress tracking
6. API endpoints for job management

**Deliverables:**
- Upload returns immediately
- Processing happens in background
- Job status can be queried
- Failed jobs are retried

---

### Phase 3: Temporal AI Modules (2 tuần)
**Mục tiêu:** AI modules với temporal tracking

✅ **Tasks:**
1. Implement LaneTracker with EMA smoothing
2. Implement ObjectTracker (SORT/ByteTrack)
3. Refactor DriverMonitor for temporal analysis
4. Add confidence scoring to all modules
5. Testing and validation

**Deliverables:**
- Stable lane detection (no jitter)
- Objects tracked across frames với IDs
- Driver state aggregated over time
- Reduced false positives

---

### Phase 4: Context Engine (1 tuần)
**Mục tiêu:** Context-aware decision making

✅ **Tasks:**
1. Implement TemporalBuffer
2. Implement ContextAnalyzer
3. Add context metrics (lane quality, traffic density, etc.)
4. Integrate with pipeline
5. Testing

**Deliverables:**
- Context analysis working
- Metrics collected over time windows
- Context data available for decisions

---

### Phase 5: Decision & Alert Engine (1 tuần)
**Mục tiêu:** Intelligent risk prediction and alerting

✅ **Tasks:**
1. Implement RiskPredictor
2. Implement AlertGenerator with smart logic
3. Alert prioritization and deduplication
4. Store alerts in database
5. Testing with real scenarios

**Deliverables:**
- Risk scores calculated
- Alerts generated intelligently
- No alert spam
- Explainable decisions

---

### Phase 6: Real-time Communication (3 ngày)
**Mục tiêu:** WebSocket và TTS alerts

✅ **Tasks:**
1. WebSocket endpoint implementation
2. ConnectionManager for client management
3. Alert broadcasting
4. TTS integration (pyttsx3)
5. Vietnamese language support
6. Testing

**Deliverables:**
- WebSocket working
- Alerts pushed to clients in real-time
- TTS announcements working
- Multi-client support

---

### Phase 7: API Hardening (1 tuần)
**Mục tiêu:** Production-ready API

✅ **Tasks:**
1. JWT authentication implementation
2. Role-based access control
3. Rate limiting
4. Structured logging với request_id
5. Error handling standardization
6. Input validation improvements
7. API versioning (/api/v1)
8. Documentation (OpenAPI/Swagger)

**Deliverables:**
- Secure authentication
- All endpoints protected
- Proper error responses
- Comprehensive logging
- API documentation

---

### Phase 8: Testing & Optimization (1 tuần)
**Mục tiêu:** Performance và stability

✅ **Tasks:**
1. Unit tests for all modules
2. Integration tests
3. Load testing
4. Memory leak detection
5. Performance optimization
6. Database query optimization
7. Video processing optimization

**Deliverables:**
- Test coverage > 80%
- No memory leaks
- Performance benchmarks met
- System stable under load

---

### Phase 9: Deployment Preparation (3 ngày)
**Mục tiêu:** Production deployment ready

✅ **Tasks:**
1. Docker configuration for Windows Server
2. Environment configuration
3. Database backup/restore procedures
4. Monitoring setup
5. Deployment documentation
6. Rollback procedures

**Deliverables:**
- Docker images built
- Deployment guide
- Monitoring in place
- System ready for production

---

**TỔNG THỜI GIAN: 8-9 tuần**

---

## 10. CONSIDERATIONS CHO PRODUCTION

### 10.1 Performance

**Video Processing:**
- Batch frame processing khi có thể
- Use CUDA nếu có GPU
- Video decoding optimization (hardware acceleration)
- Memory management (release frames sau khi process)

**Database:**
- Connection pooling
- Index optimization
- Query optimization (avoid N+1)
- Batch inserts for events

**API:**
- Response caching cho static data
- Pagination cho large datasets
- Rate limiting để tránh abuse

### 10.2 Scalability

**Hiện tại (Phase 1):**
- Single server
- ThreadPoolExecutor
- Async I/O

**Future (Phase 2):**
- Redis for job queue
- Celery workers
- Load balancer
- Multiple API instances
- Shared storage (NFS/S3)

### 10.3 Security

**Authentication:**
- JWT tokens với expiry
- Refresh tokens
- Password hashing (bcrypt)

**Authorization:**
- Role-based access (admin, analyst, driver)
- Endpoint-level permissions

**Input Validation:**
- File size limits
- Video format validation
- SQL injection prevention (ORM)
- XSS prevention

**Data Protection:**
- Sensitive data encryption at rest
- HTTPS in production
- Secure password storage

### 10.4 Monitoring

**Application Metrics:**
- Request count, latency
- Error rates
- Job processing time
- Queue depth

**System Metrics:**
- CPU, Memory, Disk usage
- GPU utilization
- Network I/O

**Business Metrics:**
- Videos processed per day
- Events detected
- Alert distribution
- User activity

**Logging:**
```python
{
  "timestamp": "2025-12-26T10:30:45.123Z",
  "level": "INFO",
  "request_id": "uuid",
  "job_id": "uuid",
  "user_id": "user_123",
  "endpoint": "/api/v1/videos/upload",
  "message": "Video uploaded successfully",
  "metadata": {
    "filename": "dashcam_20251226.mp4",
    "size_mb": 125.5,
    "duration_s": 300
  }
}
```

### 10.5 Error Handling

**API Errors:**
```python
{
  "success": false,
  "error": {
    "code": "INVALID_VIDEO_FORMAT",
    "message": "Video format not supported. Allowed: mp4, avi, mov",
    "details": {
      "filename": "video.mkv",
      "detected_format": "mkv"
    },
    "timestamp": "2025-12-26T10:30:45.123Z",
    "request_id": "uuid"
  }
}
```

**Job Failures:**
- Automatic retry (max 3 attempts)
- Exponential backoff
- Error logging to database
- Notification to admins

### 10.6 Data Retention

**Videos:**
- Raw: 30 days
- Processed: 90 days
- Snapshots: 180 days

**Database:**
- Events: 1 year
- Trips: 2 years
- Alerts: 6 months
- Logs: 90 days

**Archival:**
- Compress old videos
- Move to cold storage
- Database partitioning by date

### 10.7 Disaster Recovery

**Backups:**
- Database: Daily full + hourly incremental
- Videos: Weekly to external storage
- Configuration: Version controlled (Git)

**Recovery:**
- Documented restore procedures
- Regular testing (monthly)
- RTO: 4 hours
- RPO: 1 hour

---

## KẾT LUẬN

Đây là một kế hoạch refactor toàn diện để chuyển hệ thống ADAS từ demo sang production-ready system.

**Điểm nhấn chính:**

1. **Database:** SQLite → SQL Server với schema chuyên nghiệp
2. **Async Processing:** Blocking → True async background jobs
3. **AI Stability:** Frame-by-frame → Temporal tracking với context
4. **Intelligence:** Simple rules → Context-aware risk prediction
5. **Communication:** Polling → WebSocket real-time alerts
6. **Architecture:** Monolithic demo → Layered enterprise system

**Tiếp theo:**
1. Review kiến trúc này
2. Confirm database schema
3. Bắt đầu Phase 1 (Database Migration)
4. Tiến hành từng phase một cách có kiểm soát

Hệ thống sau khi hoàn thành sẽ:
- Phù hợp triển khai thương mại
- Đủ chất lượng cho nghiên cứu khoa học (NCKH)
- Stable và scalable
- Auditable và explainable
- Production-ready cho Windows Server

**Bạn có muốn tôi bắt đầu implement Phase 1 (Database Migration) không?**
