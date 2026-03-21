from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.video_service import VideoService
# V2: No job_service - GPU workers poll PostgreSQL directly
from app.schemas.video import VideoJobResponse, VideoJobCreate
from app.schemas.event import SafetyEventResponse
from app.core.exceptions import ValidationError
from app.core.config import settings
from fastapi import Body

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
            user_id=None  # Avoid FK violation when local users table does not have seed user id=1
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
            "completed_at": job.completed_at,
            "video_url": f"{settings.API_BASE_URL}/public/results/{'/'.join(job.result_path.replace(chr(92), '/').split('/')[-2:])}" if job.result_path else None,
            "full_result_video_url": f"{settings.API_BASE_URL}/public/results/{'/'.join(job.result_path.replace(chr(92), '/').split('/')[-2:])}" if job.result_path else None
        }
        
        # Job is now in database with status='pending'
        # GPU workers will automatically claim it using SELECT FOR UPDATE SKIP LOCKED
        # NO Celery needed - workers poll the PostgreSQL queue directly
        
        total_time = time.time() - start_time
        logger.info(f"✅ Upload complete - Job {job.job_id} queued for processing (total: {total_time:.1f}s)")
        logger.info(f"   Status: {job.status}")
        logger.info(f"   GPU workers will claim this job automatically")
        
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



@router.post("/analyze")
async def analyze_video(
    job_id: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    """
    Re-queue a failed job for analysis.
    
    NOTE: For new uploads, this is NOT needed - workers auto-claim pending jobs.
    This endpoint is only for RETRYING failed jobs.
    
    Args:
        job_id: The ID of the job to retry
        
    Returns:
        Job status
    """
    try:
        from app.db.repositories.job_queue_repo import JobQueueRepository
        
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
            
        if job.status not in ['pending', 'failed']:
             return {
                 "message": f"Job is already {job.status}",
                 "job_id": job_id,
                 "status": job.status
             }

        # Reset to pending for workers to pick up
        from app.db.models.job_queue import JobStatus
        await repo.update_status(job_id, JobStatus.PENDING)
        await repo.update(job.id, attempts=0, error_message=None)
        await db.commit()
        
        logger.info(f"Job {job_id} reset to pending for retry")
             
        return {
            "message": "Job reset to pending - workers will claim it automatically",
            "job_id": job_id,
            "status": "pending"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analyze failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress/{job_id}")
async def get_progress(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get progress of a video analysis job (with HLS streaming support).
    
    Returns:
        - status: pending | processing | completed | failed
        - progress_percent: 0-100
        - hls_ready: True if HLS stream is available for playback
        - hls_playlist_url: URL to HLS playlist (if available)
        - segments_generated: Number of segments generated so far
    """
    try:
        from app.db.repositories.job_queue_repo import JobQueueRepository
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Build HLS playlist URL if ready
        hls_ready = getattr(job, 'hls_ready', False)
        hls_playlist_path = getattr(job, 'hls_playlist_path', None)
        hls_playlist_url = None
        
        if hls_ready and hls_playlist_path:
            # URL format: /api/hls/{job_id}/playlist.m3u8
            hls_playlist_url = f"{settings.API_BASE_URL}/api/hls/{job.job_id}/playlist.m3u8"
            
        return {
            "job_id": str(job.job_id),
            "status": job.status,
            "progress_percent": job.progress_percent,
            "processing_time_seconds": getattr(job, 'processing_time_seconds', 0),
            
            # HLS streaming fields
            "hls_ready": hls_ready,
            "hls_playlist_url": hls_playlist_url,
            "segments_generated": getattr(job, 'segments_generated', 0),
            "total_segments": getattr(job, 'total_segments', 0),
            
            # Legacy MP4 (fallback)
            "result_path": getattr(job, 'result_path', None)
        }
    except Exception as e:
         logger.error(f"Get progress failed: {e}")
         raise HTTPException(status_code=500, detail=str(e))


@router.get("/sample")
async def get_sample_video():
    """
    Get a sample video file for demonstration.
    Returns the file content of a default sample video.
    """
    try:
        # Check for sample in storage/samples or storage/raw
        sample_dir = Path(settings.STORAGE_ROOT) / "samples"
        raw_dir = Path(settings.RAW_VIDEO_DIR)
        
        sample_file = None
        
        # 1. Try specific samples dir
        if sample_dir.exists():
            files = list(sample_dir.glob("*.mp4"))
            if files:
                sample_file = files[0]
        
        # 2. Try raw dir if no sample found
        if not sample_file and raw_dir.exists():
            files = list(raw_dir.glob("*.mp4"))
            if files:
                sample_file = files[0] # Just take the first one
                
        if not sample_file or not sample_file.exists():
             raise HTTPException(status_code=404, detail="No sample video available")
             
        return FileResponse(
            path=str(sample_file),
            media_type="video/mp4",
            filename="sample_video.mp4"
        )
    except Exception as e:
        logger.error(f"Get sample failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
            "completed_at": job.completed_at,
            "video_url": f"{settings.API_BASE_URL}/public/results/{'/'.join(job.result_path.replace(chr(92), '/').split('/')[-2:])}" if job.result_path else None,
            "full_result_video_url": f"{settings.API_BASE_URL}/public/results/{'/'.join(job.result_path.replace(chr(92), '/').split('/')[-2:])}" if job.result_path else None
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
        filename: Result filename (ignored, uses result.mp4)
        db: Database session
        
    Returns:
        Video file
    """
    try:
        from app.db.repositories.job_queue_repo import JobQueueRepository
        
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
        
        # Use result_path directly from job record
        if not job.result_path:
            raise HTTPException(status_code=404, detail="Result video path not set")
        
        result_path = Path(job.result_path)
        
        # Handle both absolute and relative paths
        if not result_path.is_absolute():
            # Try relative to project root
            result_path = Path(settings.STORAGE_ROOT).parent / job.result_path
        
        if not result_path.exists():
            # Try storage/result/{job_id}/result.mp4 as fallback
            fallback_path = Path(os.getenv('VIDEOS_OUTPUT_DIR', './storage/result')) / str(job_id) / "result.mp4"
            if fallback_path.exists():
                result_path = fallback_path
            else:
                logger.error(f"Result video not found: tried {job.result_path} and {fallback_path}")
                raise HTTPException(status_code=404, detail=f"Result video not found at {job.result_path}")
        
        logger.info(f"Serving result video: {result_path}")
        
        # Return file
        return FileResponse(
            path=str(result_path),
            media_type="video/mp4",
            filename=filename or "result.mp4"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.get("/stream/{job_id}")
async def stream_result_video(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Stream processed video file directly (no filename required).
    
    Simpler alternative to /download/{job_id}/{filename}.
    
    Args:
        job_id: Job ID
        db: Database session
        
    Returns:
        Video file stream
        
    Example:
        GET /api/video/stream/036948c7-5a72-40cf-8266-f597e1f47f50
    """
    try:
        from app.db.repositories.job_queue_repo import JobQueueRepository
        
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
        
        # Find result video
        result_path = None
        
        # 1. Try job.result_path
        if job.result_path:
            candidate = Path(job.result_path)
            if candidate.exists():
                result_path = candidate
            elif not candidate.is_absolute():
                # Try relative to project root
                candidate = Path(settings.STORAGE_ROOT).parent / job.result_path
                if candidate.exists():
                    result_path = candidate
        
        # 2. Fallback to standard location
        if not result_path:
            fallback = Path(os.getenv('VIDEOS_OUTPUT_DIR', './storage/result')) / str(job_id) / "result.mp4"
            if fallback.exists():
                result_path = fallback
        
        if not result_path or not result_path.exists():
            raise HTTPException(status_code=404, detail=f"Result video not found for job {job_id}")
        
        logger.info(f"Streaming result video: {result_path}")
        
        return FileResponse(
            path=str(result_path),
            media_type="video/mp4",
            filename=f"result_{job_id[:8]}.mp4"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stream failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Stream failed: {str(e)}")


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


@router.post("/upload-sync")
async def upload_and_analyze_sync(
    file: UploadFile = File(...),
    video_type: str = "dashcam",
    db: AsyncSession = Depends(get_db)
):
    """
    SYNCHRONOUS video upload and analysis.
    
    This endpoint uploads a video, processes it immediately with GPU,
    and returns the analyzed video URL when complete.
    
    Typical processing time:
    - 10s video @ 30fps: ~10-15s (with GPU)
    - 30s video @ 30fps: ~25-35s (with GPU)  
    - 60s video @ 30fps: ~50-70s (with GPU)
    
    Flow:
    1. Upload video to storage
    2. Create job record
    3. Process with GPU (blocking)
    4. Return result URL
    
    Args:
        file: Video file (mp4, avi, mov, max 200MB for sync)
        video_type: "dashcam" or "in_cabin"
        db: Database session
        
    Returns:
        {
            "job_id": "uuid",
            "status": "completed",
            "video_url": "https://api/public/results/uuid/result.mp4",
            "processing_time_seconds": 35,
            "events_count": 12
        }
    """
    import time
    import asyncio
    import uuid
    from concurrent.futures import ThreadPoolExecutor
    
    start_time = time.time()
    job_id = None
    
    try:
        logger.info(f"📤 [SYNC] Upload started: {file.filename} (type={video_type})")
        
        # === VALIDATION ===
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Check file size (max 200MB for sync processing to avoid timeout)
        MAX_SYNC_SIZE_MB = 200
        file_content = await file.read()
        file_size_mb = len(file_content) / (1024 * 1024)
        
        if file_size_mb > MAX_SYNC_SIZE_MB:
            raise HTTPException(
                status_code=400,
                detail=f"File too large for sync processing ({file_size_mb:.1f}MB). "
                       f"Max: {MAX_SYNC_SIZE_MB}MB. Use /upload for async processing."
            )
        
        # Reset file position for saving
        await file.seek(0)
        
        # === CREATE VIDEO SERVICE ===
        video_service = VideoService(db)
        
        # Quick validation (extension + content type)
        valid_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
        ext = Path(file.filename).suffix.lower()
        if ext not in valid_extensions:
            raise HTTPException(status_code=400, detail=f"Invalid video format: {ext}")
        
        # === CREATE JOB IN DATABASE ===
        job = await video_service.create_job(
            filename=file.filename,
            video_type=video_type,
            device="cuda",
            user_id=None  # Optional uploader; keep sync upload working without seeded user row
        )
        job_id = str(job.job_id)
        
        # Save uploaded file
        await video_service.save_uploaded_video(job.job_id, file)
        upload_time = time.time() - start_time
        logger.info(f"[SYNC] ✓ Video uploaded: {job_id} ({upload_time:.1f}s, {file_size_mb:.1f}MB)")
        
        # === GET VIDEO PATH ===
        # Refresh job to get video info
        from app.db.repositories.job_queue_repo import JobQueueRepository
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job or not job.video:
            raise HTTPException(status_code=500, detail="Failed to create job record")
        
        input_path = job.video.storage_path
        
        # === RUN GPU PROCESSING ===
        logger.info(f"[SYNC] 🚀 Starting GPU processing: {job_id}")
        
        # Import and run GPU worker processing directly
        # This runs synchronously in a ThreadPool to not block event loop
        def _run_gpu_analysis():
            """Run GPU analysis in thread."""
            import os
            import sys
            import cv2
            import numpy as np
            from pathlib import Path as PPath
            
            # Add project root
            project_root = PPath(__file__).parent.parent.parent.parent
            sys.path.insert(0, str(project_root))
            
            # Import ADAS components
            from backend.perception.object.object_detector_v11 import ObjectDetectorV11
            from backend.perception.lane.lane_detector_ufld import UFLDLaneDetector
            from backend.perception.distance.distance_estimator import DistanceEstimator
            from backend.perception.cuda_preprocess import CUDAPreprocessor
            from backend.perception.risk.fcw_ttc import compute_fcw
            from backend.core.ffmpeg_utils import FFmpegEncoder, get_video_info
            
            # Setup paths
            output_dir = PPath(os.getenv('VIDEOS_OUTPUT_DIR', './storage/result')) / job_id
            output_dir.mkdir(parents=True, exist_ok=True)
            result_path = output_dir / "result.mp4"
            
            # Load models (cached after first load)
            device = "cuda"
            cuda_prep = CUDAPreprocessor(enable_cuda=True, device=device)
            
            obj_detector = ObjectDetectorV11(
                model_path='backend/models/yolo11x.pt',
                device=device,
                conf_threshold=0.5,
                imgsz=416,
            )
            
            lane_detector = UFLDLaneDetector(
                model_path=None,  # Using untrained for now
                device=device,
                cuda_preprocessor=cuda_prep,
            )
            
            dist_estimator = DistanceEstimator(focal_length=700.0, camera_height=1.2)
            
            # Open video
            cap = cv2.VideoCapture(str(input_path))
            if not cap.isOpened():
                raise RuntimeError(f"Cannot open video: {input_path}")
            
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Process frames
            events = []
            frame_idx = 0
            
            with FFmpegEncoder(
                output_path=str(result_path),
                width=width,
                height=height,
                fps=fps,
                use_nvenc=True,
                preset='fast'
            ) as encoder:
                
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # Object detection
                    obj_result = obj_detector.process_frame(frame)
                    objects = obj_result.get('detections', [])
                    
                    # Lane detection (every 3 frames)
                    if frame_idx % 3 == 0:
                        lane_result = lane_detector.process_frame(frame)
                    
                    # Distance + FCW for each object
                    EGO_SPEED = 50.0  # km/h
                    for obj in objects:
                        if obj.get('bbox'):
                            dist = dist_estimator.estimate_distance_bbox(
                                bbox=obj['bbox'],
                                vehicle_type=obj.get('class_name', 'car'),
                                frame_height=height
                            )
                            fcw = compute_fcw(dist.get('distance', 100), EGO_SPEED)
                            obj['distance'] = dist
                            obj['fcw_state'] = fcw.state
                    
                    # Draw overlay (simplified)
                    annotated = frame.copy()
                    
                    # Draw lane corridor if available
                    if 'annotated_frame' in lane_result:
                        annotated = lane_result['annotated_frame']
                    
                    # Draw object boxes
                    for obj in objects:
                        if obj.get('bbox'):
                            x1, y1, x2, y2 = [int(v) for v in obj['bbox']]
                            color = (0, 255, 0)
                            if obj.get('fcw_state') == 'COLLISION_RISK':
                                color = (0, 0, 255)
                            elif obj.get('fcw_state') == 'WARNING':
                                color = (0, 165, 255)
                            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                            
                            # Label
                            label = obj.get('class_name', 'obj')
                            if obj.get('distance'):
                                label += f" {obj['distance'].get('distance', 0):.0f}m"
                            cv2.putText(annotated, label, (x1, y1 - 10),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    
                    # Write frame
                    encoder.write(annotated)
                    frame_idx += 1
                    
                    # Progress logging
                    if frame_idx % 30 == 0:
                        progress = int((frame_idx / max(1, total_frames)) * 100)
                        logger.info(f"[SYNC] Progress: {progress}% ({frame_idx}/{total_frames})")
            
            cap.release()
            
            return {
                'result_path': str(result_path),
                'frames_processed': frame_idx,
                'events_count': len(events),
            }
        
        # Run in thread pool to not block async event loop
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='sync_gpu') as executor:
            result = await loop.run_in_executor(executor, _run_gpu_analysis)
        
        processing_time = int(time.time() - start_time)
        
        # === UPDATE JOB STATUS ===
        from app.db.models.job_queue import JobStatus
        await repo.update_status(job_id, JobStatus.COMPLETED)
        await repo.update(
            job.id,
            result_path=result['result_path'],
            processing_time_seconds=processing_time,
            progress_percent=100
        )
        await db.commit()
        
        logger.info(
            f"[SYNC] ✅ Completed: {job_id} in {processing_time}s "
            f"({result['frames_processed']} frames)"
        )
        
        # Build result URL
        result_filename = Path(result['result_path']).name
        result_url = f"{settings.API_BASE_URL}/public/results/{job_id}/{result_filename}"
        
        return {
            "job_id": job_id,
            "status": "completed",
            "video_url": result_url,
            "full_result_video_url": result_url,
            "processing_time_seconds": processing_time,
            "frames_processed": result['frames_processed'],
            "events_count": result.get('events_count', 0),
            "message": f"Video analyzed successfully in {processing_time}s"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SYNC] ❌ Failed: {e}", exc_info=True)
        
        # Mark job as failed if we have a job_id
        if job_id:
            try:
                from app.db.repositories.job_queue_repo import JobQueueRepository
                from app.db.models.job_queue import JobStatus
                repo = JobQueueRepository(db)
                await repo.update_status(job_id, JobStatus.FAILED)
                await repo.update(job.id, error_message=str(e))
                await db.commit()
            except Exception:
                pass
        
        raise HTTPException(
            status_code=500,
            detail=f"Video analysis failed: {str(e)}"
        )
