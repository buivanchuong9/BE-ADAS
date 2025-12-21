"""
Videos API endpoints - Phase 2 High Priority
Handles video management and processing status
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime, timedelta
import random

from ..models import storage, Video, VideoStatus

router = APIRouter(prefix="/api", tags=["videos"])


@router.get("/videos/list")
async def get_videos_list(
    limit: int = 50,
    page: int = 1,
    status: Optional[str] = None,
    processed: Optional[bool] = None
):
    """
    List all uploaded videos
    
    Query Params:
    - limit: Number of videos per page (default: 50)
    - page: Page number (default: 1)
    - status: Filter by status (uploaded/processing/completed)
    - processed: Filter by processed status (true/false)
    """
    videos = list(storage.videos.values())
    
    # Apply filters
    if status:
        videos = [v for v in videos if v.status.value == status]
    
    if processed is not None:
        videos = [v for v in videos if v.processed == processed]
    
    # Sort by uploaded_at (most recent first)
    videos.sort(key=lambda x: x.uploaded_at, reverse=True)
    
    # Pagination
    total = len(videos)
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_videos = videos[start_idx:end_idx]
    
    # Format response
    response_videos = []
    for v in paginated_videos:
        response_videos.append({
            "id": v.id,
            "filename": v.filename,
            "file_path": v.file_path,
            "thumbnail_url": v.thumbnail_url or f"/api/videos/{v.id}/thumbnail.jpg",
            "duration_seconds": v.duration_seconds,
            "uploaded_at": v.uploaded_at,
            "processed": v.processed,
            "detections_count": v.detections_count,
            "status": v.status.value
        })
    
    return {
        "success": True,
        "videos": response_videos,
        "total": total
    }


@router.get("/videos/{id}")
async def get_video_details(id: int):
    """
    Get detailed information about a video
    
    Path Params:
    - id: Video ID
    """
    if id not in storage.videos:
        raise HTTPException(status_code=404, detail=f"Video {id} not found")
    
    video = storage.videos[id]
    
    # Get detections for this video
    video_detections = [d for d in storage.detections if d.video_id == id]
    
    # Get events for this video
    video_events = [e for e in storage.events.values() if e.metadata and e.metadata.get("video_id") == id]
    
    response = video.model_dump()
    response["detections"] = [d.model_dump() for d in video_detections[:50]]  # Limit to 50
    response["events"] = [e.model_dump() for e in video_events[:20]]  # Limit to 20
    
    return {
        "success": True,
        "video": response
    }


@router.delete("/videos/{id}")
async def delete_video(id: int):
    """
    Delete a video
    
    Path Params:
    - id: Video ID
    """
    if id not in storage.videos:
        raise HTTPException(status_code=404, detail=f"Video {id} not found")
    
    video = storage.videos.pop(id)
    
    # Also remove from datasets if exists
    if id in storage.datasets:
        storage.datasets.pop(id)
    
    # Remove associated detections
    storage.detections = [d for d in storage.detections if d.video_id != id]
    
    return {
        "success": True,
        "message": f"Video '{video.filename}' deleted successfully"
    }


@router.get("/videos/{id}/detections")
async def get_video_detections(
    id: int,
    class_name: Optional[str] = None,
    min_confidence: Optional[float] = None
):
    """
    Get all detections for a video
    
    Path Params:
    - id: Video ID
    
    Query Params:
    - class_name: Filter by class name
    - min_confidence: Minimum confidence threshold
    """
    if id not in storage.videos:
        raise HTTPException(status_code=404, detail=f"Video {id} not found")
    
    # Get detections for this video
    detections = [d for d in storage.detections if d.video_id == id]
    
    # Apply filters
    if class_name:
        detections = [d for d in detections if d.class_name == class_name]
    
    if min_confidence is not None:
        detections = [d for d in detections if d.confidence >= min_confidence]
    
    # Group by frame/timestamp for timeline view
    # Dummy: assume 1 detection per second
    timeline_detections = []
    frame_number = 0
    
    for det in detections[:100]:  # Limit to 100 for performance
        timeline_detections.append({
            "frame_number": frame_number,
            "timestamp_seconds": frame_number / 30.0,  # Assuming 30 fps
            "detections": [{
                "class_name": det.class_name,
                "confidence": det.confidence,
                "bbox": det.bbox
            }]
        })
        frame_number += 30  # Next second
    
    return {
        "success": True,
        "detections": timeline_detections
    }


@router.get("/video/{id}/process-status")
async def get_video_process_status(id: int):
    """
    Get video processing status (for polling during processing)
    
    Path Params:
    - id: Video ID
    
    Returns:
    - progress: Processing progress (0-100)
    - current_frame: Current frame being processed
    - total_frames: Total frames in video
    - status: "processing", "completed", or "error"
    - detections_count: Number of detections so far
    - estimated_time_remaining_seconds: Estimated time to completion
    """
    if id not in storage.videos:
        raise HTTPException(status_code=404, detail=f"Video {id} not found")
    
    video = storage.videos[id]
    
    # If already completed
    if video.status == VideoStatus.COMPLETED or video.processed:
        detections_count = len([d for d in storage.detections if d.video_id == id])
        
        return {
            "success": True,
            "progress": 100,
            "current_frame": int(video.duration_seconds * video.fps),
            "total_frames": int(video.duration_seconds * video.fps),
            "status": "completed",
            "detections_count": detections_count,
            "estimated_time_remaining_seconds": 0
        }
    
    # If processing, return dummy progress
    # In real implementation, this would track actual processing progress
    total_frames = int(video.duration_seconds * video.fps)
    
    # Simulate progress based on time since upload
    if video.status == VideoStatus.PROCESSING:
        # Random progress between 20-80%
        progress = random.randint(20, 80)
    elif video.status == VideoStatus.UPLOADED:
        # Just started
        progress = random.randint(0, 15)
    else:
        progress = 0
    
    current_frame = int(total_frames * progress / 100)
    estimated_remaining = int((100 - progress) / 100 * video.duration_seconds * 2)  # Rough estimate
    
    return {
        "success": True,
        "progress": progress,
        "current_frame": current_frame,
        "total_frames": total_frames,
        "status": video.status.value,
        "detections_count": len([d for d in storage.detections if d.video_id == id]),
        "estimated_time_remaining_seconds": estimated_remaining
    }
