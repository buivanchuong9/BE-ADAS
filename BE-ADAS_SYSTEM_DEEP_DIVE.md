# BE-ADAS SYSTEM DEEP DIVE
## Advanced Driver Assistance System - Backend Documentation

> **Version**: 2.0.0  
> **Target**: Version 3.0 Enterprise Upgrade  
> **Date**: January 2, 2026  
> **Author**: Principal Backend Engineer & Software Architect

---

## 1. OVERALL SYSTEM OVERVIEW

### 1.1 Problem Statement

BE-ADAS solves the critical challenge of **automated driving safety analysis** by providing:
- Real-time and offline video analysis for driver safety
- AI-powered detection of dangerous driving conditions
- Enterprise-grade data persistence and analytics

### 1.2 ADAS Features Provided

| Feature | Technology | Status |
|---------|------------|--------|
| **Forward Collision Warning (FCW)** | YOLOv11 + Distance Estimation | ✅ Production |
| **Lane Departure Warning (LDW)** | Geometry-based detection with EMA | ✅ Production |
| **Driver Fatigue Detection (DMS)** | MediaPipe Face Mesh | ✅ Production |
| **Traffic Sign Recognition** | YOLOv11 classification | ✅ Production |
| **Object Detection & Tracking** | YOLOv11 + ByteTrack | ✅ Production |
| **Real-time Streaming** | WebSocket + Frame Processing | ✅ Production |

### 1.3 Target Deployment Environments

```
┌─────────────────────────────────────────────────────────────┐
│  DEPLOYMENT OPTIONS                                          │
├─────────────────────────────────────────────────────────────┤
│  1. Server GPU (Primary)                                    │
│     - Ubuntu 22.04 LTS                                      │
│     - NVIDIA GPU with CUDA 11.8+                            │
│     - SQL Server 2022                                       │
│     - Port: 52000                                           │
│                                                             │
│  2. CPU-Only Server                                         │
│     - Same as above without GPU                             │
│     - Slower inference (~3-5 FPS vs 30+ FPS)                │
│                                                             │
│  3. Edge Devices (Future v3.0)                              │
│     - Jetson Orin / Xavier                                  │
│     - TensorRT optimization required                        │
│                                                             │
│  4. Cloud (AWS/Azure/GCP)                                   │
│     - Container deployment via Docker                       │
│     - Managed SQL Server / PostgreSQL                       │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 Current Version Limitations

| Limitation | Impact | v3.0 Solution |
|------------|--------|---------------|
| SQL Server on Linux complexity | ODBC driver issues | Migrate to PostgreSQL |
| Synchronous DB wrapper | Performance overhead | Native async driver |
| Single-process architecture | Limited scalability | Worker separation |
| No authentication | Security risk | JWT + OAuth2 |
| No rate limiting | DoS vulnerability | Redis-based limiting |
| Hardcoded model paths | Deployment friction | Model registry |

---

## 2. PROJECT STRUCTURE ANALYSIS

### 2.1 Top-Level Directory Structure

```
backend-python/
├── run.py                    # 🚀 ENTRY POINT - Server launcher
├── backend/                  # 📦 Core application package
│   ├── app/                  # FastAPI application
│   │   ├── main.py          # App factory & lifespan
│   │   ├── api/             # 15 API routers
│   │   ├── core/            # Config, logging, exceptions
│   │   ├── db/              # Database layer
│   │   ├── services/        # Business logic
│   │   ├── schemas/         # Pydantic models
│   │   └── storage/         # File storage directories
│   ├── perception/          # 🤖 AI modules
│   │   ├── pipeline/        # Main video pipeline
│   │   ├── object/          # YOLOv11 detector
│   │   ├── lane/            # Lane detection
│   │   ├── driver/          # Driver monitoring
│   │   ├── distance/        # Distance estimation
│   │   ├── traffic/         # Traffic sign recognition
│   │   └── risk/            # Risk assessment
│   └── models/              # AI model weights
├── alembic/                  # Database migrations (disabled)
├── requirements.txt          # Python dependencies
├── Dockerfile               # Container build
├── docker-compose.yml       # Container orchestration
├── database_schema.sql      # SQL Server schema (source of truth)
├── DATABASE_SETUP.md        # Setup instructions
├── SYSTEM_OVERVIEW.md       # Vietnamese documentation
├── .env                     # Environment variables (gitignored)
└── .env.production          # Production config template
```

### 2.2 Control Flow Diagram

```
                        ┌──────────────────┐
                        │    run.py        │
                        │  (Entry Point)   │
                        └────────┬─────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Environment Check     │
                    │   - .env file           │
                    │   - Dependencies        │
                    │   - SQL Server conn     │
                    │   - Database init       │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   uvicorn.run()         │
                    │   app.main:app          │
                    │   --host 0.0.0.0        │
                    │   --port 52000          │
                    └────────────┬────────────┘
                                 │
          ┌──────────────────────▼──────────────────────┐
          │              FastAPI Lifespan               │
          │  ┌─────────────────────────────────────┐   │
          │  │ STARTUP:                             │   │
          │  │  1. init_db() - Create tables        │   │
          │  │  2. get_job_service() - Init worker  │   │
          │  │  3. Log API documentation URL        │   │
          │  └─────────────────────────────────────┘   │
          │  ┌─────────────────────────────────────┐   │
          │  │ SHUTDOWN:                            │   │
          │  │  1. job_service.shutdown()           │   │
          │  │  2. close_db() - Dispose engine      │   │
          │  └─────────────────────────────────────┘   │
          └─────────────────────────────────────────────┘
```

### 2.3 Key Files Explained

#### `run.py` - Entry Point
```python
# Purpose: Production-ready server launcher
# Features:
# - Environment validation  
# - Dependency auto-install
# - SQL Server connection check
# - Database initialization
# - Uvicorn server with proxy headers

# Usage:
python run.py              # Development (port 8000, hot reload)
python run.py --production # Production (port 52000, no reload)
python run.py --port 8080  # Custom port
```

#### `backend/app/main.py` - FastAPI Application
- Creates FastAPI app with OpenAPI documentation
- Configures CORS for production domain (adas-api.aiotlab.edu.vn)
- Registers 15 API routers
- Implements request logging middleware with Cloudflare support
- Defines health check and debug endpoints

#### `database_schema.sql` - Single Source of Truth
- Complete SQL Server schema with 9 tables
- Indexes for performance optimization
- Sample data (admin user, sample vehicle)
- **CRITICAL**: Manual execution required, Alembic disabled

---

## 3. BACKEND ARCHITECTURE

### 3.1 Framework: FastAPI 0.115

```python
# Key FastAPI features used:
app = FastAPI(
    title="ADAS Backend API",
    version="2.0.0",
    lifespan=lifespan,           # Modern lifecycle management
    servers=[                     # Swagger server configuration
        {"url": "https://adas-api.aiotlab.edu.vn"},
        {"url": "http://localhost:52000"}
    ]
)
```

### 3.2 Application Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LIFECYCLE                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [STARTUP] ─────────────────────────────────────────────►  │
│      │                                                      │
│      ├── init_db()                                          │
│      │   └── Create SQLAlchemy engine                       │
│      │   └── Create all tables if not exist                 │
│      │                                                      │
│      ├── get_job_service()                                  │
│      │   └── Initialize ThreadPoolExecutor                  │
│      │   └── Set max_workers from settings                  │
│      │                                                      │
│      └── Log startup message                                │
│                                                             │
│  [RUNNING] ◄─────────────────────────────────────────────►  │
│      │                                                      │
│      ├── Handle HTTP requests                               │
│      ├── Process background jobs                            │
│      └── Manage WebSocket connections                       │
│                                                             │
│  [SHUTDOWN] ◄───────────────────────────────────────────    │
│      │                                                      │
│      ├── job_service.shutdown()                             │
│      │   └── Wait for active jobs to complete               │
│      │                                                      │
│      └── close_db()                                         │
│          └── Dispose engine and connections                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Dependency Injection Pattern

```python
# Database session injection
from app.db.session import get_db

@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)  # Injected per-request
):
    video_service = VideoService(db)
    # ...

# Session lifecycle:
# 1. get_db() creates sync session wrapped in AsyncSessionWrapper
# 2. Session yielded to route handler
# 3. Rollback on exception, close on completion
```

### 3.4 Middleware Stack

| Order | Middleware | Purpose |
|-------|------------|---------|
| 1 | CORS | Cross-origin request handling |
| 2 | Request Logger | Log all requests with Cloudflare headers |
| 3 | FastAPI Exception Handler | Convert errors to JSON responses |

**CORS Configuration (Critical for Swagger UI):**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://adas-api.aiotlab.edu.vn",
        "http://localhost:52000",
        # ... other origins
    ],
    allow_credentials=False,  # MUST be False for file uploads
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3.5 Configuration System

```python
# backend/app/core/config.py
class Settings(BaseSettings):
    # Application
    APP_NAME: str = "ADAS Backend API"
    APP_VERSION: str = "2.0.0"
    
    # Database (SQL Server)
    DB_HOST: str = "localhost"
    DB_PORT: int = 1433
    DB_NAME: str = "adas_production"
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"
    
    # Processing
    MAX_VIDEO_SIZE_MB: int = 500
    MAX_CONCURRENT_JOBS: int = 2
    
    class Config:
        env_file = ".env"
```

---

## 4. API DESIGN

### 4.1 API Endpoint Summary

| Group | Prefix | Endpoints | Status |
|-------|--------|-----------|--------|
| Video Processing | `/api/video` | 5 | ✅ Production |
| Authentication | `/api/auth` | 5 | ⚠️ Mock (dummy JWT) |
| Events & Alerts | `/api/events`, `/api/alerts` | 8 | ✅ Production |
| Trips & Statistics | `/api/trips`, `/api/statistics` | 9 | ✅ Production |
| Streaming | `/api/streaming` | 4 | ✅ Production |
| WebSocket | `/ws/alerts` | 1 | ✅ Production |
| AI Chat | `/api/chat` | 3 | ✅ Production |
| Driver Monitor | `/api/driver` | 4 | ✅ Production |
| Models | `/api/models` | 4 | ⚠️ Partial |
| Dataset | `/api/dataset` | 4 | ⚠️ Mock |
| Detections | `/api/detections` | 3 | ✅ In-memory |
| Settings | `/api/settings` | 6 | ⚠️ Mock |
| Upload/Storage | `/api/upload`, `/api/storage` | 5 | ✅ Production |
| Videos | `/api/videos` | 4 | ✅ In-memory |

### 4.2 Core Video Processing API

```
POST /api/video/upload
├── Input: multipart/form-data
│   ├── file: Video file (mp4, avi, mov)
│   ├── video_type: "dashcam" | "in_cabin"
│   └── device: "cpu" | "cuda"
├── Processing: NON-BLOCKING
│   ├── Validate file (size ≤ 500MB, format)
│   ├── Create VideoJob in database
│   ├── Save to storage/raw/{job_id}/
│   └── Submit to ThreadPoolExecutor
└── Output: VideoJobResponse
    ├── job_id: UUID string
    ├── status: "pending"
    └── video_path: Input file location

GET /api/video/result/{job_id}
├── Input: job_id (path parameter)
├── Processing: Database lookup
└── Output: VideoJobResponse
    ├── status: "pending" | "processing" | "completed" | "failed"
    ├── progress_percent: 0-100
    ├── result_path: Output video location
    └── events: Array of detected events (when completed)

GET /api/video/download/{job_id}/{filename}
├── Input: job_id, filename (path parameters)
├── Validation: Job must be "completed"
└── Output: FileResponse (video/mp4)
```

### 4.3 Error Handling Strategy

```python
# Standard error response format:
{
    "detail": "Error message for client"
}

# HTTP Status Codes:
# 400 - Validation errors (bad input)
# 404 - Resource not found
# 500 - Internal server errors

# Custom exceptions (app/core/exceptions.py):
class ValidationError(Exception): ...
class JobNotFoundError(Exception): ...
class ProcessingError(Exception): ...
```

### 4.4 API Versioning Strategy (Current State)

**PROBLEM**: No versioning implemented

```
# Current:
/api/video/upload        ← No version prefix

# Recommended for v3.0:
/api/v3/video/upload     ← Versioned
/api/v2/video/upload     ← Maintain backwards compatibility
```

### 4.5 Problems with Current API Design

| Issue | Impact | Recommendation |
|-------|--------|----------------|
| No API versioning | Breaking changes affect all clients | Implement `/api/v3/` prefix |
| Mixed response formats | Inconsistent client handling | Standardize envelope pattern |
| No pagination on lists | Memory issues with large datasets | Add limit/offset parameters |
| Mock authentication | Security vulnerability | Implement proper JWT/OAuth2 |
| No rate limiting | DoS susceptibility | Add Redis-based limiter |
| Sync DB operations | Request blocking | Full async migration |

---

## 5. AI / ADAS PIPELINE

### 5.1 Video Processing Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    VIDEO PROCESSING PIPELINE                 │
└─────────────────────────────────────────────────────────────┘

[1. UPLOAD]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  VideoService.validate_video()                               │
│  - Check file size (≤ 500MB)                                │
│  - Validate format (mp4, avi, mov)                          │
│  - Check content-type header                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
[2. DATABASE]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  VideoJobRepository.create()                                 │
│  - Generate UUID job_id                                     │
│  - Insert row with status="pending"                         │
│  - Set video_path, video_filename                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
[3. STORAGE]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Save file to: backend/storage/raw/{job_id}/filename.mp4    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
[4. SUBMIT TO EXECUTOR]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  JobService.submit_job()                                     │
│  - Update status → "processing"                             │
│  - ThreadPoolExecutor.submit(process_video_sync)            │
│  - Return immediately (NON-BLOCKING)                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼ (Background Thread)
[5. AI PIPELINE]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  VideoPipelineV11.process_video()                            │
│                                                              │
│  FOR EACH FRAME:                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ [DASHCAM]                                              │  │
│  │  1. LaneDetectorV11.process_frame()                   │  │
│  │     - Edge detection (Canny)                          │  │
│  │     - Hough line transform                            │  │
│  │     - Polynomial fitting                              │  │
│  │     - EMA temporal smoothing                          │  │
│  │     - Lane departure check                            │  │
│  │                                                        │  │
│  │  2. ObjectDetectorV11.process_frame()                 │  │
│  │     - YOLOv11 inference                               │  │
│  │     - Filter ADAS classes (car, truck, person, etc)   │  │
│  │     - ByteTrack multi-object tracking                 │  │
│  │                                                        │  │
│  │  3. DistanceEstimator.process_detection()             │  │
│  │     - Monocular distance estimation                   │  │
│  │     - TTC (Time-to-Collision) calculation             │  │
│  │     - Risk level: SAFE/CAUTION/DANGER                 │  │
│  │                                                        │  │
│  │  4. TrafficSignV11.process_frame()                    │  │
│  │     - Detect speed limits, stop signs, warnings       │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ [IN-CABIN]                                             │  │
│  │  1. DriverMonitorV11.process_frame()                  │  │
│  │     - MediaPipe Face Mesh                             │  │
│  │     - EAR (Eye Aspect Ratio) calculation              │  │
│  │     - MAR (Mouth Aspect Ratio) calculation            │  │
│  │     - Drowsiness detection                            │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  OUTPUTS:                                                    │
│  - Annotated video → storage/result/{job_id}/filename.mp4   │
│  - Events list → Database (safety_events table)             │
│  - Statistics → Processing time, FPS, event counts          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
[6. CALLBACK]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  JobService._on_job_complete()                               │
│  - Update VideoJob status → "completed"                     │
│  - Set result_path, processing_time_seconds                 │
│  - Store all events via SafetyEventRepository               │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 AI Module Details

| Module | File | Model | Purpose |
|--------|------|-------|---------|
| ObjectDetectorV11 | `perception/object/object_detector_v11.py` | YOLOv11 (yolo11n.pt) | Detect vehicles, pedestrians |
| LaneDetectorV11 | `perception/lane/lane_detector_v11.py` | Geometry-based | Lane line detection |
| DistanceEstimator | `perception/distance/distance_estimator.py` | Calibration-based | Monocular distance |
| DriverMonitorV11 | `perception/driver/driver_monitor_v11.py` | MediaPipe Face Mesh | Drowsiness detection |
| TrafficSignV11 | `perception/traffic/traffic_sign_v11.py` | YOLOv11 | Sign recognition |
| ByteTracker | `perception/object/object_tracker.py` | Kalman Filter | Multi-object tracking |

### 5.3 GPU Utilization Strategy

```python
# Device selection in settings:
DEFAULT_DEVICE: str = "cpu"  # or "cuda"

# YOLOv11 inference:
results = self.model(
    frame,
    device=self.device,  # "cpu" or "cuda"
    conf=self.conf_threshold,
    verbose=False
)

# Performance comparison:
# CPU (Intel i7): ~3-5 FPS
# GPU (NVIDIA RTX 3060): ~30-60 FPS
```

### 5.4 Bottlenecks and Performance Risks

| Bottleneck | Impact | Mitigation |
|------------|--------|------------|
| YOLOv11 inference on CPU | Very slow (3-5 FPS) | Require CUDA GPU |
| Video I/O (read/write) | Disk-bound | Use SSD storage |
| Large video files | Memory pressure | Streaming processing (future) |
| Single ThreadPoolExecutor | Limited concurrency | Distributed workers (v3.0) |
| Synchronous DB wrapper | Blocking on queries | Native async driver |
| MediaPipe initialization | ~2s startup per video | Keep instance alive |

---

## 6. DATABASE LAYER (CURRENT)

### 6.1 Original SQL Server Design

```sql
-- Database: adas_production
-- Driver: ODBC Driver 18 for SQL Server
-- Connection: mssql+pyodbc://sa:password@localhost:1433/adas_production

-- 9 Core Tables:
1. users          -- User accounts (admin, operator, viewer, driver)
2. vehicles       -- Vehicle fleet management
3. trips          -- Driving session records
4. video_jobs     -- Video processing jobs
5. safety_events  -- Detected safety events (FCW, LDW, DMS)
6. driver_states  -- Driver monitoring snapshots
7. traffic_signs  -- Traffic sign detections
8. alerts         -- Real-time alert queue
9. model_versions -- AI model version tracking
```

### 6.2 Why SQL Server Causes Issues on Linux

| Problem | Root Cause | Impact |
|---------|------------|--------|
| ODBC Driver 18 installation | Complex Linux package setup | Deployment friction |
| TrustServerCertificate | Required for local dev | Security configuration |
| No native async driver | pyodbc is synchronous | Wrapped in executor |
| License costs | SQL Server licensing | Enterprise expense |
| Container complexity | Large mssql image (~1.5GB) | Slow builds |

### 6.3 Current AsyncSessionWrapper Pattern

```python
# backend/app/db/session.py
class AsyncSessionWrapper:
    """Wraps sync pyodbc session for async FastAPI"""
    
    def __init__(self, sync_session):
        self.sync_session = sync_session
    
    async def execute(self, statement):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            self.sync_session.execute, 
            statement
        )
    
    async def commit(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.sync_session.commit)
```

**PROBLEM**: Every DB operation runs in thread pool = overhead

### 6.4 Database Schema Relationships

```
┌─────────┐      ┌─────────┐      ┌───────────┐
│  users  │──1:N─►│  trips  │──1:N─►│video_jobs │
└─────────┘      └────┬────┘      └─────┬─────┘
                      │                  │
                      │ 1:N              │ 1:N
                      ▼                  ▼
               ┌──────────────┐   ┌──────────────┐
               │safety_events │   │driver_states │
               └──────────────┘   └──────────────┘
                      │
                      │ 1:N
                      ▼
               ┌──────────────┐
               │   alerts     │
               └──────────────┘
```

---

## 7. SUPABASE / POSTGRES MIGRATION PLAN

### 7.1 Database Layer Refactoring

```python
# CURRENT (SQL Server with sync wrapper):
DATABASE_URL = "mssql+pyodbc://..."
sync_engine = create_engine(DATABASE_URL)
# Wrapped in AsyncSessionWrapper

# TARGET (PostgreSQL with native async):
DATABASE_URL = "postgresql+asyncpg://..."
async_engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(async_engine)
```

### 7.2 Proposed PostgreSQL Schema

```sql
-- Migration to PostgreSQL syntax
CREATE TABLE video_jobs (
    id SERIAL PRIMARY KEY,
    job_id UUID UNIQUE DEFAULT gen_random_uuid(),
    trip_id INTEGER REFERENCES trips(id) ON DELETE SET NULL,
    video_filename VARCHAR(255) NOT NULL,
    video_path VARCHAR(500) NOT NULL,
    video_size_mb REAL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- ... rest of columns
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Use JSONB for flexible metadata
ALTER TABLE safety_events 
    ALTER COLUMN meta_data TYPE JSONB USING meta_data::jsonb;
```

### 7.3 Async Driver Stack

```
┌─────────────────────────────────────────┐
│           FastAPI (async)               │
└───────────────────┬─────────────────────┘
                    │
┌───────────────────▼─────────────────────┐
│       SQLAlchemy 2.0 (async)            │
│   - AsyncSession                        │
│   - async_sessionmaker                  │
└───────────────────┬─────────────────────┘
                    │
┌───────────────────▼─────────────────────┐
│          asyncpg driver                 │
│   - Native async PostgreSQL             │
│   - Connection pooling                  │
└───────────────────┬─────────────────────┘
                    │
┌───────────────────▼─────────────────────┐
│      PostgreSQL / Supabase              │
└─────────────────────────────────────────┘
```

### 7.4 Connection Pooling Configuration

```python
# Recommended PostgreSQL settings:
async_engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,           # Min connections
    max_overflow=30,        # Extra connections under load
    pool_timeout=30,        # Wait time for connection
    pool_recycle=3600,      # Recycle connections after 1 hour
    pool_pre_ping=True,     # Verify connection health
)
```

### 7.5 Migration Strategy Using Alembic

```bash
# Step 1: Generate migration from current schema
alembic revision --autogenerate -m "Initial PostgreSQL schema"

# Step 2: Review and fix generated migration
# - Change NVARCHAR → VARCHAR
# - Change DATETIME → TIMESTAMPTZ
# - Change IDENTITY → SERIAL

# Step 3: Create new PostgreSQL database
createdb adas_production_pg

# Step 4: Run migration
alembic upgrade head

# Step 5: Data migration script (custom)
python scripts/migrate_data_mssql_to_pg.py

# Step 6: Update .env
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/adas_production_pg
```

---

## 8. CONFIGURATION & ENVIRONMENT MANAGEMENT

### 8.1 Environment Files

| File | Purpose | Git Status |
|------|---------|------------|
| `.env` | Local development config | ❌ gitignored |
| `.env.production` | Production template | ✅ committed |
| `.env.example` | Safe template for sharing | ✅ should create |

### 8.2 Key Environment Variables

```bash
# Database (CRITICAL - contains passwords)
DB_HOST=localhost
DB_PORT=1433
DB_NAME=adas_production
DB_USER=sa
DB_PASSWORD=YourStrong@Passw0rd
DB_DRIVER=ODBC Driver 18 for SQL Server

# Application
ENVIRONMENT=production  # or development
DEBUG=False
HOST=0.0.0.0
PORT=52000

# Security
SECRET_KEY=<min-32-character-random-string>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# AI
YOLO_MODEL_PATH=./backend/models/yolov11n.pt
DEFAULT_DEVICE=cuda  # or cpu

# Processing
MAX_VIDEO_SIZE_MB=500
MAX_CONCURRENT_JOBS=2

# CORS
CORS_ORIGINS=https://adas-api.aiotlab.edu.vn,http://localhost:3000
```

### 8.3 Security Risks in Current Setup

| Risk | Current State | Recommendation |
|------|---------------|----------------|
| `.env` in git | Properly gitignored ✅ | Maintain |
| Default passwords | Hardcoded in code | Move to env vars |
| SECRET_KEY exposure | Default value in config.py | Generate unique per deployment |
| No secrets manager | Direct env vars | Use HashiCorp Vault / AWS Secrets |
| CORS wildcard | Limited origins ✅ | Maintain strict list |

### 8.4 Secrets Management Recommendations

```python
# v3.0: Integrate with external secrets manager

# Option 1: HashiCorp Vault
from hvac import Client
vault = Client(url='https://vault.internal:8200')
secret = vault.secrets.kv.v2.read_secret_version(path='adas/db')
DB_PASSWORD = secret['data']['data']['password']

# Option 2: AWS Secrets Manager
import boto3
client = boto3.client('secretsmanager')
secret = client.get_secret_value(SecretId='adas/production/db')
DB_PASSWORD = json.loads(secret['SecretString'])['password']

# Option 3: Environment injection at runtime
# Use Docker secrets or Kubernetes secrets
```

---

## 9. ERROR HANDLING & LOGGING

### 9.1 Current Error Handling Patterns

```python
# Route-level try/catch pattern:
@router.post("/upload")
async def upload_video(...):
    try:
        # Business logic
        return result
    except HTTPException:
        raise  # Re-raise FastAPI exceptions
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

### 9.2 Logging Structure

```python
# backend/app/core/logging.py
def setup_logging(log_level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            # Future: Add file handler, JSON formatter
        ]
    )

# Request logging in main.py middleware:
logger.info(
    f"📨 {request.method} {request.url.path} | "
    f"Client: {client_ip} | "
    f"CF-Ray: {cf_ray}"
)
```

### 9.3 Improvements for Enterprise Readiness

| Current | Recommended |
|---------|-------------|
| Console output only | Structured JSON logs |
| No log rotation | Daily rotation with retention |
| No correlation IDs | Request ID tracing |
| No centralized logging | ELK Stack / CloudWatch |
| Error stack traces in response | Sanitized error messages |

```python
# Recommended logging configuration:
LOG_CONFIG = {
    "version": 1,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(timestamp)s %(level)s %(name)s %(message)s %(request_id)s"
        }
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/adas.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 30
        }
    }
}
```

---

## 10. DEPLOYMENT STRATEGY

### 10.1 Current Deployment Approach

```bash
# Production deployment on Ubuntu 22.04:
cd /home/user/backend-python
source .venv/bin/activate
python run.py --production

# Expected output:
# 🚗 ADAS BACKEND - Advanced Driver Assistance System
# 📍 Domain: https://adas-api.aiotlab.edu.vn:52000
# 🔧 Version: 2.0.0
# 🏭 Mode: PRODUCTION
```

### 10.2 Why Docker is Problematic

| Issue | Details |
|-------|---------|
| ODBC Driver | Requires custom Dockerfile with Microsoft repo |
| GPU Access | nvidia-container-toolkit complexity |
| SQL Server | 1.5GB+ mssql image, compatibility issues |
| File permissions | Volume mount ownership problems |
| Debugging | Harder to inspect running container |

### 10.3 Native Ubuntu Deployment (Recommended)

```bash
#!/bin/bash
# deploy.sh - Native deployment without sudo

# 1. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Install ODBC Driver 18 (requires sudo once)
# curl ... | sudo apt-get install msodbcsql18

# 4. Configure environment
cp .env.production .env
# Edit .env with production values

# 5. Initialize database
sqlcmd -S localhost -U sa -P password -i database_schema.sql

# 6. Run with systemd (create service file)
# /etc/systemd/system/adas-backend.service

# 7. Start service
systemctl --user start adas-backend
```

### 10.4 Systemd Service File

```ini
# /etc/systemd/system/adas-backend.service
[Unit]
Description=ADAS Backend API
After=network.target mssql-server.service

[Service]
Type=simple
User=adas
WorkingDirectory=/home/adas/backend-python
Environment="PATH=/home/adas/backend-python/.venv/bin"
ExecStart=/home/adas/backend-python/.venv/bin/python run.py --production
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 10.5 Nginx Reverse Proxy Configuration

```nginx
# /etc/nginx/sites-available/adas-api
server {
    listen 443 ssl http2;
    server_name adas-api.aiotlab.edu.vn;

    ssl_certificate /etc/letsencrypt/live/adas-api.aiotlab.edu.vn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/adas-api.aiotlab.edu.vn/privkey.pem;

    client_max_body_size 500M;  # Match MAX_VIDEO_SIZE_MB

    location / {
        proxy_pass http://127.0.0.1:52000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for video upload
        proxy_connect_timeout 600;
        proxy_send_timeout 600;
        proxy_read_timeout 600;
    }

    # WebSocket support
    location /ws/ {
        proxy_pass http://127.0.0.1:52000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 11. SCALABILITY & PERFORMANCE

### 11.1 Current Scalability Limitations

```
┌─────────────────────────────────────────────────────────────┐
│                 CURRENT ARCHITECTURE                         │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         Single Process (uvicorn)                     │   │
│  │  ┌─────────────────┐  ┌────────────────────────┐   │   │
│  │  │   FastAPI App   │  │  ThreadPoolExecutor    │   │   │
│  │  │   (main loop)   │  │  (max_workers=2)       │   │   │
│  │  └─────────────────┘  └────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              SQL Server (single instance)            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  LIMITATIONS:                                                │
│  - Only 2 concurrent video processing jobs                  │
│  - Single database connection pool                          │
│  - No horizontal scaling                                    │
│  - No load balancing                                        │
│  - No caching layer                                         │
└─────────────────────────────────────────────────────────────┘
```

### 11.2 GPU Bottleneck Analysis

```
Video Processing Performance:

┌───────────────────────────────────────────────────────────┐
│ Device        │ YOLOv11 FPS │ Total Pipeline │ 1min Video │
├───────────────┼─────────────┼────────────────┼────────────┤
│ CPU (i7-10th) │ 3-5 FPS     │ 2-3 FPS        │ ~10 min    │
│ RTX 3060      │ 45-60 FPS   │ 25-35 FPS      │ ~2 min     │
│ RTX 4090      │ 120+ FPS    │ 60-80 FPS      │ ~45 sec    │
│ A100          │ 200+ FPS    │ 100+ FPS       │ ~30 sec    │
└───────────────────────────────────────────────────────────┘

Bottleneck Distribution (CPU mode):
- YOLOv11 inference:     60%
- Lane detection:        15%
- Video I/O:             15%
- Distance calculation:   5%
- Other:                  5%
```

### 11.3 Multi-Worker Strategy (v3.0)

```
┌─────────────────────────────────────────────────────────────┐
│                  v3.0 SCALABLE ARCHITECTURE                  │
│                                                              │
│  ┌──────────────────┐     ┌──────────────────┐             │
│  │  API Server 1    │     │  API Server 2    │             │
│  │  (uvicorn)       │     │  (uvicorn)       │             │
│  └────────┬─────────┘     └────────┬─────────┘             │
│           │                        │                         │
│           └───────────┬────────────┘                         │
│                       │                                      │
│           ┌───────────▼───────────┐                         │
│           │     Redis Queue       │                         │
│           │  (job distribution)   │                         │
│           └───────────┬───────────┘                         │
│                       │                                      │
│     ┌─────────────────┼─────────────────┐                   │
│     │                 │                 │                   │
│  ┌──▼──────────┐ ┌────▼─────────┐ ┌────▼─────────┐         │
│  │ AI Worker 1 │ │ AI Worker 2  │ │ AI Worker 3  │         │
│  │ (GPU 0)     │ │ (GPU 1)      │ │ (CPU)        │         │
│  └─────────────┘ └──────────────┘ └──────────────┘         │
│                                                              │
│           ┌───────────────────────────┐                     │
│           │  PostgreSQL (Primary)     │                     │
│           │     ↓ Replication         │                     │
│           │  PostgreSQL (Replica)     │                     │
│           └───────────────────────────┘                     │
│                                                              │
│           ┌───────────────────────────┐                     │
│           │     Redis Cache           │                     │
│           │  (session, results)       │                     │
│           └───────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

### 11.4 Async vs Sync Tradeoffs

| Operation | Current | Recommendation |
|-----------|---------|----------------|
| HTTP handling | Async ✅ | Keep |
| Database queries | Sync wrapped | Native async |
| File I/O | aiofiles ✅ | Keep |
| AI inference | Sync (CPU-bound) | Keep in thread pool |
| WebSocket | Async ✅ | Keep |

---

## 12. SECURITY CONSIDERATIONS

### 12.1 Current API Security

| Aspect | Current State | Risk Level |
|--------|---------------|------------|
| Authentication | Mock JWT | 🔴 Critical |
| Authorization | Hardcoded roles | 🔴 Critical |
| Rate limiting | None | 🟡 High |
| Input validation | Pydantic ✅ | 🟢 Low |
| SQL injection | SQLAlchemy ORM ✅ | 🟢 Low |
| XSS | JSON responses ✅ | 🟢 Low |
| CORS | Strict origins ✅ | 🟢 Low |
| File upload | Size/type validation ✅ | 🟡 Medium |

### 12.2 Authentication/Authorization Strategy (v3.0)

```python
# Recommended: OAuth2 + JWT
from fastapi.security import OAuth2PasswordBearer
from jose import jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v3/auth/token")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

# Role-based access control
def require_role(allowed_roles: List[str]):
    async def role_checker(user: User = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker

# Usage:
@router.delete("/job/{job_id}")
async def delete_job(
    job_id: str,
    user: User = Depends(require_role(["admin", "operator"]))
):
    ...
```

### 12.3 Rate Limiting Implementation

```python
# Using slowapi with Redis backend
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@router.post("/upload")
@limiter.limit("5/minute")  # 5 uploads per minute per IP
async def upload_video(request: Request, ...):
    ...
```

### 12.4 Input Validation Risks

| Input | Current Validation | Risk |
|-------|-------------------|------|
| Video file | Size + content-type | Path traversal in filename |
| job_id | UUID format | None if properly validated |
| video_type | Enum check | None |
| device | String check | Injection in shell commands |

```python
# Recommended: Strict filename sanitization
import re
from pathlib import Path

def sanitize_filename(filename: str) -> str:
    # Remove path components
    filename = Path(filename).name
    # Remove special characters
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    # Limit length
    return filename[:255]
```

---

## 13. VERSION 3.0 ENTERPRISE ROADMAP

### 13.1 Architectural Changes Required

```
┌─────────────────────────────────────────────────────────────┐
│                 v3.0 TARGET ARCHITECTURE                     │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    API GATEWAY                          │ │
│  │  - Kong / AWS API Gateway                               │ │
│  │  - Rate limiting, Auth, Routing                         │ │
│  └─────────────────────────┬──────────────────────────────┘ │
│                            │                                 │
│  ┌─────────────────────────▼──────────────────────────────┐ │
│  │              MICROSERVICES LAYER                        │ │
│  │                                                         │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │ │
│  │  │ Auth        │ │ Video       │ │ Analytics   │       │ │
│  │  │ Service     │ │ Service     │ │ Service     │       │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘       │ │
│  │                                                         │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │ │
│  │  │ Alert       │ │ Storage     │ │ AI Worker   │       │ │
│  │  │ Service     │ │ Service     │ │ Service     │       │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘       │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            │                                 │
│  ┌─────────────────────────▼──────────────────────────────┐ │
│  │              MESSAGE QUEUE                              │ │
│  │  - RabbitMQ / Redis Streams                             │ │
│  │  - Job distribution, Event bus                          │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            │                                 │
│  ┌─────────────────────────▼──────────────────────────────┐ │
│  │              DATA LAYER                                 │ │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐          │ │
│  │  │ PostgreSQL│  │   Redis   │  │    S3     │          │ │
│  │  │ (Primary) │  │  (Cache)  │  │ (Storage) │          │ │
│  │  └───────────┘  └───────────┘  └───────────┘          │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 13.2 Modularization Plan

| Current Module | v3.0 Service | Responsibilities |
|----------------|--------------|------------------|
| `app/api/auth.py` | Auth Service | JWT, OAuth2, RBAC |
| `app/api/video.py` | Video Service | Upload, metadata, job management |
| `perception/*` | AI Worker Service | Video processing, model inference |
| `app/api/events_alerts.py` | Alert Service | Event storage, notifications |
| `app/api/trips_stats.py` | Analytics Service | Statistics, reporting |
| `app/storage/` | Storage Service | File management, S3 integration |

### 13.3 AI Worker Separation

```python
# Separate AI Worker Process
# ai_worker/main.py

import redis
from perception.pipeline.video_pipeline_v11 import process_video

redis_client = redis.Redis()

def main():
    while True:
        # Wait for job from queue
        job_data = redis_client.blpop("video_jobs", timeout=30)
        
        if job_data:
            job = json.loads(job_data[1])
            
            # Process video
            result = process_video(
                input_path=job["input_path"],
                output_path=job["output_path"],
                video_type=job["video_type"],
                device=job["device"]
            )
            
            # Store result
            redis_client.set(f"result:{job['job_id']}", json.dumps(result))
            
            # Notify completion
            redis_client.publish("job_complete", job["job_id"])

if __name__ == "__main__":
    main()
```

### 13.4 Event-Driven Processing

```python
# Event publisher
from redis import Redis

class EventBus:
    def __init__(self):
        self.redis = Redis()
    
    async def publish(self, event_type: str, data: dict):
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.redis.publish("adas_events", json.dumps(message))

# Usage:
event_bus = EventBus()

# When video processing completes:
await event_bus.publish("video.processed", {
    "job_id": job_id,
    "events_count": len(events),
    "processing_time": processing_time
})

# When alert is detected:
await event_bus.publish("alert.critical", {
    "type": "forward_collision",
    "vehicle_id": vehicle_id,
    "driver_id": driver_id
})
```

### 13.5 Enterprise-Grade API Design

```yaml
# OpenAPI 3.1 specification structure
openapi: 3.1.0
info:
  title: ADAS Enterprise API
  version: 3.0.0

paths:
  /api/v3/video/upload:
    post:
      summary: Upload video for processing
      security:
        - bearerAuth: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              $ref: '#/components/schemas/VideoUploadRequest'
      responses:
        '202':
          description: Accepted for processing
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/VideoJobResponse'
        '400':
          $ref: '#/components/responses/ValidationError'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '429':
          $ref: '#/components/responses/RateLimited'

components:
  schemas:
    VideoJobResponse:
      type: object
      properties:
        data:
          type: object
          properties:
            job_id:
              type: string
              format: uuid
            status:
              type: string
              enum: [pending, processing, completed, failed]
        meta:
          type: object
          properties:
            request_id:
              type: string
            timestamp:
              type: string
              format: date-time
```

---

## 14. SUMMARY & CRITICAL ACTION ITEMS

### 14.1 Technical Debt Inventory

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 🔴 P0 | Implement real authentication | 2 weeks | Security |
| 🔴 P0 | Add rate limiting | 1 week | Security |
| 🟡 P1 | Migrate to PostgreSQL | 3 weeks | Maintainability |
| 🟡 P1 | Native async database driver | 2 weeks | Performance |
| 🟡 P1 | API versioning | 1 week | Maintainability |
| 🟢 P2 | Structured JSON logging | 3 days | Observability |
| 🟢 P2 | Secrets management | 1 week | Security |
| 🟢 P3 | Microservices separation | 2 months | Scalability |

### 14.2 Version 3.0 Milestones

```
Q1 2026: Foundation
├── PostgreSQL migration complete
├── Native async database operations
├── Real JWT authentication
├── Rate limiting implemented
└── API v3 with versioning

Q2 2026: Scalability
├── Redis job queue
├── Separate AI worker process
├── Multi-GPU support
├── Horizontal scaling tested
└── Kubernetes deployment

Q3 2026: Enterprise Features
├── Full RBAC implementation
├── Audit logging
├── Multi-tenant support
├── SLA monitoring
└── Disaster recovery

Q4 2026: Commercial Ready
├── SOC2 compliance
├── Performance optimization
├── Documentation complete
├── SDK for clients
└── Commercial support
```

---

## 15. APPENDIX

### A. Command Reference

```bash
# Development
python run.py                    # Start dev server (port 8000)
python run.py --port 8080       # Custom port

# Production
python run.py --production      # Start production (port 52000)
python run.py --skip-checks     # Skip startup validation

# Database
sqlcmd -S localhost -U sa -P password -i database_schema.sql

# Testing (future)
pytest backend/tests/
pytest --cov=app backend/tests/
```

### B. API Quick Reference

```
# Health Check
GET /health

# Video Upload & Processing
POST /api/video/upload
GET  /api/video/result/{job_id}
GET  /api/video/download/{job_id}/{filename}
DELETE /api/video/job/{job_id}

# Events & Alerts
GET  /api/events/list
POST /api/events
GET  /api/alerts/latest

# Statistics
GET /api/statistics/summary
GET /api/statistics/detections-by-class

# WebSocket
WS /ws/alerts
```

### C. Configuration Checklist

```markdown
[ ] .env file created with production values
[ ] DB_PASSWORD changed from default
[ ] SECRET_KEY is 32+ random characters
[ ] CORS_ORIGINS includes only trusted domains
[ ] MAX_CONCURRENT_JOBS set based on GPU memory
[ ] YOLO_MODEL_PATH points to valid model
[ ] Nginx configured with SSL certificate
[ ] Systemd service file installed
[ ] Firewall rules configured (port 52000)
[ ] Log rotation configured
```

---

**Document End**

*This document is the authoritative reference for BE-ADAS system architecture.*
*Last updated: January 2, 2026*
