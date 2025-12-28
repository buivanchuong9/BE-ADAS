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

from fastapi import FastAPI, Request, UploadFile, File
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
    lifespan=lifespan,
    # 🔧 CRITICAL FIX: Tell Swagger UI the correct server URL for Cloudflare
    servers=[
        {
            "url": "https://adas-api.aiotlab.edu.vn",
            "description": "Production server (Cloudflare proxy)"
        },
        {
            "url": "http://localhost:52000",
            "description": "Local development server"
        }
    ],
    # Optimize Swagger UI for production use
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,  # Hide schemas by default for cleaner UI
        "tryItOutEnabled": True,
    }
)

# Configure CORS - PRODUCTION SAFE
# CRITICAL: allow_credentials=False is required for Swagger UI file uploads to work
# When credentials=True, browsers enforce strict CORS checks that block multipart uploads
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Production domain (all variations)
        "https://adas-api.aiotlab.edu.vn",
        "https://adas-api.aiotlab.edu.vn:52000",
        "http://adas-api.aiotlab.edu.vn",
        "http://adas-api.aiotlab.edu.vn:52000",
        # Development
        "http://localhost:52000",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:52000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=False,  # MUST be False for file uploads to work in Swagger UI
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],  # Allow browsers to read all response headers
)

# Add request logging middleware with Cloudflare support
@app.middleware("http")
async def log_requests(request, call_next):
    """
    Log all incoming requests with Cloudflare-specific headers.
    Captures CF-Ray for support debugging and real client IP.
    """
    # Get real client IP from Cloudflare headers
    cf_connecting_ip = request.headers.get("CF-Connecting-IP")
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    client_ip = cf_connecting_ip or x_forwarded_for or (request.client.host if request.client else "unknown")
    
    # Get Cloudflare Ray ID for support debugging
    cf_ray = request.headers.get("CF-Ray", "N/A")
    
    # Log incoming request with Cloudflare info
    logger.info(
        f"📨 {request.method} {request.url.path} | "
        f"Client: {client_ip} | "
        f"CF-Ray: {cf_ray}"
    )
    logger.debug(
        f"Headers: Origin={request.headers.get('origin')}, "
        f"Content-Type={request.headers.get('content-type')}, "
        f"Content-Length={request.headers.get('content-length', 'unknown')}"
    )
    
    # Process request
    response = await call_next(request)
    
    # Log response
    logger.info(f"✅ {response.status_code} for {request.method} {request.url.path}")
    
    return response


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
async def health_check(request: Request):
    """
    Health check endpoint with Cloudflare detection.
    Returns server status and Cloudflare connection info for debugging.
    """
    # Detect if request came through Cloudflare
    is_cloudflare = "CF-Ray" in request.headers
    cf_ray = request.headers.get("CF-Ray", "N/A")
    cf_connecting_ip = request.headers.get("CF-Connecting-IP", "N/A")
    
    return {
        "status": "healthy",
        "service": "ADAS Video Analysis API",
        "version": "2.0.0",
        "cloudflare": {
            "detected": is_cloudflare,
            "cf_ray": cf_ray,
            "client_ip": cf_connecting_ip
        },
        "server": {
            "host": request.url.hostname,
            "port": request.url.port,
            "scheme": request.url.scheme
        }
    }


@app.post("/debug/upload-test")
async def debug_upload_test(file: UploadFile = File(...)):
    """
    Minimal upload endpoint for debugging Cloudflare issues.
    Returns immediately without processing to verify uploads reach FastAPI.
    
    Use this to test:
    1. If uploads reach the server at all
    2. Cloudflare timeout behavior
    3. File upload configuration
    """
    import time
    from fastapi import UploadFile, File
    
    start_time = time.time()
    
    try:
        # Read file metadata only (don't save to disk)
        filename = file.filename
        content_type = file.content_type
        
        # Read first 1KB to verify file is readable
        chunk = await file.read(1024)
        file_size_sample = len(chunk)
        
        # Calculate elapsed time
        elapsed = time.time() - start_time
        
        logger.info(f"🧪 Debug upload test: {filename} ({file_size_sample}+ bytes) in {elapsed:.2f}s")
        
        return {
            "status": "success",
            "message": "✅ Upload test successful - file reached FastAPI",
            "filename": filename,
            "content_type": content_type,
            "bytes_read": file_size_sample,
            "elapsed_seconds": round(elapsed, 3),
            "timestamp": time.time(),
            "note": "This endpoint does not save or process the file"
        }
    except Exception as e:
        logger.error(f"❌ Debug upload test failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "elapsed_seconds": round(time.time() - start_time, 3)
        }


if __name__ == "__main__":
    import uvicorn
    
    # Production: https://adas-api.aiotlab.edu.vn/ on port 52000
    # CRITICAL: proxy_headers=True required for reverse proxy (Nginx/IIS)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=52000,
        reload=True,
        log_level="info",
        proxy_headers=True,  # Trust X-Forwarded-* headers from reverse proxy
        forwarded_allow_ips="*",  # Allow all proxy IPs (configure specific IPs in production)
    )

