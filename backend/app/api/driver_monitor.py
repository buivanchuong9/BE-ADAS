"""
Driver Monitoring API endpoints - Phase 2 High Priority
Handles driver status monitoring and fatigue detection via VIDEO UPLOAD
"""
from fastapi import APIRouter, HTTPException, Form, UploadFile, File, Depends
from typing import Optional
from datetime import datetime, timedelta
import random
import logging
import time
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import storage, DriverStatus, DriverStatusRequest
from app.db.session import get_db
from app.services.video_service import VideoService
# V2: No job_service - GPU workers poll PostgreSQL directly
from app.schemas.video import VideoJobResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["driver-monitoring"])


@router.post("/driver-monitor/analyze", response_model=VideoJobResponse)
async def analyze_driver_video(
    file: UploadFile = File(...),
    camera_id: Optional[str] = Form("in_cabin_camera"),
    device: str = Form("cuda"),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload driver monitoring video for fatigue/distraction analysis.
    
    Args:
        file: Video file (mp4, avi, mov, max 500MB)
        camera_id: Camera identifier (default: "in_cabin_camera")
        device: "cpu" or "cuda" (default: "cuda")
        db: Database session
        
    Returns:
        Video job with job_id and status for tracking
        
    Response includes:
        - job_id: Track processing progress
        - status: "pending", "processing", "completed", "failed"
        - progress_percent: 0-100
        
    After completion, results will include:
        - fatigue_level: 0-100 (higher = more fatigued)
        - distraction_level: 0-100 (higher = more distracted)
        - eyes_closed_count: Number of frames with eyes closed
        - head_pose_violations: Count of dangerous head poses
        - alert_triggered: Whether alerts were triggered
        - recommendations: Safety recommendations
        - result_video_url: Processed video with annotations
        
    Example:
        POST /api/driver-monitor/analyze
        FormData:
            file: <video_file>
            camera_id: "in_cabin_camera"
            device: "cuda"
    """
    start_time = time.time()
    
    try:
        logger.info(f"📹 Driver monitoring upload started: {file.filename} (camera={camera_id}, device={device})")
        
        # Validate file exists
        if not file or not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No file provided. Please select a video file to upload."
            )
        
        # Create video service
        video_service = VideoService(db)
        
        # FAST validation (doesn't read entire file)
        logger.info(f"[Driver Monitor] Step 1/4: Validating video format and size...")
        await video_service.validate_video(file)
        logger.info(f"[Driver Monitor] ✓ Validation passed ({time.time() - start_time:.1f}s)")
        
        # Validate device
        if device not in ["cpu", "cuda"]:
            logger.warning(f"Invalid device '{device}', defaulting to 'cpu'")
            device = "cpu"
        
        # Create job in database with video_type="in_cabin" for driver monitoring
        logger.info(f"[Driver Monitor] Step 2/4: Creating driver monitoring job...")
        job = await video_service.create_job(
            filename=file.filename,
            video_type="in_cabin",  # Driver monitoring uses in_cabin type
            device=device,
            user_id=1  # TODO: Get from authentication
        )
        logger.info(f"[Driver Monitor] ✓ Job created: {job.job_id} ({time.time() - start_time:.1f}s)")
        
        # Save uploaded video (streaming)
        logger.info(f"[Driver Monitor] Step 3/4: Uploading video (streaming)...")
        await video_service.save_uploaded_video(job.job_id, file)
        upload_time = time.time() - start_time
        logger.info(f"[Driver Monitor] ✓ Video uploaded ({upload_time:.1f}s)")
        
        # 3.5 Save to DriverMonitoringVideo table (New Dataset)
        try:
            from app.db.models.driver_video import DriverMonitoringVideo
            
            driver_video = DriverMonitoringVideo(
                job_id=str(job.job_id),
                title=f"Driver Video - {file.filename}",
                description=f"Uploaded via Driver Monitor API (Camera: {camera_id})",
                original_video_path=job.video.storage_path,
                is_sample=False  # User upload is not a sample gallery item by default
            )
            db.add(driver_video)
            await db.commit()
            logger.info(f"[Driver Monitor] ✓ Saved to DriverMonitoringVideo table")
            
        except Exception as e:
            logger.error(f"Failed to save to DriverMonitoringVideo table: {e}")
            # Don't fail the whole request, as JobQueue is the primary execution engine
        
        # Extract all video attributes BEFORE submitting to background
        logger.info(f"[Driver Monitor] Step 4/4: Preparing response data...")
        
        response_data = {
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
            # Add download URLs for frontend
            "download_url": f"/api/driver-monitor/download/{job.job_id}",
            "result_url": f"/api/video/result/{job.job_id}",
        }
        
        
        # V2: Job automatically claimed by GPU workers - No manual submission needed
        # Workers poll PostgreSQL queue directly
        logger.info(f"✅ Job {job.job_id} queued in PostgreSQL - workers will claim automatically")
        
        total_time = time.time() - start_time
        logger.info(f"✅ Driver monitoring upload complete - Job {job.job_id} submitted (total: {total_time:.1f}s)")
        
        # Store camera_id in history for tracking
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "job_id": str(job.job_id),
            "camera_id": camera_id,
            "filename": file.filename,
            "status": "submitted"
        }
        storage.driver_status_history.append(history_entry)
        
        return response_data
    
    except HTTPException:
        raise
    except Exception as e:
        upload_time = time.time() - start_time
        logger.error(f"❌ Driver monitoring upload failed after {upload_time:.1f}s: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Driver monitoring upload failed: {str(e)}. Please try again or contact support."
        )


@router.post("/driver-status")
async def save_driver_status(request: DriverStatusRequest):
    """
    Save driver status update
    
    Request body:
    - driver_id: Optional driver identifier
    - fatigue_level: 0-100
    - distraction_level: 0-100
    - eyes_closed: Boolean
    - head_pose: Optional head pose data
    - timestamp: ISO timestamp
    - camera_id: Optional camera ID
    """
    # Determine alert status
    alert_status = "normal"
    if request.fatigue_level > 70 or request.distraction_level > 70 or request.eyes_closed:
        alert_status = "critical"
    elif request.fatigue_level > 50 or request.distraction_level > 50:
        alert_status = "warning"
    
    # Store in history
    history_entry = {
        "timestamp": request.timestamp,
        "driver_id": request.driver_id,
        "fatigue_level": request.fatigue_level,
        "distraction_level": request.distraction_level,
        "eyes_closed": request.eyes_closed,
        "head_pose": request.head_pose,
        "camera_id": request.camera_id,
        "alert_triggered": alert_status in ["warning", "critical"]
    }
    storage.driver_status_history.append(history_entry)
    
    # Generate recommendations
    recommendations = []
    if request.fatigue_level > 70:
        recommendations.append("High fatigue - take immediate break")
    if request.distraction_level > 70:
        recommendations.append("High distraction - focus on road")
    if request.eyes_closed:
        recommendations.append("Eyes closed detected - stay alert")
    
    return {
        "success": True,
        "alert_triggered": alert_status in ["warning", "critical"],
        "recommendations": recommendations
    }


@router.get("/driver-status")
async def get_current_driver_status(
    driver_id: Optional[str] = None,
    camera_id: Optional[str] = None
):
    """
    Get current driver status
    
    Query Params:
    - driver_id: Optional driver ID filter
    - camera_id: Optional camera ID filter
    """
    # Get latest status from history
    history = storage.driver_status_history
    
    if driver_id:
        history = [h for h in history if h.get("driver_id") == driver_id]
    
    if camera_id:
        history = [h for h in history if h.get("camera_id") == camera_id]
    
    if not history:
        # Return default safe status
        return {
            "success": True,
            "status": {
                "fatigue_level": 0,
                "distraction_level": 0,
                "eyes_closed": False,
                "last_updated": datetime.now().isoformat(),
                "alert_status": "normal"
            }
        }
    
    # Get most recent entry
    latest = history[-1]
    
    # Determine alert status
    alert_status = "normal"
    fatigue = latest.get("fatigue_level", 0)
    distraction = latest.get("distraction_level", 0)
    eyes_closed = latest.get("eyes_closed", False)
    
    if fatigue > 70 or distraction > 70 or eyes_closed:
        alert_status = "critical"
    elif fatigue > 50 or distraction > 50:
        alert_status = "warning"
    
    return {
        "success": True,
        "status": {
            "fatigue_level": fatigue,
            "distraction_level": distraction,
            "eyes_closed": eyes_closed,
            "last_updated": latest.get("timestamp", datetime.now().isoformat()),
            "alert_status": alert_status
        }
    }


@router.get("/driver-status/history")
async def get_driver_status_history(
    driver_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 100
):
    """
    Get driver status history
    
    Query Params:
    - driver_id: Optional driver ID filter
    - from_date: Start date filter (ISO format)
    - to_date: End date filter (ISO format)
    - limit: Maximum number of records (default: 100)
    """
    history = storage.driver_status_history.copy()
    
    # Apply filters
    if driver_id:
        history = [h for h in history if h.get("driver_id") == driver_id]
    
    if from_date:
        history = [h for h in history if h.get("timestamp", "") >= from_date]
    
    if to_date:
        history = [h for h in history if h.get("timestamp", "") <= to_date]
    
    # Sort by timestamp (most recent first)
    history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    # Limit results
    history = history[:limit]
    
    return {
        "success": True,
        "history": history
    }


@router.get("/download/{job_id}")
async def download_driver_monitoring_result(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Download processed driver monitoring video.
    
    This endpoint downloads the annotated video with:
    - Facial landmarks (468 points)
    - EAR/MAR metrics overlay
    - Head pose angles
    - Vietnamese alerts
    - Detected objects (phone, bottle)
    
    Args:
        job_id: Job ID from /analyze endpoint
        
    Returns:
        MP4 video file with driver monitoring annotations
        
    Example:
        GET /api/driver-monitor/download/97924c1d-850f-4905-bce2-5e31f6a8d829
    """
    try:
        from pathlib import Path
        from fastapi.responses import FileResponse
        from app.db.repositories.job_queue_repo import JobQueueRepository
        from app.core.config import settings
        
        # Get job from database
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        if job.status != 'completed':
            raise HTTPException(
                status_code=400, 
                detail=f"Job not completed yet. Status: {job.status}. Progress: {job.progress_percent}%"
            )
        
        # ── Find result video — try ALL known paths ──────────────────────
        import os
        output_path = None
        tried_paths = []
        
        # Project root (same as worker's PROJECT_ROOT)
        project_root = Path(__file__).resolve().parent.parent.parent.parent  # api/ → app/ → backend/ → project
        
        # Strategy 1: result_path from DB (GPU worker now stores absolute path)
        if job.result_path:
            candidate = Path(job.result_path)
            tried_paths.append(str(candidate))
            if candidate.exists():
                output_path = candidate
                logger.info(f"[Download] ✅ DB result_path: {output_path}")
            elif not candidate.is_absolute():
                # Relative path — resolve against project root
                candidate2 = project_root / job.result_path
                tried_paths.append(str(candidate2))
                if candidate2.exists():
                    output_path = candidate2
                    logger.info(f"[Download] ✅ DB path (resolved): {output_path}")
        
        # Strategy 2: settings.VIDEOS_OUTPUT_DIR (/hdd3/adas/videos/output default)
        if output_path is None:
            candidate = Path(settings.VIDEOS_OUTPUT_DIR) / str(job_id) / "result.mp4"
            tried_paths.append(str(candidate))
            if candidate.exists():
                output_path = candidate
                logger.info(f"[Download] ✅ settings path: {output_path}")
        
        # Strategy 3: Worker default output (storage/result/{job_id}/result.mp4)
        if output_path is None:
            for base in [
                project_root / 'storage' / 'result',
                Path('./storage/result'),
                Path('./backend/storage/result'),
                project_root / 'backend' / 'storage' / 'result',
                Path(settings.PROCESSED_VIDEO_DIR),
            ]:
                candidate = base / str(job_id) / "result.mp4"
                tried_paths.append(str(candidate))
                if candidate.exists():
                    output_path = candidate
                    logger.info(f"[Download] ✅ search path: {output_path}")
                    break
        
        # Strategy 4: os.getenv VIDEOS_OUTPUT_DIR (from .env)
        if output_path is None:
            env_dir = os.getenv('VIDEOS_OUTPUT_DIR')
            if env_dir:
                candidate = Path(env_dir) / str(job_id) / "result.mp4"
                tried_paths.append(str(candidate))
                if candidate.exists():
                    output_path = candidate
                    logger.info(f"[Download] ✅ env path: {output_path}")
        
        if output_path is None:
            logger.error(
                f"[Download] ❌ Result not found for job {job_id}. "
                f"DB result_path={job.result_path}. "
                f"project_root={project_root}. "
                f"Tried: {tried_paths}"
            )
            raise HTTPException(
                status_code=404, 
                detail=f"Result video not found. DB path: {job.result_path}. Tried {len(tried_paths)} locations."
            )
        
        logger.info(f"Serving driver monitoring result: {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f}MB)")
        
        # Return file
        return FileResponse(
            path=str(output_path),
            media_type="video/mp4",
            filename=f"driver_monitoring_{job_id}.mp4",
            headers={
                "Content-Disposition": f"attachment; filename=driver_monitoring_{job_id}.mp4"
            }
        )
    
    except HTTPException:
        raise  # Re-raise HTTP exceptions (404, 400) as-is
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.get("/samples/list")
async def list_sample_videos(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    List Sample Driver Videos (Video Mẫu).
    These are processed videos saved for demonstration/gallery purposes.
    
    Args:
        limit: Max videos to return
        offset: Pagination offset
        
    Returns:
        List of driver monitoring videos
    """
    try:
        from sqlalchemy import select, desc
        from app.db.models.driver_video import DriverMonitoringVideo
        
        # Select all videos, ordered by newest first
        # Ideally, we filter by is_sample=True, but for now show all "Driver Monitoring" videos
        query = select(DriverMonitoringVideo).order_by(desc(DriverMonitoringVideo.created_at)).limit(limit).offset(offset)
        
        result = await db.execute(query)
        samples = result.scalars().all()
        
        return {
            "success": True,
            "samples": samples,
            "total": len(samples)
        }
            
    except Exception as e:
        logger.error(f"Failed to list samples: {e}", exc_info=True)
        # Return empty list instead of erroring out to keep frontend safe
        return {
            "success": False,
            "samples": [],
            "error": str(e)
        }

