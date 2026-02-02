"""
MAIN FASTAPI APPLICATION - Version 3.1
========================================
Entry point for ADAS Video Analysis Backend.

Version 3.0 Changes:
- PostgreSQL database with asyncpg
- Distributed job queue with SELECT FOR UPDATE SKIP LOCKED
- GPU worker pool with supervisor
- Video deduplication with SHA256
- Improved error handling and stability

Author: Senior ADAS Engineer
Date: 2026-01-03
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
from app.api.video_sse import router as video_sse_router  # NEW: SSE streaming
from app.api.dataset import router as dataset_router
from app.api.detections import router as detections_router
from app.api.videos_api import router as videos_router
from app.api.driver_monitor import router as driver_monitor_router
from app.api.ai_chat import router as ai_chat_router
from app.api.settings import router as settings_router
from app.api.upload_storage import router as upload_storage_router
from app.api.auth import router as auth_router
from app.api.websocket_alerts import router as websocket_alerts_router  # Phase 6: WebSocket streaming
from app.api.video_progress_ws import router as video_progress_ws_router  # WebSocket video progress
from app.api.logs_stream import router as logs_stream_router  # Live log streaming for mobile app
from app.api.mobile import router as mobile_router  # Mobile-specific API endpoints

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
        logger.error("Please check database configuration and ensure PostgreSQL is running")
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
    # 🚗 Hệ Thống ADAS Backend v3.1 - PostgreSQL
    
    **Hệ thống phân tích video ADAS triển khai thương mại**
    
    ---
    
    ## 🎯 Tính Năng Phiên Bản 3.0
    
    ### 💾 Cơ Sở Dữ Liệu
    - ✅ **PostgreSQL** - Cơ sở dữ liệu production-grade
    - ✅ **Async asyncpg** - Hiệu suất cao với async I/O
    - ✅ **Distributed Job Queue** - Hàng đợi phân tán với `SELECT FOR UPDATE SKIP LOCKED`
    - ✅ **Video Deduplication** - Loại bỏ trùng lặp với SHA256 hash
    
    ### 🎬 Xử Lý Video
    - ✅ **Non-blocking Upload** - API trả về ngay lập tức
    - ✅ **GPU Worker Pool** - Quản lý worker với Supervisor
    - ✅ **Real-time Progress** - Theo dõi tiến độ xử lý real-time
    - ✅ **Event Logging** - Ghi log sự kiện vào PostgreSQL
    - ✅ **Auto Retry** - Tự động thử lại khi job thất bại
    
    ### 🤖 Phân Tích ADAS
    - 🛣️ **Lane Detection** - Phát hiện làn đường dựa trên hình học thực
    - 🚙 **Object Detection** - Phát hiện xe và người đi bộ với YOLOv11
    - 📏 **Distance Estimation** - Ước lượng khoảng cách monocular
    - ⚠️ **Lane Departure Warning** - Cảnh báo lệch làn đường real-time
    - 🚨 **Forward Collision Warning** - Cảnh báo va chạm dựa trên TTC
    - 🚦 **Traffic Sign Recognition** - Nhận diện biển báo giao thông
    - 😴 **Driver Monitoring** - Giám sát mệt mỏi với MediaPipe Face Mesh
    
    ### 🏗️ Hạ Tầng
    - ☁️ **Cloudflare Proxy** - Hỗ trợ proxy với CF-Ray tracking
    - 🔔 **WebSocket Alerts** - Thông báo real-time qua WebSocket
    - 📊 **Structured Logging** - Log có cấu trúc định dạng JSON
    - 💚 **Health Checks** - Endpoint kiểm tra sức khỏe hệ thống
    
    ### 🚀 Triển Khai
    Thiết kế cho **Ubuntu Production Server** với PostgreSQL.  
    
    ---
    
    ## 📚 Tài Liệu API
    
    - **Swagger UI**: `/docs` (trang này)
    - **ReDoc**: `/redoc` (giao diện thay thế)
    
    ## 🔗 Endpoints Chính
    
    | Nhóm | Endpoint | Mô Tả |
    |------|----------|-------|
    | 🎬 Video | `POST /api/video/upload` | Upload video để phân tích |
    | 📊 Kết Quả | `GET /api/video/result/{job_id}` | Lấy kết quả phân tích |
    | 💾 Download | `GET /api/video/download/{job_id}/{filename}` | Tải video đã xử lý |
    | 🔐 Auth | `POST /api/auth/login` | Đăng nhập hệ thống |
    | 📈 Stats | `GET /api/statistics/summary` | Thống kê tổng quan |
    
    ---
    
    **Phát triển bởi:** ADAS Research Team - Bùi Văn Chương
    **Phiên bản:** 3.0.0 (PostgreSQL)  
    **Ngày cập nhật:** 03/01/2026
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

# PRODUCTION: Add Request ID middleware for distributed tracing
from app.core.middleware import RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)

# Add request logging middleware with Cloudflare support
# IMPORTANT: This middleware is defined with @app.middleware decorator
# which means it runs AFTER middlewares added with app.add_middleware()
# We'll move this to a proper middleware class below to ensure correct order
from starlette.middleware.base import BaseHTTPMiddleware

class CloudflareLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log all incoming requests with Cloudflare-specific headers.
    Captures CF-Ray for support debugging and real client IP.
    
    PRODUCTION: Suppress 404 logs for /admin/* paths to reduce spam.
    """
    async def dispatch(self, request, call_next):
        # Get real client IP from Cloudflare headers
        cf_connecting_ip = request.headers.get("CF-Connecting-IP")
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        client_ip = cf_connecting_ip or x_forwarded_for or (request.client.host if request.client else "unknown")
        
        # Get Cloudflare Ray ID for support debugging
        cf_ray = request.headers.get("CF-Ray", "N/A")
        
        # Log incoming request with Cloudflare info (suppress admin 404s)
        should_log = not (request.url.path.startswith("/admin") or request.url.path.startswith("/_admin"))
        
        if should_log:
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
        
        # Log response (suppress admin 404s)
        if should_log or response.status_code != 404:
            logger.info(f"✅ {response.status_code} for {request.method} {request.url.path}")
        
        return response

# Add logging middleware
app.add_middleware(CloudflareLoggingMiddleware)

# Configure CORS - PRODUCTION SAFE
# ⚠️ CRITICAL: CORSMiddleware MUST be added LAST so it runs FIRST
# This ensures OPTIONS preflight requests are handled before authentication checks
# When credentials=True, browsers enforce strict CORS checks that block multipart uploads
app.add_middleware(
    CORSMiddleware,
    # Use allow_origin_regex to automatically allow all subdomains and http/https
    # This specifically fixes the issue where Safari reports "Origin http://... is not allowed"
    # even when the site is accessed via HTTPS (due to Cloudflare flexible SSL or redirects).
    allow_origin_regex=r"https?://.*\.aiotlab\.edu\.vn|https?://localhost:\d+",
    
    allow_credentials=True,  # Set to True to allow cookies/auth headers
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],  # Explicit methods
    allow_headers=["*"],  # Allow all headers including Authorization
    expose_headers=["*"],  # Allow browsers to read all response headers
    max_age=86400,  # Cache preflight requests for 24 hours
)

# NOTE: We removed the manual @app.options handler.
# Starlette's CORSMiddleware automatically handles OPTIONS requests.
# Adding a manual handler can cause conflicts or return 200 without CORS headers.


# Include routers
app.include_router(video_router)  # Legacy API (backward compatible with v3.0)
app.include_router(video_sse_router)  # NEW: SSE streaming for realtime partial results
app.include_router(dataset_router)
app.include_router(detections_router)
app.include_router(videos_router)
app.include_router(driver_monitor_router)
app.include_router(ai_chat_router)
app.include_router(settings_router)
app.include_router(upload_storage_router)
app.include_router(auth_router)
app.include_router(websocket_alerts_router)  # Phase 6: WebSocket alert streaming
app.include_router(video_progress_ws_router)  # WebSocket video progress streaming
app.include_router(logs_stream_router)  # Live log streaming for mobile app
app.include_router(mobile_router)  # Mobile-specific API endpoints

# ============================================================
# Public Results API (for Mobile App)
# ============================================================
# Serves processed videos with:
# - CORS: Access-Control-Allow-Origin: *
# - Range Request: HTTP 206 Partial Content (for streaming)
# - Cache: public, max-age=86400
from fastapi import Response
from fastapi.responses import StreamingResponse

@app.get("/public/results/{filename}")
async def serve_public_result(
    filename: str,
    request: Request
):
    """
    Serve processed video files with streaming support.
    
    Features:
    - Public access (no auth required)
    - Range request support (HTTP 206)
    - CORS headers for cross-origin access
    - Proper caching headers
    """
    from pathlib import Path
    import os
    
    public_results_dir = Path(settings.PROCESSED_VIDEO_DIR)
    file_path = public_results_dir / filename
    
    # Security: prevent path traversal
    if ".." in filename or not file_path.resolve().is_relative_to(public_results_dir.resolve()):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid filename"}
        )
    
    if not file_path.exists():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=404,
            content={"error": "File not found"},
            headers={
                "Access-Control-Allow-Origin": "*"
            }
        )
    
    file_size = file_path.stat().st_size
    
    # Determine content type
    content_type = "video/mp4"
    if filename.endswith(".jpg") or filename.endswith(".jpeg"):
        content_type = "image/jpeg"
    elif filename.endswith(".png"):
        content_type = "image/png"
    
    # Handle Range request (for video streaming)
    range_header = request.headers.get("range")
    
    if range_header:
        # Parse Range header
        try:
            range_spec = range_header.replace("bytes=", "")
            start_end = range_spec.split("-")
            start = int(start_end[0]) if start_end[0] else 0
            end = int(start_end[1]) if len(start_end) > 1 and start_end[1] else file_size - 1
            
            # Clamp values
            start = max(0, start)
            end = min(end, file_size - 1)
            chunk_size = end - start + 1
            
            def iter_file():
                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        read_size = min(65536, remaining)  # 64KB chunks
                        data = f.read(read_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data
            
            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type=content_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(chunk_size),
                    "Accept-Ranges": "bytes",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                    "Cache-Control": "public, max-age=86400",
                    "Content-Disposition": f'inline; filename="{filename}"'
                }
            )
        except Exception as e:
            logger.warning(f"Invalid Range header: {range_header} - {e}")
    
    # Full file response (no Range)
    def iter_full_file():
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk
    
    return StreamingResponse(
        iter_full_file(),
        media_type=content_type,
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f'inline; filename="{filename}"'
        }
    )


@app.get("/")
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "service": "ADAS Video Analysis API",
        "version": "3.1.0",
        "status": "running",
        "endpoints": {
            "legacy": {
                "upload": "POST /api/video/upload",
                "result": "GET /api/video/result/{job_id}",
                "download": "GET /api/video/download/{job_id}/{filename}",
                "health": "GET /api/video/health"
            },
            "mobile": {
                "upload": "POST /api/mobile/video/upload",
                "status": "GET /api/mobile/video/status/{job_id}",
                "download": "GET /api/mobile/video/download/{job_id}",
                "history": "GET /api/mobile/video/history",
                "health": "GET /api/mobile/health"
            },
            "public": {
                "video": "GET /public/results/{job_id}_result.mp4"
            }
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

