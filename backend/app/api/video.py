"""
VIDEO API - REST Endpoints
===========================
FastAPI routes for video upload and result retrieval.

Endpoints:
- POST /api/video/upload - Upload video for analysis
- GET /api/video/result/{job_id} - Get analysis results
- GET /api/video/download/{job_id}/{filename} - Download result video

Author: Senior ADAS Engineer
Date: 2025-12-21 (Refactored for production)
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.video_service import VideoService
from app.services.job_service import get_job_service
from app.schemas.video import VideoJobResponse, VideoJobCreate
from app.schemas.event import SafetyEventResponse
from app.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/video", tags=["video"])


@router.post("/upload", response_model=VideoJobResponse)
async def upload_video(
    file: UploadFile = File(...),
    video_type: str = "dashcam",
    device: str = "cuda",  # GPU by default
    db: AsyncSession = Depends(get_db)
):
    """
    Upload video for ADAS analysis.
    
    Args:
        file: Video file (mp4, avi, mov, max 500MB)
        video_type: "dashcam" or "in_cabin"
        device: "cpu" or "cuda"
        db: Database session
        
    Returns:
        Video job with job_id and status
        
    Raises:
        400: Invalid file, format, or size
        500: Server error during upload
    """
    import time
    start_time = time.time()
    
    try:
        logger.info(f"📤 Upload started: {file.filename} (type={video_type}, device={device})")
        
        # Validate file exists
        if not file or not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No file provided. Please select a video file to upload."
            )
        
        # Create video service
        video_service = VideoService(db)
        
        # FAST validation (doesn't read entire file)
        logger.info(f"[Upload] Step 1/4: Validating format and size...")
        await video_service.validate_video(file)
        logger.info(f"[Upload] ✓ Validation passed ({time.time() - start_time:.1f}s)")
        
        # Validate video type
        if video_type not in ["dashcam", "in_cabin"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid video_type '{video_type}'. Must be 'dashcam' or 'in_cabin'"
            )
        
        # Validate device
        if device not in ["cpu", "cuda"]:
            logger.warning(f"Invalid device '{device}', defaulting to 'cpu'")
            device = "cpu"
        
        # Create job in database
        logger.info(f"[Upload] Step 2/4: Creating job record...")
        job = await video_service.create_job(
            filename=file.filename,
            video_type=video_type,
            device=device,
            user_id=1  # TODO: Get from authentication - Currently using default user for MVP
        )
        logger.info(f"[Upload] ✓ Job created: {job.job_id} ({time.time() - start_time:.1f}s)")
        
        # Save uploaded file (streaming)
        logger.info(f"[Upload] Step 3/4: Uploading video (streaming)...")
        await video_service.save_uploaded_video(job.job_id, file)
        upload_time = time.time() - start_time
        logger.info(f"[Upload] ✓ Video uploaded ({upload_time:.1f}s)")
        
        # CRITICAL FIX: Extract all video attributes BEFORE submitting to background
        # This prevents MissingGreenlet error from lazy loading outside async session
        logger.info(f"[Upload] Step 4/4: Preparing response data...")
        
        # Access all job and video attributes while still in session context
        response_data = {
            "id": job.id,
            "job_id": str(job.job_id),  # Convert UUID to string
            "video_filename": job.video.original_filename if job.video else "",
            "video_path": job.video.storage_path if job.video else "",
            "video_size_mb": round(job.video.size_bytes / (1024 * 1024), 2) if job.video and job.video.size_bytes else 0.0,
            "duration_seconds": job.video.duration_seconds if job.video else None,
            "fps": job.video.fps if job.video else None,
            "resolution": job.video.resolution if job.video else None,
            "status": job.status,
            "progress_percent": job.progress_percent,
            "result_path": job.result_path,
            "error_message": job.error_message,
            "processing_time_seconds": job.processing_time_seconds,
            "trip_id": job.trip_id,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at
        }
        
        # Now submit to background processing (after extracting all data)
        logger.info(f"[Upload] Submitting job {job.job_id} to Celery queue...")
        
        # Submit to Celery task queue (non-blocking)
        from app.tasks import process_video_task
        
        try:
            task = process_video_task.delay(str(job.job_id))
            logger.info(f"   ✅ Celery task submitted")
            logger.info(f"   Task ID: {task.id}")
            logger.info(f"   Job ID: {job.job_id}")
        except Exception as e:
            logger.error(f"   ❌ Failed to submit Celery task: {e}")
            # Even if Celery fails, the job is in database for retry
            raise HTTPException(
                status_code=500,
                detail=f"Failed to queue video processing: {str(e)}"
            )
        
        total_time = time.time() - start_time
        logger.info(f"✅ Upload complete - Job {job.job_id} submitted (total: {total_time:.1f}s)")
        
        return response_data
    
    except HTTPException:
        raise
    except ValidationError as e:
        upload_time = time.time() - start_time
        logger.warning(f"⚠️ Upload validation failed after {upload_time:.1f}s: {e.message}")
        raise HTTPException(
            status_code=400, 
            detail=e.message
        )
    except Exception as e:
        upload_time = time.time() - start_time
        logger.error(f"❌ Upload failed after {upload_time:.1f}s: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Upload failed: {str(e)}. Please try again or contact support if the issue persists."
        )



@router.get("/result/{job_id}", response_model=VideoJobResponse)
async def get_result(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get analysis results for a job.
    
    Args:
        job_id: Job ID from upload
        db: Database session
        
    Returns:
        Video job with status and results
    """
    try:
        logger.info(f"📊 Fetching result for job: {job_id}")
        
        from app.db.repositories.job_queue_repo import JobQueueRepository
        
        # Get job from database
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            logger.warning(f"⚠️ Job not found: {job_id}")
            raise HTTPException(
                status_code=404, 
                detail=f"Job '{job_id}' not found. Please check the job_id."
            )
        
        logger.info(f"✓ Job {job_id} status: {job.status}")
        
        # Extract attributes to prevent lazy loading during Pydantic serialization
        return {
            "id": job.id,
            "job_id": str(job.job_id),
            "video_filename": job.video.original_filename if job.video else "",
            "video_path": job.video.storage_path if job.video else "",
            "video_size_mb": round(job.video.size_bytes / (1024 * 1024), 2) if job.video and job.video.size_bytes else 0.0,
            "duration_seconds": job.video.duration_seconds if job.video else None,
            "fps": job.video.fps if job.video else None,
            "resolution": job.video.resolution if job.video else None,
            "status": job.status,
            "progress_percent": job.progress_percent,
            "result_path": job.result_path,
            "error_message": job.error_message,
            "processing_time_seconds": job.processing_time_seconds,
            "trip_id": job.trip_id,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Get result failed for {job_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to retrieve job result: {str(e)}"
        )


@router.get("/download/{job_id}/{filename}")
async def download_result(
    job_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Download processed video file.
    
    Args:
        job_id: Job ID
        filename: Result filename
        db: Database session
        
    Returns:
        Video file
    """
    try:
        from app.db.repositories.job_queue_repo import JobQueueRepository
        from app.services.video_service import VideoService
        
        # Get job from database
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        if job.status != 'completed':
            raise HTTPException(
                status_code=400, 
                detail=f"Job {job_id} not completed. Status: {job.status}"
            )
        
        # Get output path
        video_service = VideoService(db)
        output_path = Path(video_service.get_output_path(job_id))
        
        if not output_path.exists():
            raise HTTPException(status_code=404, detail="Result video not found")
        
        # Return file
        return FileResponse(
            path=str(output_path),
            media_type="video/mp4",
            filename=filename
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.delete("/job/{job_id}")
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete job and cleanup files.
    
    Args:
        job_id: Job ID
        db: Database session
        
    Returns:
        Success message
    """
    try:
        from app.db.repositories.job_queue_repo import JobQueueRepository
        from app.services.video_service import VideoService
        
        # Get job from database
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        # Delete from database
        await repo.delete(job.id)
        await db.commit()
        
        # Cleanup files
        video_service = VideoService(db)
        try:
            input_path = Path(job.video_path) if job.video_path else None
            if input_path and input_path.exists():
                input_path.unlink()
            
            output_path_str = video_service.get_output_path(job.job_id)
            output_path = Path(output_path_str)
            if output_path.exists():
                output_path.unlink()
        except Exception as e:
            logger.warning(f"File cleanup error for job {job_id}: {e}")
        
        return {"message": f"Job {job_id} deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "service": "ADAS Video Analysis API",
        "version": "1.0.0"
    }


@router.get("/list")
async def list_videos(
    limit: int = 10,
    offset: int = 0,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    List all uploaded videos (for demo/frontend).
    
    Args:
        limit: Max results (default: 10)
        offset: Skip N results (default: 0)
        status: Filter by status: "pending", "processing", "completed", "failed"
        db: Database session
        
    Returns:
        List of video jobs
        
    Example:
        GET /api/video/list?limit=10&status=completed
    """
    try:
        from app.db.repositories.job_queue_repo import JobQueueRepository
        from app.db.models.job_queue import JobQueue  # <--- FIXED: Added missing import
        
        repo = JobQueueRepository(db)
        
        # Get all jobs (with optional status filter)
        from sqlalchemy import select, desc
        from sqlalchemy.orm import joinedload
        
        query = select(JobQueue).options(joinedload(JobQueue.video))
        
        if status:
            query = query.where(JobQueue.status == status)
        
        query = query.order_by(desc(JobQueue.created_at)).limit(limit).offset(offset)
        
        result = await db.execute(query)
        jobs = result.scalars().all()
        
        # Extract attributes to prevent lazy loading
        videos_list = []
        for job in jobs:
            videos_list.append({
                "id": job.id,
                "job_id": str(job.job_id),
                "video_filename": job.video.original_filename if job.video else "",
                "video_path": job.video.storage_path if job.video else "",
                "video_size_mb": round(job.video.size_bytes / (1024 * 1024), 2) if job.video and job.video.size_bytes else 0.0,
                "duration_seconds": job.video.duration_seconds if job.video else None,
                "fps": job.video.fps if job.video else None,
                "resolution": job.video.resolution if job.video else None,
                "status": job.status,
                "progress_percent": job.progress_percent,
                "result_path": job.result_path,
                "created_at": job.created_at,
                "completed_at": job.completed_at
            })
        
        return {
            "videos": videos_list,
            "total": len(videos_list),
            "limit": limit,
            "offset": offset
        }
    
    except Exception as e:
        logger.error(f"List videos failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list videos: {str(e)}")


@router.get("/sample/{job_id}/{filename}")
async def get_raw_video(
    job_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Download RAW/original video (not processed) for demo purposes.
    
    Args:
        job_id: Job ID
        filename: Original filename
        db: Database session
        
    Returns:
        Original uploaded video file
        
    Example:
        GET /api/video/sample/9d507862-f5ec-4c7e-a617-153528f5377d/project_video.mp4
    """
    try:
        from app.db.repositories.job_queue_repo import JobQueueRepository
        from pathlib import Path
        
        # Get job from database
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        # Get raw video path from Video table
        if not job.video or not job.video.storage_path:
            raise HTTPException(status_code=404, detail="Raw video not found")
        
        raw_path = Path(job.video.storage_path)
        
        if not raw_path.exists():
            raise HTTPException(status_code=404, detail="Raw video file not found on disk")
        
        # Return file
        return FileResponse(
            path=str(raw_path),
            media_type="video/mp4",
            filename=filename
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get raw video failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get raw video: {str(e)}")

