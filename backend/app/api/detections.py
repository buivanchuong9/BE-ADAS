"""
Detections API endpoints - Phase 1 Critical
Handles object detection results from video/webcam
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from datetime import datetime, timedelta
from collections import Counter

from ..models import storage, Detection, DetectionSaveRequest

router = APIRouter(prefix="/api/detections", tags=["detections"])


@router.post("/save")
async def save_detections(request: DetectionSaveRequest):
    """
    Save detection results from video/webcam
    
    Request body:
    - video_id: Optional video ID
    - camera_id: Optional camera ID
    - detections: Array of detection objects
    - metadata: Optional metadata
    """
    detection_ids = []
    
    for det_data in request.detections:
        detection_id = storage.detection_counter
        storage.detection_counter += 1
        
        detection = Detection(
            id=detection_id,
            class_name=det_data.get("class_name", "unknown"),
            class_id=det_data.get("class_id", 0),
            confidence=det_data.get("confidence", 0.0),
            bbox=det_data.get("bbox", [0, 0, 0, 0]),
            timestamp=det_data.get("timestamp", datetime.now().isoformat()),
            camera_id=request.camera_id,
            video_id=request.video_id
        )
        
        storage.detections.append(detection)
        detection_ids.append(detection_id)
    
    return {
        "success": True,
        "detection_id": detection_ids[0] if detection_ids else None,
        "message": f"Saved {len(detection_ids)} detections successfully"
    }


@router.get("/recent")
async def get_recent_detections(
    limit: int = 20,
    camera_id: Optional[str] = None,
    class_name: Optional[str] = None
):
    """
    Get recent detections
    
    Query Params:
    - limit: Number of detections to return (default: 20)
    - camera_id: Filter by camera ID
    - class_name: Filter by class name
    """
    detections = storage.detections.copy()
    
    # Apply filters
    if camera_id:
        detections = [d for d in detections if d.camera_id == camera_id]
    
    if class_name:
        detections = [d for d in detections if d.class_name == class_name]
    
    # Sort by timestamp (most recent first)
    detections.sort(key=lambda x: x.timestamp, reverse=True)
    
    # Limit results
    detections = detections[:limit]
    
    return {
        "success": True,
        "detections": [
            {
                "id": d.id,
                "class_name": d.class_name,
                "confidence": d.confidence,
                "timestamp": d.timestamp,
                "camera_id": d.camera_id,
                "bbox": d.bbox
            }
            for d in detections
        ]
    }


@router.get("/stats")
async def get_detection_stats():
    """
    Get detection statistics for dashboard
    
    Returns:
    - total_detections: Total number of detections
    - classes: Detection count and avg confidence by class
    - by_camera: Detection count by camera
    """
    detections = storage.detections
    
    # Count by class
    class_counter = Counter(d.class_name for d in detections)
    
    # Calculate average confidence per class
    class_stats = []
    for class_name, count in class_counter.items():
        class_detections = [d for d in detections if d.class_name == class_name]
        avg_confidence = sum(d.confidence for d in class_detections) / len(class_detections)
        
        class_stats.append({
            "class_name": class_name,
            "count": count,
            "avg_confidence": round(avg_confidence, 3)
        })
    
    # Sort by count descending
    class_stats.sort(key=lambda x: x["count"], reverse=True)
    
    # Count by camera
    camera_counter = Counter(d.camera_id for d in detections if d.camera_id)
    camera_stats = [
        {"camera_id": camera_id, "count": count}
        for camera_id, count in camera_counter.items()
    ]
    
    return {
        "success": True,
        "total_detections": len(detections),
        "classes": class_stats,
        "by_camera": camera_stats
    }
