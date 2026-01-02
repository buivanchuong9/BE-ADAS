"""
Video API v3 - Upload with Hash Deduplication
==============================================
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session_v3 import get_db
from ..db.models.video import Video
from ..db.models.job_queue import JobQueue, JobStatus
from ..db.repositories.job_queue_repo import JobQueueRepository
from ..core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/videos", tags=["videos-v3"])


# ============================================================
# Response Models
# ============================================================

class VideoUploadResponse(BaseModel):
    video_id: int
    sha256: str
    is_duplicate: bool
    original_filename: str
    size_bytes: int


class VideoCheckResponse(BaseModel):
    exists: bool
    video_id: Optional[int] = None
    sha256: Optional[str] = None


class JobCreateResponse(BaseModel):
    job_id: UUID
    video_id: int
    status: str
    priority: int
    queue_position: int


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    progress_percent: int
    current_step: Optional[str] = None
    events_detected: int = 0
    result_path: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_seconds: Optional[int] = None


class VideoListItem(BaseModel):
    id: int
    sha256_hash: str
    original_filename: str
    size_bytes: int
    duration_seconds: Optional[float] = None
    upload_count: int
    

class VideoListResponse(BaseModel):
    items: list[VideoListItem]
    total: int
    page: int
    limit: int


# ============================================================
# Utility Functions
# ============================================================

def compute_sha256(file_content: bytes) -> str:
    """Compute SHA256 hash of file content."""
    return hashlib.sha256(file_content).hexdigest()


async def save_video_file(sha256: str, filename: str, content: bytes) -> str:
    """Save video file to storage, organized by hash."""
    # Use /hdd3/adas/videos/raw/{hash}/original.ext
    storage_dir = Path(settings.VIDEOS_RAW_DIR) / sha256
    storage_dir.mkdir(parents=True, exist_ok=True)
    
    # Keep original extension
    ext = Path(filename).suffix or '.mp4'
    file_path = storage_dir / f"original{ext}"
    
    with open(file_path, 'wb') as f:
        f.write(content)
    
    return str(file_path)


# ============================================================
# Endpoints
# ============================================================

@router.get("/check", response_model=VideoCheckResponse)
async def check_video_exists(
    sha256: str = Query(..., min_length=64, max_length=64),
    db: AsyncSession = Depends(get_db)
):
    """
    Check if a video with given SHA256 hash already exists.
    
    Call this BEFORE uploading to avoid duplicate uploads.
    """
    result = await db.execute(
        select(Video).where(Video.sha256_hash == sha256.lower())
    )
    video = result.scalar_one_or_none()
    
    if video:
        return VideoCheckResponse(
            exists=True,
            video_id=video.id,
            sha256=video.sha256_hash
        )
    
    return VideoCheckResponse(exists=False)


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a video file with SHA256 deduplication.
    
    If the same video was uploaded before, returns existing record
    and increments upload_count.
    """
    # Read file content
    content = await file.read()
    size_bytes = len(content)
    
    # Validate size
    max_size = settings.MAX_VIDEO_SIZE_MB * 1024 * 1024
    if size_bytes > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max: {settings.MAX_VIDEO_SIZE_MB}MB"
        )
    
    # Compute hash
    sha256 = compute_sha256(content)
    
    # Check if already exists
    result = await db.execute(
        select(Video).where(Video.sha256_hash == sha256)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        # Increment upload count
        await db.execute(
            update(Video)
            .where(Video.id == existing.id)
            .values(upload_count=Video.upload_count + 1)
        )
        await db.commit()
        
        logger.info(f"Duplicate video detected: {sha256[:8]}...")
        
        return VideoUploadResponse(
            video_id=existing.id,
            sha256=sha256,
            is_duplicate=True,
            original_filename=file.filename or "unknown",
            size_bytes=size_bytes
        )
    
    # Save new file
    storage_path = await save_video_file(sha256, file.filename or "video.mp4", content)
    
    # Create database record
    video = Video(
        sha256_hash=sha256,
        original_filename=file.filename or "video.mp4",
        storage_path=storage_path,
        size_bytes=size_bytes
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)
    
    logger.info(f"New video uploaded: {sha256[:8]}... ({size_bytes} bytes)")
    
    return VideoUploadResponse(
        video_id=video.id,
        sha256=sha256,
        is_duplicate=False,
        original_filename=file.filename or "unknown",
        size_bytes=size_bytes
    )


@router.post("/jobs", response_model=JobCreateResponse)
async def create_job(
    video_id: int,
    video_type: str = Form("dashcam"),
    priority: int = Form(0),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a processing job for a video.
    
    Returns immediately with job_id. Poll /jobs/{job_id}/status for progress.
    """
    # Verify video exists
    result = await db.execute(
        select(Video).where(Video.id == video_id)
    )
    video = result.scalar_one_or_none()
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Create job
    repo = JobQueueRepository(db)
    job = await repo.create_job(
        video_id=video_id,
        video_type=video_type,
        priority=priority,
        device="cuda"
    )
    
    # Get queue position
    pending_count = await repo.get_pending_count()
    
    await db.commit()
    
    logger.info(f"Created job {job.job_id} for video {video_id}")
    
    return JobCreateResponse(
        job_id=job.job_id,
        video_id=video_id,
        status=job.status,
        priority=priority,
        queue_position=pending_count
    )


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get detailed status of a processing job."""
    result = await db.execute(
        select(JobQueue).where(JobQueue.job_id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Count events for this job
    from sqlalchemy import func
    from ..db.models.safety_event import SafetyEvent
    
    event_count = 0
    if job.status == JobStatus.COMPLETED:
        result = await db.execute(
            select(func.count(SafetyEvent.id)).where(SafetyEvent.job_id == job.id)
        )
        event_count = result.scalar() or 0
    
    # Determine current step based on progress
    current_step = None
    if job.status == JobStatus.PROCESSING:
        if job.progress_percent < 10:
            current_step = "initializing"
        elif job.progress_percent < 50:
            current_step = "object_detection"
        elif job.progress_percent < 80:
            current_step = "lane_analysis"
        else:
            current_step = "rendering"
    
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress_percent=job.progress_percent,
        current_step=current_step,
        events_detected=event_count,
        result_path=job.result_path,
        error_message=job.error_message,
        processing_time_seconds=job.processing_time_seconds
    )


@router.get("/", response_model=VideoListResponse)
async def list_videos(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List all uploaded videos with pagination."""
    offset = (page - 1) * limit
    
    # Get total count
    from sqlalchemy import func
    total_result = await db.execute(select(func.count(Video.id)))
    total = total_result.scalar() or 0
    
    # Get items
    result = await db.execute(
        select(Video)
        .order_by(Video.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    videos = result.scalars().all()
    
    items = [
        VideoListItem(
            id=v.id,
            sha256_hash=v.sha256_hash,
            original_filename=v.original_filename,
            size_bytes=v.size_bytes,
            duration_seconds=v.duration_seconds,
            upload_count=v.upload_count
        )
        for v in videos
    ]
    
    return VideoListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit
    )


@router.get("/jobs/{job_id}/download")
async def download_result(
    job_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Download the processed video result."""
    result = await db.execute(
        select(JobQueue).where(JobQueue.job_id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400, 
            detail=f"Job not completed. Status: {job.status}"
        )
    
    if not job.result_path or not Path(job.result_path).exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    
    return FileResponse(
        job.result_path,
        media_type="video/mp4",
        filename=f"adas_result_{job_id}.mp4"
    )
