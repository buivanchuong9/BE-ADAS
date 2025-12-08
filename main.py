# ADAS Backend - Production Ready FastAPI
# Version 3.0.0 - Competition Build

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import uvicorn
from typing import List
import json
import logging
from datetime import datetime
from contextlib import asynccontextmanager

# Core infrastructure
from core.config import get_settings
from core.responses import APIResponse, ErrorCode
from core.exceptions import register_exception_handlers
from core.logging_config import setup_logging, get_logger

# Database
from database import get_db, engine
from models import Base

# Services
from services.enhanced_services import (
    CameraService,
    DriverService,
    DetectionService,
    AlertService,
)
from services.realtime_aggregator import RealTimeDataAggregator

# Schemas
from schemas import (
    CameraCreate,
    CameraResponse,
    DriverCreate,
    DriverResponse,
    TripCreate,
    TripResponse,
    EventCreate,
    EventResponse,
    AIModelResponse,
    AIModelCreate,
    AnalyticsResponse,
)

# API routers
from api.upload.router import router as upload_router
from api.inference.router import router as inference_router
# Training endpoints removed per request (training feature disabled)
from api.dataset.router import router as dataset_router
from api.alerts.router import router as alerts_router
from api.detections.router import router as detections_router
from api.models.router import router as models_router
from api.websocket_inference import router as ws_router
from api.video_upload import router as video_upload_router  # NEW: Video upload API
from api.driver_monitoring.router import router as driver_monitor_router  # NEW v4.0: Driver monitoring
from api.analytics import router as analytics_router  # Analytics for dashboard
# Auto-learning APIs removed (feature disabled)

# 🆕 ADAS API routers
from api.adas.router import router as adas_router
from api.adas.websocket import router as adas_ws_router

# Get settings
settings = get_settings()

# Setup logging
setup_logging()
logger = get_logger(__name__)

# Initialize real-time aggregator
realtime_aggregator = RealTimeDataAggregator()


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("🚀 Starting ADAS Backend API...")
    logger.info(f"Environment: {'Production' if not settings.DEBUG else 'Development'}")
    logger.info(f"Database: {settings.DATABASE_URL}")
    logger.info(f"Server: {settings.HOST}:{settings.PORT}")

    # Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created/verified")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise

    # Create necessary directories
    for path in [
        settings.RAW_DATASET_PATH,
        settings.LABELS_PATH,
        settings.AUTO_COLLECT_PATH,
        settings.LOG_DIR,
        settings.ALERT_LOG_DIR,
        settings.WEIGHTS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    logger.info("✅ Directories verified")

    logger.info("✅ Startup complete!")

    yield

    # Shutdown
    logger.info("🛑 Shutting down ADAS Backend API...")


# Create FastAPI app
app = FastAPI(
    title="ADAS Backend API",
    description="Advanced Driver Assistance System - Production Backend with Real-Time AI",
    version="3.0.0",
    lifespan=lifespan,
)

# Register exception handlers
register_exception_handlers(app)

# CORS Configuration - Allow ALL origins for Cloudflare Tunnel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests"""
    start_time = datetime.now()
    logger.info(f"→ {request.method} {request.url.path}")

    try:
        response = call_next(request)
        return await response
    except Exception as e:
        logger.error(f"❌ Request failed: {e}", exc_info=True)
        raise
    finally:
        duration = (datetime.now() - start_time).total_seconds()
        logger.debug(f"← {request.method} {request.url.path} ({duration:.3f}s)")


# Include API routers with tags
app.include_router(upload_router, tags=["Upload"])
app.include_router(inference_router, tags=["Inference"])
app.include_router(dataset_router, tags=["Dataset"])
app.include_router(alerts_router, tags=["Alerts"])
app.include_router(detections_router, tags=["Detections"])
app.include_router(models_router, tags=["Models"])
app.include_router(ws_router, tags=["WebSocket"])
app.include_router(video_upload_router, tags=["Video Upload"])  # NEW
app.include_router(driver_monitor_router, tags=["Driver Monitoring"])  # NEW v4.0
app.include_router(analytics_router, tags=["Analytics"])  # Real dashboard data

# 🆕 ADAS routers
app.include_router(adas_router, tags=["ADAS"])
app.include_router(adas_ws_router, tags=["ADAS WebSocket"])


# ============ Core Endpoints ============


@app.get("/", response_model=APIResponse)
async def root():
    """API information"""
    return APIResponse(
        success=True,
        message="ADAS Backend API v3.0.0 - Production Ready",
        data={
            "name": "ADAS Backend API",
            "version": "3.0.0",
            "description": "Advanced Driver Assistance System",
            "documentation": "/docs",
            "health_check": "/health",
            "status_check": "/api/status",
        },
    )


@app.get("/health", response_model=APIResponse)
async def health_check():
    """Simple health check endpoint"""
    return APIResponse(
        success=True,
        message="Service is healthy",
        data={
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
        },
    )


@app.get("/api/status", response_model=APIResponse)
async def detailed_status(db: Session = Depends(get_db)):
    """Detailed status with database check"""
    try:
        # Test database connection
        db.execute(text("SELECT 1"))

        camera_service = CameraService(db)
        detection_service = DetectionService(db)

        status_data = {
            "status": "operational",
            "timestamp": datetime.now().isoformat(),
            "version": "3.0.0",
            "environment": "development" if settings.DEBUG else "production",
            "database": {
                "connected": True,
                "type": "SQL Server" if settings.SQL_SERVER else "SQLite",
            },
            "features": {
                "voice_alerts": settings.ENABLE_VOICE_ALERTS,
                "driver_monitoring": settings.ENABLE_DRIVER_MONITORING,
            },
            "statistics": {
                "active_cameras": len(camera_service.get_all()),
                "total_detections": detection_service.get_count(),
            },
        }

        return APIResponse(success=True, message="All systems operational", data=status_data)

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return APIResponse(
            success=False,
            message="Service degraded",
            error=ErrorCode.INTERNAL_ERROR,
            data={
                "status": "degraded",
                "error": str(e),
            },
        )


# ============ Camera Endpoints (Using Enhanced Services) ============


@app.get("/api/cameras/list", response_model=APIResponse[List[CameraResponse]])
async def get_cameras(db: Session = Depends(get_db)):
    """Get all cameras"""
    camera_service = CameraService(db)
    cameras = camera_service.get_all()
    return APIResponse(
        success=True,
        message=f"Retrieved {len(cameras)} cameras",
        data=cameras,
    )


@app.get("/api/cameras/{camera_id}", response_model=APIResponse[CameraResponse])
async def get_camera(camera_id: int, db: Session = Depends(get_db)):
    """Get camera by ID"""
    camera_service = CameraService(db)
    camera = camera_service.get_by_id(camera_id)
    return APIResponse(
        success=True,
        message="Camera retrieved successfully",
        data=camera,
    )


@app.post("/api/cameras", response_model=APIResponse[CameraResponse])
async def create_camera(camera: CameraCreate, db: Session = Depends(get_db)):
    """Create new camera"""
    camera_service = CameraService(db)
    new_camera = camera_service.create(camera)
    return APIResponse(
        success=True,
        message="Camera created successfully",
        data=new_camera,
    )


@app.put("/api/cameras/{camera_id}", response_model=APIResponse[CameraResponse])
async def update_camera(camera_id: int, camera: CameraCreate, db: Session = Depends(get_db)):
    """Update camera"""
    camera_service = CameraService(db)
    updated_camera = camera_service.update(camera_id, camera)
    return APIResponse(
        success=True,
        message="Camera updated successfully",
        data=updated_camera,
    )


@app.delete("/api/cameras/{camera_id}", response_model=APIResponse)
async def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    """Delete camera"""
    camera_service = CameraService(db)
    camera_service.delete(camera_id)
    return APIResponse(
        success=True,
        message="Camera deleted successfully",
    )


# ============ Real-Time Dashboard Endpoint ============


@app.get("/api/dashboard/snapshot", response_model=APIResponse)
async def get_dashboard_snapshot():
    """Get real-time dashboard data snapshot"""
    snapshot = realtime_aggregator.get_dashboard_snapshot()
    return APIResponse(
        success=True,
        message="Dashboard snapshot retrieved",
        data=snapshot,
    )


# ============ Run Server ============

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚗 ADAS Backend API - Production v3.0.0")
    logger.info("=" * 60)

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_config=None,  # Use custom logging
    )
