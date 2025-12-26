"""
MAIN FASTAPI APPLICATION - Version 2.0
========================================
Entry point for ADAS Video Analysis Backend.

Version 2.0 Changes:
- Microsoft SQL Server database
- Async job processing
- Repository pattern for data access
- Proper separation of concerns

Author: Senior ADAS Engineer
Date: 2025-12-26
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import sys

# Add parent directory to path for absolute imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import core configuration
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import init_db, close_db
from app.services.job_service import get_job_service

# Import API routers (absolute import)
from app.api.video import router as video_router
from app.api.dataset import router as dataset_router
from app.api.detections import router as detections_router
from app.api.models_api import router as models_router
from app.api.streaming import router as streaming_router
from app.api.events_alerts import router as events_alerts_router
from app.api.videos_api import router as videos_router
from app.api.driver_monitor import router as driver_monitor_router
from app.api.trips_stats import router as trips_stats_router
from app.api.ai_chat import router as ai_chat_router
from app.api.settings import router as settings_router
from app.api.upload_storage import router as upload_storage_router
from app.api.auth import router as auth_router
from app.api.websocket_alerts import router as websocket_alerts_router  # Phase 6: WebSocket streaming

# Setup structured logging
setup_logging(log_level="INFO" if not settings.DEBUG else "DEBUG")
logger = logging.getLogger(__name__)


# Lifespan event handler (replaces deprecated on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=" * 80)
    logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION} Starting...")
    logger.info("=" * 80)
    
    # Initialize database
    try:
        logger.info("Initializing database connection...")
        await init_db()
        logger.info("✓ Database initialized successfully")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
        logger.error("Please check database configuration and ensure SQL Server is running")
        raise
    
    # Initialize job service
    logger.info("Initializing job service...")
    job_service = get_job_service()
    logger.info(f"✓ Job service initialized with {settings.MAX_CONCURRENT_JOBS} workers")
    
    logger.info("Perception modules ready")
    logger.info("Storage directories configured")
    logger.info(f"API Documentation: http://{settings.HOST}:{settings.PORT}/docs")
    logger.info("=" * 80)
    
    yield
    
    # Shutdown
    logger.info("=" * 80)
    logger.info(f"{settings.APP_NAME} Shutting Down...")
    logger.info("=" * 80)
    
    # Shutdown job service
    logger.info("Shutting down job service...")
    job_service.shutdown()
    logger.info("✓ Job service shutdown complete")
    
    # Close database connections
    logger.info("Closing database connections...")
    await close_db()
    logger.info("✓ Database connections closed")
    
    logger.info("=" * 80)
    logger.info("Shutdown complete")
    logger.info("=" * 80)


# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.APP_NAME,
    description="""
    Production-Grade ADAS Backend System for Research and Commercial Use
    
    ## Version 2.0 Features
    
    ### Database
    - **Microsoft SQL Server** for production-grade data persistence
    - **Async SQLAlchemy** for efficient database operations
    - **Alembic migrations** for schema version control
    
    ### Video Processing
    - **Non-blocking uploads** - API returns immediately
    - **Background processing** with ThreadPoolExecutor
    - **Job status tracking** with progress updates
    - **Event logging** to database
    
    ### ADAS Analysis
    - **Lane Detection**: Real geometry-based curved lane detection
    - **Object Detection**: YOLOv11-based vehicle and pedestrian detection
    - **Distance Estimation**: Monocular distance with risk classification
    - **Lane Departure Warning**: Real-time LDW based on vehicle offset
    - **Forward Collision Warning**: TTC-based collision risk assessment
    - **Traffic Sign Recognition**: Speed limits, stop signs, warnings
    - **Driver Monitoring**: MediaPipe Face Mesh for fatigue detection
    
    ### Architecture
    - **Repository Pattern**: Clean data access layer
    - **Service Layer**: Business logic separation
    - **Pydantic Schemas**: Request/response validation
    - **Structured Logging**: JSON logs with request_id tracking
    
    ## Deployment
    
    Designed for Windows Server with SQL Server Developer Edition.
    Suitable for scientific research (NCKH) and commercial deployment.
    """,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(video_router)
app.include_router(dataset_router)
app.include_router(detections_router)
app.include_router(models_router)
app.include_router(streaming_router)
app.include_router(events_alerts_router)
app.include_router(videos_router)
app.include_router(driver_monitor_router)
app.include_router(trips_stats_router)
app.include_router(ai_chat_router)
app.include_router(settings_router)
app.include_router(upload_storage_router)
app.include_router(auth_router)
app.include_router(websocket_alerts_router)  # Phase 6: WebSocket alert streaming


@app.get("/")
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "service": "ADAS Video Analysis API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "upload": "POST /api/video/upload",
            "result": "GET /api/video/result/{job_id}",
            "download": "GET /api/video/download/{job_id}/{filename}",
            "health": "GET /api/video/health",
            "docs": "GET /docs"
        },
        "documentation": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ADAS Video Analysis API"
    }


if __name__ == "__main__":
    import uvicorn
    
    # Production: https://adas-api.aiotlab.edu.vn/ on port 52000
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=52000,
        reload=True,
        log_level="info"
    )

