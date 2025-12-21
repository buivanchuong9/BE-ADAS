"""
VIDEO API - REST Endpoints
===========================
FastAPI routes for video upload and result retrieval.

Endpoints:
- POST /api/video/upload - Upload video for analysis
- GET /api/video/result/{job_id} - Get analysis results
- GET /api/video/download/{job_id}/{filename} - Download result video

Author: Senior ADAS Engineer
Date: 2025-12-21
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
from pathlib import Path

# Import service layer
from ..services.analysis_service import get_analysis_service

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/video", tags=["video"])


# Response models
class UploadResponse(BaseModel):
    """Response for video upload."""
    job_id: str
    status: str
    message: str


class EventData(BaseModel):
    """Event data model."""
    frame: int
    time: float
    type: str
    level: str
    data: Dict[str, Any]


class StatsData(BaseModel):
    """Processing statistics."""
    total_frames: int
    processed_frames: int
    fps: float
    processing_time_seconds: float
    processing_fps: float
    video_duration_seconds: float
    event_count: int


class ResultResponse(BaseModel):
    """Response for result retrieval."""
    job_id: str
    status: str
    result_video_url: Optional[str] = None
    events: Optional[List[EventData]] = None
    stats: Optional[StatsData] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


@router.post("/upload", response_model=UploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    video_type: str = "dashcam",
    device: str = "cpu"
):
    """
    Upload video for ADAS analysis.
    
    Args:
        file: Video file (mp4, avi, mov)
        video_type: "dashcam" or "in_cabin"
        device: "cpu" or "cuda"
        
    Returns:
        Upload response with job_id
    """
    try:
        logger.info(f"Received video upload: {file.filename}")
        
        # Validate video type
        if video_type not in ["dashcam", "in_cabin"]:
            raise HTTPException(
                status_code=400,
                detail="video_type must be 'dashcam' or 'in_cabin'"
            )
        
        # Validate file type
        if not file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Supported: mp4, avi, mov, mkv"
            )
        
        # Get service
        service = get_analysis_service()
        
        # Create job
        job_id = service.create_job(
            filename=file.filename,
            video_type=video_type
        )
        
        # Read file data
        file_data = await file.read()
        
        # Save uploaded file
        service.save_uploaded_video(job_id, file_data)
        
        # Start processing in background
        service.start_processing(job_id, device=device)
        
        logger.info(f"Started processing job {job_id}")
        
        return UploadResponse(
            job_id=job_id,
            status="processing",
            message="Video uploaded successfully. Processing started."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/result/{job_id}", response_model=ResultResponse)
async def get_result(job_id: str):
    """
    Get analysis results for a job.
    
    Args:
        job_id: Job ID from upload
        
    Returns:
        Result response with status and data
    """
    try:
        # Get service
        service = get_analysis_service()
        
        # Get job status
        job = service.get_job_status(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        # Prepare response
        response = ResultResponse(
            job_id=job['job_id'],
            status=job['status'],
            created_at=job['created_at'],
            updated_at=job['updated_at'],
            error=job.get('error')
        )
        
        # Add results if completed
        if job['status'] == 'completed':
            # Get result URL
            result_url = service.get_result_url(job_id, base_url="")
            
            response.result_video_url = result_url
            response.events = [EventData(**event) for event in job['events']]
            response.stats = StatsData(**job['stats'])
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get result failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Get result failed: {str(e)}")


@router.get("/download/{job_id}/{filename}")
async def download_result(job_id: str, filename: str):
    """
    Download processed video file.
    
    Args:
        job_id: Job ID
        filename: Result filename
        
    Returns:
        Video file
    """
    try:
        # Get service
        service = get_analysis_service()
        
        # Get job
        job = service.get_job_status(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        if job['status'] != 'completed':
            raise HTTPException(
                status_code=400, 
                detail=f"Job {job_id} not completed. Status: {job['status']}"
            )
        
        # Get output path
        output_path = job['output_path']
        
        if not output_path or not Path(output_path).exists():
            raise HTTPException(status_code=404, detail="Result video not found")
        
        # Return file
        return FileResponse(
            path=output_path,
            media_type="video/mp4",
            filename=filename
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """
    Delete job and cleanup files.
    
    Args:
        job_id: Job ID
        
    Returns:
        Success message
    """
    try:
        # Get service
        service = get_analysis_service()
        
        # Get job
        job = service.get_job_status(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        # Cleanup
        service.cleanup_job(job_id)
        
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
