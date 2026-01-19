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
from sqlalchemy import select, desc
from sqlalchemy.orm import joinedload
import uuid

from app.db.session import get_db
from app.services.video_service import VideoService
from app.services.job_service import get_job_service
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
    thumbnail_url: Optional[str] = None
    cars_detected: int = 0
    pedestrians_detected: int = 0
    lane_departures: int = 0
    warnings_count: int = 0
    safety_score: int = 100
    duration_seconds: float = 0
    events: List[Dict[str, Any]] = []


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
    """Generate public URL for result video"""
    base_url = settings.API_BASE_URL.rstrip('/')
    return f"{base_url}/public/results/{job_id}_result.mp4"


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


def get_current_step(status: str, progress: int) -> str:
    """Get human-readable current step based on status and progress"""
    if status == 'queued' or status == 'pending':
        return "Đang chờ trong hàng đợi..."
    elif status == 'processing':
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
        video_type: "dashcam" or "phone"
        device: "cuda" or "cpu"
        
    Returns:
        UploadResponse with job_id and status "queued"
        
    Response time target: < 10 seconds after file fully uploaded
    """
    import time
    start_time = time.time()
    
    try:
        if not file.filename:
            file.filename = f"upload_{uuid.uuid4()}.mp4"

        logger.info(f"📱 [Mobile Upload] Starting: {file.filename} (type={video_type}, device={device})")
        
        # Map video_type from mobile (phone -> dashcam)
        if video_type == "phone":
            video_type = "dashcam"
        
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
        
        # === CRITICAL: Submit job for background AI processing ===
        logger.info(f"📱 [Mobile Upload] Step 4: Submitting to AI queue...")
        
        output_path = video_service.get_output_path(job_id)
        
        job_service = get_job_service()
        await job_service.submit_job(
            session=db,
            job_id=job_id,
            input_path=job.video_path,
            output_path=output_path,
            video_type=video_type,
            device=device
        )
        
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
        
        # Build response based on status
        response = StatusResponse(
            success=True,
            job_id=str(job.job_id),
            status=status,
            progress_percent=progress,
            current_step=get_current_step(status, progress),
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
            
            response.result = AnalysisResult(
                video_url=get_public_video_url(str(job.job_id)),
                thumbnail_url=get_thumbnail_url(str(job.job_id)),
                cars_detected=0,  # TODO: Get from processing result
                pedestrians_detected=0,
                lane_departures=lane_departures,
                warnings_count=warnings,
                safety_score=calculate_safety_score(events_list),
                duration_seconds=job.video.duration_seconds if job.video else 0,
                events=events_list
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


@router.get("/video/download/{job_id}")
async def mobile_download_video(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Download processed video file.
    
    Args:
        job_id: Job ID
        
    Returns:
        Video file (binary stream)
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
        
        # Get result path
        video_service = VideoService(db)
        output_path = Path(video_service.get_output_path(job_id))
        
        # Check if result file exists
        if not output_path.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Video kết quả không tìm thấy"
                    }
                }
            )
        
        return FileResponse(
            path=str(output_path),
            media_type="video/mp4",
            filename=f"adas_result_{job_id[:8]}.mp4",
            headers={
                "Content-Disposition": f'attachment; filename="adas_result_{job_id[:8]}.mp4"'
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
    Get user's video analysis history.
    
    Args:
        page: Page number (default: 1)
        limit: Items per page (default: 10, max: 50)
        
    Returns:
        Paginated list of video jobs with results
    """
    try:
        # Calculate offset
        offset = (page - 1) * limit
        
        # Query jobs with pagination
        # TODO: Filter by user_id when auth is implemented
        query = (
            select(JobQueue)
            .options(joinedload(JobQueue.video))
            .order_by(desc(JobQueue.created_at))
            .limit(limit)
            .offset(offset)
        )
        
        result = await db.execute(query)
        jobs = result.scalars().all()
        
        # Count total jobs for pagination
        count_query = select(JobQueue)
        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())
        
        # Build history items
        history_items = []
        for job in jobs:
            item = HistoryItem(
                job_id=str(job.job_id),
                status=job.status,
                created_at=job.created_at,
                completed_at=job.completed_at
            )
            
            if job.status == 'completed':
                item.video_url = get_public_video_url(str(job.job_id))
                item.thumbnail_url = get_thumbnail_url(str(job.job_id))
                item.safety_score = 85  # TODO: Calculate from events
            
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
        "version": "1.0.0",
        "endpoints": [
            "POST /api/mobile/video/upload",
            "GET /api/mobile/video/status/{job_id}",
            "GET /api/mobile/video/download/{job_id}",
            "GET /api/mobile/video/history"
        ]
    }
