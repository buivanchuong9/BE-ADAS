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

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/video", tags=["video"])


@router.post("/upload", response_model=VideoJobResponse)
async def upload_video(
    file: UploadFile = File(...),
    video_type: str = "dashcam",
    device: str = "cpu",
    db: AsyncSession = Depends(get_db)
):
    """
    Upload video for ADAS analysis.
    
    Args:
        file: Video file (mp4, avi, mov)
        video_type: "dashcam" or "in_cabin"
        device: "cpu" or "cuda"
        db: Database session
        
    Returns:
        Video job with job_id and status
    """
    try:
        logger.info(f"Received video upload: {file.filename}")
        
        # Create video service
        video_service = VideoService(db)
        
        # Validate video
        await video_service.validate_video(file)
        
        # Validate video type
        if video_type not in ["dashcam", "in_cabin"]:
            raise HTTPException(
                status_code=400,
                detail="video_type must be 'dashcam' or 'in_cabin'"
            )
        
        # Create job in database
        job = await video_service.create_job(
            user_id=1,  # TODO: Get from authentication
            filename=file.filename,
            video_type=video_type,
            device=device
        )
        
        # Save uploaded file
        await video_service.save_uploaded_video(job.job_id, file)
        
        # Submit to background processing
        job_service = get_job_service()
        await job_service.submit_job(job.job_id, db)
        
        logger.info(f"Started processing job {job.job_id}")
        
        return job
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")



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
        from app.db.repositories.video_job_repo import VideoJobRepository
        
        # Get job from database
        repo = VideoJobRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        return job
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get result failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Get result failed: {str(e)}")


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
        from app.db.repositories.video_job_repo import VideoJobRepository
        from app.services.video_service import VideoService
        
        # Get job from database
        repo = VideoJobRepository(db)
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
        output_path = video_service.get_output_path(job_id)
        
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
        from app.db.repositories.video_job_repo import VideoJobRepository
        from app.services.video_service import VideoService
        
        # Get job from database
        repo = VideoJobRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        # Delete from database
        await repo.delete(job.id)
        await db.commit()
        
        # Cleanup files
        video_service = VideoService(db)
        try:
            input_path = Path(job.input_path)
            if input_path.exists():
                input_path.unlink()
            
            output_path = video_service.get_output_path(job.job_id)
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
