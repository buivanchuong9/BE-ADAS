"""
MOBILE API - REST Endpoints
===========================
Dedicated API endpoints for Mobile App (iOS/Android).
Optimized for mobile experience with async processing.

Key Features:
- Upload returns job_id immediately (non-blocking)
- Status polling with progress percentage
- Public video URLs for sharing
- Paginated history

Endpoints:
- POST /api/mobile/video/upload - Upload video asynchronously
- GET /api/mobile/video/status/{job_id} - Poll processing status
- GET /api/mobile/video/download/{job_id} - Download result video
- GET /api/mobile/video/history - Get user's video history

Author: ADAS Team
Date: 2026-01-19
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, String
from sqlalchemy.orm import joinedload
import uuid

from app.db.session import get_db
from app.services.video_service import VideoService
# V2: No job_service - GPU workers poll PostgreSQL directly
from app.db.repositories.job_queue_repo import JobQueueRepository
from app.db.models.job_queue import JobQueue, JobStatus
from app.core.config import settings
from app.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Create router with mobile prefix
router = APIRouter(prefix="/api/mobile", tags=["mobile"])


# ============================================================
# Response Models
# ============================================================

class UploadResponse(BaseModel):
    """Response for video upload endpoint"""
    success: bool
    job_id: str
    status: str
    message: str
    estimated_time_seconds: int = 120
    created_at: datetime


class ErrorDetail(BaseModel):
    """Error detail model"""
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = False
    error: ErrorDetail


class AnalysisResult(BaseModel):
    """Analysis result from AI processing"""
    video_url: Optional[str] = None
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    cars_detected: int = 0
    pedestrians_detected: int = 0
    lane_departures: int = 0
    warnings_count: int = 0
    safety_score: int = 100
    duration_seconds: Optional[float] = None
    events: List[Dict[str, Any]] = []
    video_type: Optional[str] = None


class StatusResponse(BaseModel):
    """Response for status endpoint"""
    success: bool = True
    job_id: str
    status: str
    progress_percent: int = 0
    current_step: Optional[str] = None
    eta_seconds: Optional[int] = None
    queue_position: Optional[int] = None
    message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    result: Optional[AnalysisResult] = None
    error: Optional[ErrorDetail] = None


class HistoryItem(BaseModel):
    """Single item in video history"""
    job_id: str
    status: str
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    safety_score: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class PaginationInfo(BaseModel):
    """Pagination metadata"""
    page: int
    limit: int
    total: int
    total_pages: int


class HistoryResponse(BaseModel):
    """Response for history endpoint"""
    success: bool = True
    data: List[HistoryItem]
    pagination: PaginationInfo


# ============================================================
# Helper Functions
# ============================================================

def get_public_video_url(job_id: str) -> str:
    """Generate public URL for result video (ends with .mp4 for mobile player compatibility)"""
    base_url = settings.API_BASE_URL.rstrip('/')
    return f"{base_url}/public/results/{job_id}/result.mp4"


def get_download_url(job_id: str) -> str:
    """Generate download URL that ends with .mp4 (required for mobile video players)"""
    base_url = settings.API_BASE_URL.rstrip('/')
    return f"{base_url}/api/mobile/video/download/{job_id}/result.mp4"


def get_thumbnail_url(job_id: str) -> str:
    """Generate URL for video thumbnail"""
    base_url = settings.API_BASE_URL.rstrip('/')
    return f"{base_url}/public/results/{job_id}_thumb.jpg"


def estimate_processing_time(file_size_mb: float) -> int:
    """
    Estimate processing time based on file size.
    
    Rule of thumb:
    - ~1 minute per 50MB of video
    - Minimum 30 seconds
    - Maximum 10 minutes
    """
    estimate = int((file_size_mb / 50) * 60)
    return max(30, min(600, estimate))


def calculate_safety_score(events: List[Dict]) -> int:
    """
    Calculate safety score based on detected events.
    
    - Start at 100
    - Deduct points for dangerous events:
      - Lane departure: -3 points
      - Collision warning: -10 points
      - Critical event: -15 points
    """
    score = 100
    
    for event in events:
        event_type = event.get('type', '')
        level = event.get('level', 'info')
        
        if level == 'critical' or level == 'danger':
            score -= 15
        elif event_type == 'collision_risk' or event_type == 'forward_collision':
            score -= 10
        elif event_type == 'lane_departure':
            score -= 3
        elif level == 'warning':
            score -= 5
    
    return max(0, min(100, score))


def get_current_step(status: str, progress: int, video_type: str = 'dashcam') -> str:
    """Get human-readable current step based on status, progress and video type"""
    if status == 'queued' or status == 'pending':
        return "Đang chờ trong hàng đợi..."
    elif status == 'processing':
        if video_type == 'in_cabin':
            # Driver monitoring steps
            if progress < 10:
                return "Đang khởi tạo Face Mesh + YOLO..."
            elif progress < 30:
                return "Đang phân tích khuôn mặt tài xế..."
            elif progress < 50:
                return "Đang phát hiện mắt nhắm, ngáp..."
            elif progress < 70:
                return "Đang kiểm tra dây an toàn, điện thoại..."
            elif progress < 90:
                return "Đang tạo video annotated..."
            else:
                return "Đang hoàn tất..."
        else:
            # ADAS dashcam steps
            if progress < 10:
                return "Đang khởi tạo AI models..."
            elif progress < 30:
                return "Đang phát hiện làn đường..."
            elif progress < 60:
                return "Đang phát hiện phương tiện..."
            elif progress < 80:
                return "Đang phân tích khoảng cách..."
            elif progress < 95:
                return "Đang tạo video kết quả..."
            else:
                return "Đang hoàn tất..."
    elif status == 'completed':
        return "Hoàn thành!"
    elif status == 'failed':
        return "Xử lý thất bại"
    else:
        return "Đang xử lý..."


# ============================================================
# API Endpoints
# ============================================================

@router.post("/video/upload", response_model=UploadResponse, status_code=202)
async def mobile_upload_video(
    file: UploadFile = File(...),
    video_type: str = "dashcam",
    device: str = "cuda",
    db: AsyncSession = Depends(get_db)
):
    """
    Upload video for ADAS analysis.
    
    Returns job_id immediately (non-blocking).
    AI processing happens in the background.
    
    Args:
        file: Video file (MP4, MOV, AVI, max 500MB)
        video_type: "dashcam" (camera hành trình - ADAS) hoặc "phone" (camera trong xe - giám sát tài xế)
        device: "cuda" or "cpu"
        
    Returns:
        UploadResponse with job_id and status "queued"
        
    Response time target: < 10 seconds after file fully uploaded
    """
    import time
    start_time = time.time()
    
    try:
        from app.db.models.mobile_video import MobileVideo # Import local to avoid circular deps
        
        if not file.filename:
            file.filename = f"upload_{uuid.uuid4()}.mp4"

        logger.info(f"📱 [Mobile Upload] Starting: {file.filename} (type={video_type}, device={device})")
        
        # Map video_type from mobile
        # "phone" = camera trong xe (in-cabin) → giám sát tài xế
        # "dashcam" = camera hành trình → phát hiện ADAS
        if video_type == "phone":
            video_type = "in_cabin"
        
        # Create video service
        video_service = VideoService(db)
        
        # FAST validation (doesn't read entire file)
        logger.info(f"📱 [Mobile Upload] Step 1: Validating format...")
        try:
            await video_service.validate_video(file)
        except ValidationError as e:
            # Check for file too large
            if "too large" in str(e.message).lower():
                raise HTTPException(
                    status_code=413,
                    detail={
                        "success": False,
                        "error": {
                            "code": "FILE_TOO_LARGE",
                            "message": f"File vượt quá giới hạn {settings.MAX_VIDEO_SIZE_MB}MB"
                        }
                    }
                )
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": {
                        "code": "INVALID_FORMAT",
                        "message": e.message
                    }
                }
            )
        
        logger.info(f"📱 [Mobile Upload] Step 2: Creating job record...")
        
        # Create job in database (status = pending)
        job = await video_service.create_job(
            filename=file.filename,
            video_type=video_type,
            device=device,
            user_id=1  # TODO: Get from auth token
        )
        job_id = str(job.job_id)
        
        logger.info(f"📱 [Mobile Upload] Job created: {job_id}")
        
        # Save uploaded file (streaming) - THIS IS THE SLOW PART
        logger.info(f"📱 [Mobile Upload] Step 3: Saving video file...")
        await video_service.save_uploaded_video(job_id, file)
        
        upload_time = time.time() - start_time
        logger.info(f"📱 [Mobile Upload] File saved ({upload_time:.1f}s)")
        
        # 3.5 Save to MobileVideo table (New Dataset for Mobile)
        try:
            mobile_video = MobileVideo(
                job_id=str(job.job_id),
                filename=file.filename,
                original_video_path=job.video.storage_path,
                file_size_mb=round(job.video.size_bytes / (1024 * 1024), 2) if job.video.size_bytes else 0,
                status="queued"
            )
            db.add(mobile_video)
            await db.commit()
            logger.info(f"📱 [Mobile Upload] Saved to MobileVideo table")
        except Exception as e:
            logger.error(f"Failed to save MobileVideo record: {e}")
            # Continue normally
        
        
        # V2: Job automatically claimed by GPU workers - No manual submission needed
        # Workers poll PostgreSQL queue directly
        logger.info(f"✅ Job {job_id} queued in PostgreSQL - workers will claim automatically")
        
        total_time = time.time() - start_time
        logger.info(f"✅ [Mobile Upload] Complete! Job {job_id} queued (total: {total_time:.1f}s)")
        
        # Estimate processing time based on file size
        # FIX: Avoid accessing job.video (lazy load) to prevent MissingGreenlet error
        file_size_mb = 100 
        estimated_time = estimate_processing_time(file_size_mb)
        
        # Return response immediately
        return UploadResponse(
            success=True,
            job_id=job_id,
            status="queued",
            message="Video đã được nhận và đang chờ xử lý",
            estimated_time_seconds=estimated_time,
            created_at=job.created_at or datetime.now(timezone.utc)
        )
        
    except HTTPException:
        raise
    except ValidationError as e:
        logger.warning(f"⚠️ [Mobile Upload] Validation failed: {e.message}")
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": {
                    "code": "INVALID_FORMAT",
                    "message": e.message
                }
            }
        )
    except Exception as e:
        logger.error(f"❌ [Mobile Upload] Failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": {
                    "code": "PROCESSING_ERROR",
                    "message": f"Upload failed: {str(e)}. Vui lòng thử lại."
                }
            }
        )
    finally:
        # CRITICAL: Always close the file handle to prevent temp file leaks
        if file:
            await file.close()


@router.get("/video/status/{job_id}", response_model=StatusResponse)
async def mobile_get_status(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get processing status for a job.
    
    Mobile app should poll this every 3-5 seconds.
    
    Args:
        job_id: Job ID from upload
        
    Returns:
        StatusResponse with current status, progress, and results (if completed)
    """
    try:
        logger.debug(f"📱 [Mobile Status] Checking job: {job_id}")
        
        # Get job from database
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Job '{job_id}' không tồn tại"
                    }
                }
            )
        
        status = job.status
        progress = job.progress_percent or 0
        job_video_type = job.video_type if hasattr(job, 'video_type') else 'dashcam'
        
        # Build response based on status
        response = StatusResponse(
            success=True,
            job_id=str(job.job_id),
            status=status,
            progress_percent=progress,
            current_step=get_current_step(status, progress, job_video_type),
            started_at=job.started_at
        )
        
        if status == 'pending' or status == 'queued':
            # Calculate queue position (jobs before this one)
            queue_query = select(JobQueue).where(
                JobQueue.status == 'pending',
                JobQueue.created_at < job.created_at
            )
            result = await db.execute(queue_query)
            queue_position = len(result.scalars().all()) + 1
            
            response.queue_position = queue_position
            response.message = f"Đang chờ {queue_position - 1} video khác xử lý xong..." if queue_position > 1 else "Sắp được xử lý..."
            
        elif status == 'processing':
            # Estimate remaining time based on progress
            if progress > 0:
                elapsed = 0
                if job.started_at:
                    elapsed = (datetime.now(timezone.utc) - job.started_at.replace(tzinfo=timezone.utc)).total_seconds()
                total_estimated = (elapsed / progress) * 100 if progress > 0 else 120
                response.eta_seconds = max(0, int(total_estimated - elapsed))
            else:
                response.eta_seconds = 120
                
        elif status == 'completed':
            response.completed_at = job.completed_at
            response.progress_percent = 100
            
            # Get events from database
            from app.db.repositories.safety_event_repo import SafetyEventRepository
            event_repo = SafetyEventRepository(db)
            
            try:
                events = await event_repo.get_by_video_job(job.id)
                events_list = []
                for e in events:
                    # Calculate timestamp in seconds from frame_number if available
                    time_sec = 0
                    if e.frame_number and job.video and job.video.fps:
                        time_sec = e.frame_number / job.video.fps
                    
                    events_list.append({
                        "type": e.event_type.value if hasattr(e.event_type, 'value') else str(e.event_type),
                        "timestamp": f"{int(time_sec) // 60:02d}:{int(time_sec) % 60:02d}",
                        "severity": e.severity.value if hasattr(e.severity, 'value') else str(e.severity)
                    })
            except Exception as e:
                logger.warning(f"Could not load events for job {job_id}: {e}")
                events_list = []
            
            # Count event types
            lane_departures = len([e for e in events_list if 'lane' in e.get('type', '').lower()])
            warnings = len([e for e in events_list if e.get('severity') in ('warning', 'critical', 'danger')])
            cars = len([e for e in events_list if e.get('type', '') in ('collision_warning', 'forward_collision', 'unsafe_distance')])
            pedestrians = len([e for e in events_list if e.get('type', '') == 'pedestrian_detected'])
            
            response.result = AnalysisResult(
                video_url=get_public_video_url(str(job.job_id)),
                download_url=get_download_url(str(job.job_id)),
                thumbnail_url=get_thumbnail_url(str(job.job_id)),
                cars_detected=cars,
                pedestrians_detected=pedestrians,
                lane_departures=lane_departures,
                warnings_count=warnings,
                safety_score=calculate_safety_score(events_list),
                duration_seconds=job.video.duration_seconds if job.video else None,
                events=events_list,
                video_type=job_video_type
            )
            
        elif status == 'failed':
            response.failed_at = job.completed_at
            response.error = ErrorDetail(
                code="PROCESSING_ERROR",
                message=job.error_message or "Không thể xử lý video. Vui lòng thử lại với file khác."
            )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Mobile Status] Failed for {job_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": {
                    "code": "SERVER_ERROR",
                    "message": str(e)
                }
            }
        )


@router.get("/video/download/{job_id}/result.mp4")
async def mobile_download_video_mp4(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Download processed video (URL ends with .mp4 for mobile player compatibility)."""
    return await _mobile_download_video(job_id, request, db)


@router.get("/video/download/{job_id}")
async def mobile_download_video(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Download processed video (legacy endpoint without .mp4 suffix)."""
    return await _mobile_download_video(job_id, request, db)


async def _mobile_download_video(
    job_id: str,
    request: Request,
    db: AsyncSession
):
    """
    Internal: Download processed video with Range request support for streaming.
    
    Args:
        job_id: Job ID
        request: HTTP request (for Range header)
        
    Returns:
        Video file (binary stream with Range support)
    """
    try:
        # Get job from database
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "error": {"code": "NOT_FOUND", "message": "Job not found"}}
            )
        
        if job.status != 'completed':
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False, 
                    "error": {
                        "code": "NOT_READY",
                        "message": f"Video chưa xử lý xong. Status: {job.status}"
                    }
                }
            )
        
        # Try multiple paths to find the video file
        import os
        from app.core.config import settings
        
        search_paths = [
            # 1. From VideoService (respects VIDEOS_OUTPUT_DIR env)
            Path(VideoService(db).get_output_path(job_id)),
            
            # 2. Production path (explicit)
            Path(os.getenv('VIDEOS_OUTPUT_DIR', '/hdd3/adas/videos/output')) / str(job_id) / "result.mp4",
            
            # 3. Development path
            Path(settings.PROCESSED_VIDEO_DIR) / str(job_id) / "result.mp4",
            
            # 4. Relative fallback
            Path("storage/result") / str(job_id) / "result.mp4",
            
            # 5. From job.result_path if available
        ]
        
        if job.result_path:
            search_paths.append(Path(job.result_path))
        
        output_path = None
        for candidate in search_paths:
            try:
                if candidate.exists() and candidate.is_file():
                    output_path = candidate
                    logger.info(f"[Mobile Download] Found video at: {output_path}")
                    break
            except Exception as e:
                logger.debug(f"[Mobile Download] Path check failed for {candidate}: {e}")
                continue
        
        if not output_path or not output_path.exists():
            logger.error(
                f"[Mobile Download] Video file not found for job {job_id}. "
                f"Tried paths: {[str(p) for p in search_paths]}"
            )
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Video kết quả không tìm thấy. Job status: {job.status}",
                        "searched_paths": [str(p) for p in search_paths]
                    }
                }
            )
        
        file_size = output_path.stat().st_size
        result_filename = f"adas_result_{job_id[:8]}.mp4"
        
        # Support Range requests (required for mobile video streaming)
        range_header = request.headers.get("range")
        if range_header:
            from fastapi.responses import StreamingResponse
            try:
                range_spec = range_header.replace("bytes=", "")
                start_end = range_spec.split("-")
                start = int(start_end[0]) if start_end[0] else 0
                end = int(start_end[1]) if len(start_end) > 1 and start_end[1] else file_size - 1
                start = max(0, start)
                end = min(end, file_size - 1)
                chunk_size = end - start + 1
                
                def iter_range():
                    with open(output_path, "rb") as f:
                        f.seek(start)
                        remaining = chunk_size
                        while remaining > 0:
                            data = f.read(min(65536, remaining))
                            if not data:
                                break
                            remaining -= len(data)
                            yield data
                
                return StreamingResponse(
                    iter_range(),
                    status_code=206,
                    media_type="video/mp4",
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Content-Length": str(chunk_size),
                        "Accept-Ranges": "bytes",
                        "Access-Control-Allow-Origin": "*",
                        "Content-Disposition": f'inline; filename="{result_filename}"'
                    }
                )
            except Exception as e:
                logger.warning(f"Invalid Range header: {range_header} - {e}")
        
        # Full file response
        return FileResponse(
            path=str(output_path),
            media_type="video/mp4",
            filename=result_filename,
            headers={
                "Content-Disposition": f'inline; filename="{result_filename}"',
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Mobile Download] Failed for {job_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}
        )


@router.get("/video/history", response_model=HistoryResponse)
async def mobile_get_history(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's video analysis history from MobileVideo dataset.
    Joins with JobQueue to get real-time status.
    """
    try:
        from app.db.models.mobile_video import MobileVideo
        from sqlalchemy import func
        
        offset = (page - 1) * limit
        
        # Query MobileVideo + JobQueue (Left Join to preserve history even if JobQueue is purged)
        # Note: JobQueue.job_id is UUID, MobileVideo.job_id is String. Cast needed.
        query = (
            select(MobileVideo, JobQueue)
            .outerjoin(JobQueue, func.cast(JobQueue.job_id, String) == MobileVideo.job_id)
            .order_by(desc(MobileVideo.created_at))
            .limit(limit)
            .offset(offset)
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        # Count total
        count_query = select(func.count(MobileVideo.id))
        total = await db.scalar(count_query) or 0
        
        # Build history items
        history_items = []
        for vid, job in rows:
            # Source of truth: JobQueue if available, else MobileVideo
            current_status = job.status if job else (vid.status or "unknown")
            completed_at = job.completed_at if job else vid.completed_at
            
            item = HistoryItem(
                job_id=vid.job_id,
                status=current_status,
                created_at=vid.created_at,
                completed_at=completed_at
            )
            
            # Generate URLs if completed
            if current_status == 'completed' or vid.processed_video_path:
                item.video_url = get_public_video_url(vid.job_id)
                item.thumbnail_url = get_thumbnail_url(vid.job_id)
                item.safety_score = vid.safety_score or 85
                
            history_items.append(item)
        
        return HistoryResponse(
            success=True,
            data=history_items,
            pagination=PaginationInfo(
                page=page,
                limit=limit,
                total=total,
                total_pages=(total + limit - 1) // limit
            )
        )
        
    except Exception as e:
        logger.error(f"❌ [Mobile History] Failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}
        )


# ============================================================
# Driver Monitoring Mobile API
# ============================================================

class DriverUploadResponse(BaseModel):
    """Response for driver monitoring video upload"""
    success: bool
    job_id: str
    status: str
    message: str
    video_type: str = "in_cabin"
    estimated_time_seconds: int = 90
    created_at: datetime


class DriverStatusResponse(BaseModel):
    """Response for driver monitoring status check"""
    success: bool
    job_id: str
    status: str  # pending, processing, completed, failed
    progress_percent: int
    video_type: str = "in_cabin"
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, str]] = None


@router.post("/driver/upload", response_model=DriverUploadResponse)
async def mobile_driver_upload(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload driver monitoring (in-cabin) video for analysis.
    
    This endpoint accepts:
    - In-cabin camera videos
    - Driver face monitoring footage
    - Videos up to 500MB
    
    Returns job_id to track processing status.
    
    Example:
        POST /api/mobile/driver/upload
        Content-Type: multipart/form-data
        Body: file=<video.mp4>
    """
    try:
        if not file or not file.filename:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": {"code": "NO_FILE", "message": "Vui lòng chọn file video để upload"}
                }
            )
        
        logger.info(f"📹 [Driver Mobile] Upload started: {file.filename}")
        
        # Create video service
        video_service = VideoService(db)
        
        # Validate video
        await video_service.validate_video(file)
        
        # Create job with video_type="in_cabin"
        job = await video_service.create_job(
            filename=file.filename,
            video_type="in_cabin",  # Driver monitoring uses in_cabin type
            device="cuda",
            user_id=1  # TODO: Get from authentication
        )
        
        # Save uploaded video
        await video_service.save_uploaded_video(job.job_id, file)
        
        # Also save to DriverMonitoringVideo table
        try:
            from app.db.models.driver_video import DriverMonitoringVideo
            driver_video = DriverMonitoringVideo(
                job_id=str(job.job_id),
                title=f"Mobile Driver Video - {file.filename}",
                description=f"Uploaded via Mobile Driver API",
                original_video_path=job.video.storage_path,
                is_sample=False
            )
            db.add(driver_video)
            await db.commit()
        except Exception as e:
            logger.warning(f"Could not save to DriverMonitoringVideo: {e}")
        
        logger.info(f"✅ [Driver Mobile] Upload complete: {job.job_id}")
        
        return DriverUploadResponse(
            success=True,
            job_id=str(job.job_id),
            status=job.status,
            message="Video đã được upload. Đang chờ xử lý phát hiện mệt mỏi/mất tập trung.",
            video_type="in_cabin",
            estimated_time_seconds=90,
            created_at=job.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Driver Mobile] Upload failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": {"code": "UPLOAD_FAILED", "message": str(e)}}
        )


@router.get("/driver/status/{job_id}", response_model=DriverStatusResponse)
async def mobile_driver_status(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get driver monitoring video processing status.
    
    Poll this endpoint to track analysis progress.
    
    Returns:
        - status: pending, processing, completed, failed
        - progress_percent: 0-100
        - result: Analysis results when completed
    """
    try:
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "error": {"code": "NOT_FOUND", "message": "Job không tồn tại"}}
            )
        
        result = None
        error = None
        
        if job.status == 'completed':
            # Build result with download URL
            duration = job.video.duration_seconds if job.video and job.video.duration_seconds else None
            
            result = {
                "download_url": f"/api/mobile/driver/download/{job_id}/result.mp4",
                "video_url": f"/api/mobile/driver/download/{job_id}/result.mp4",
                "duration_seconds": duration,
                "processing_time_seconds": job.processing_time_seconds,
                "fatigue_detection": True,
                "distraction_detection": True
            }
        elif job.status == 'failed':
            error = {
                "code": "PROCESSING_FAILED",
                "message": job.error_message or "Xử lý video thất bại"
            }
        
        return DriverStatusResponse(
            success=True,
            job_id=job_id,
            status=job.status,
            progress_percent=job.progress_percent or 0,
            video_type="in_cabin",
            result=result,
            error=error
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Driver Mobile] Status check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}
        )


@router.get("/driver/download/{job_id}/result.mp4")
async def mobile_driver_download_mp4(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Download driver monitoring result video (.mp4 extension for player compatibility)."""
    return await _mobile_driver_download(job_id, request, db)


@router.get("/driver/download/{job_id}")
async def mobile_driver_download(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Download driver monitoring result video (legacy endpoint)."""
    return await _mobile_driver_download(job_id, request, db)


async def _mobile_driver_download(
    job_id: str,
    request: Request,
    db: AsyncSession
):
    """Internal: Download driver monitoring result with Range request support."""
    try:
        from fastapi.responses import StreamingResponse
        
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "error": {"code": "NOT_FOUND", "message": "Job không tồn tại"}}
            )
        
        if job.status != 'completed':
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": {"code": "NOT_READY", "message": f"Video chưa xử lý xong. Status: {job.status}"}
                }
            )
        
        # Try multiple paths to find the video file
        import os
        from app.core.config import settings
        
        search_paths = [
            # 1. From VideoService (respects VIDEOS_OUTPUT_DIR env)
            Path(VideoService(db).get_output_path(job_id)),
            
            # 2. Production path (explicit)
            Path(os.getenv('VIDEOS_OUTPUT_DIR', '/hdd3/adas/videos/output')) / str(job_id) / "result.mp4",
            
            # 3. Development path
            Path(settings.PROCESSED_VIDEO_DIR) / str(job_id) / "result.mp4",
            
            # 4. Relative fallback
            Path("storage/result") / str(job_id) / "result.mp4",
            
            # 5. From job.result_path if available
        ]
        
        if job.result_path:
            search_paths.append(Path(job.result_path))
        
        output_path = None
        for candidate in search_paths:
            try:
                if candidate.exists() and candidate.is_file():
                    output_path = candidate
                    logger.info(f"[Driver Download] Found video at: {output_path}")
                    break
            except Exception as e:
                logger.debug(f"[Driver Download] Path check failed for {candidate}: {e}")
                continue
        
        if not output_path or not output_path.exists():
            logger.error(
                f"[Driver Download] Video file not found for job {job_id}. "
                f"Tried paths: {[str(p) for p in search_paths]}"
            )
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Video kết quả không tìm thấy. Job status: {job.status}",
                        "searched_paths": [str(p) for p in search_paths]
                    }
                }
            )
        
        file_size = output_path.stat().st_size
        result_filename = f"driver_result_{job_id[:8]}.mp4"
        
        # Support Range requests for mobile streaming
        range_header = request.headers.get("range")
        if range_header:
            range_spec = range_header.replace("bytes=", "")
            start_end = range_spec.split("-")
            start = int(start_end[0]) if start_end[0] else 0
            end = int(start_end[1]) if len(start_end) > 1 and start_end[1] else file_size - 1
            start = max(0, start)
            end = min(end, file_size - 1)
            chunk_size = end - start + 1
            
            def iter_range():
                with open(output_path, "rb") as f:
                    f.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        data = f.read(min(65536, remaining))
                        if not data:
                            break
                        remaining -= len(data)
                        yield data
            
            return StreamingResponse(
                iter_range(),
                status_code=206,
                media_type="video/mp4",
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(chunk_size),
                    "Content-Disposition": f'inline; filename="{result_filename}"'
                }
            )
        
        # Full file response
        return FileResponse(
            path=str(output_path),
            media_type="video/mp4",
            filename=result_filename,
            headers={"Content-Disposition": f'inline; filename="{result_filename}"'}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Driver Mobile] Download failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}
        )


# ============================================================
# Health Check
# ============================================================

@router.get("/health")
async def mobile_health_check():
    """
    Health check for mobile API.
    """
    return {
        "status": "healthy",
        "service": "ADAS Mobile API",
        "version": "1.1.0",
        "endpoints": {
            "video": [
                "POST /api/mobile/video/upload",
                "GET /api/mobile/video/status/{job_id}",
                "GET /api/mobile/video/download/{job_id}/result.mp4",
                "GET /api/mobile/video/history"
            ],
            "driver_monitoring": [
                "POST /api/mobile/driver/upload",
                "GET /api/mobile/driver/status/{job_id}",
                "GET /api/mobile/driver/download/{job_id}/result.mp4"
            ]
        }
    }
