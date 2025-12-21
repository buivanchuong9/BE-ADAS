"""
Settings and Configuration API endpoints - Phase 4 Low Priority
Handles system settings and camera configuration
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/settings", tags=["settings"])


# In-memory settings storage
_system_settings = {
    "detection": {
        "confidence_threshold": 0.5,
        "nms_threshold": 0.45,
        "max_detections": 100
    },
    "alerts": {
        "enabled": True,
        "sound_enabled": True,
        "severity_filter": ["critical", "warning", "info"]
    },
    "video": {
        "auto_process": True,
        "save_processed_video": True,
        "max_file_size_mb": 500
    }
}

_cameras = {
    "cam_01": {
        "id": "cam_01",
        "name": "Front Dashcam",
        "location": "Windshield - Center",
        "status": "active",
        "stream_url": "rtsp://192.168.1.100:554/stream1"
    },
    "cam_02": {
        "id": "cam_02",
        "name": "In-Cabin Camera",
        "location": "Dashboard - Facing Driver",
        "status": "active",
        "stream_url": "rtsp://192.168.1.101:554/stream1"
    },
    "cam_03": {
        "id": "cam_03",
        "name": "Rear Camera",
        "location": "Rear Bumper",
        "status": "inactive",
        "stream_url": None
    }
}


@router.get("")
async def get_settings():
    """
    Get system settings
    
    Returns all configuration settings for detection, alerts, and video processing
    """
    return {
        "success": True,
        "settings": _system_settings
    }


@router.put("")
async def update_settings(settings: dict):
    """
    Update system settings
    
    Request body: Same structure as GET /api/settings response
    - detection: Detection configuration
    - alerts: Alert configuration
    - video: Video processing configuration
    """
    global _system_settings
    
    # Validate and update settings
    if "detection" in settings:
        if "confidence_threshold" in settings["detection"]:
            threshold = settings["detection"]["confidence_threshold"]
            if not 0 <= threshold <= 1:
                raise HTTPException(
                    status_code=400, 
                    detail="confidence_threshold must be between 0 and 1"
                )
        _system_settings["detection"].update(settings["detection"])
    
    if "alerts" in settings:
        _system_settings["alerts"].update(settings["alerts"])
    
    if "video" in settings:
        if "max_file_size_mb" in settings["video"]:
            max_size = settings["video"]["max_file_size_mb"]
            if max_size < 1 or max_size > 2000:
                raise HTTPException(
                    status_code=400,
                    detail="max_file_size_mb must be between 1 and 2000"
                )
        _system_settings["video"].update(settings["video"])
    
    return {
        "success": True,
        "message": "Settings updated successfully",
        "settings": _system_settings
    }


@router.get("/cameras")
async def get_cameras():
    """
    List all configured cameras
    
    Returns list of cameras with their status and configuration
    """
    cameras = list(_cameras.values())
    
    return {
        "success": True,
        "cameras": cameras,
        "total": len(cameras)
    }


@router.post("/cameras")
async def add_camera(
    name: str,
    location: str,
    stream_url: Optional[str] = None
):
    """
    Add a new camera
    
    Request body (as JSON or form data):
    - name: Camera name
    - location: Camera location description
    - stream_url: Optional RTSP/HTTP stream URL
    """
    # Generate camera ID
    camera_id = f"cam_{str(uuid.uuid4())[:8]}"
    
    # Create camera entry
    camera = {
        "id": camera_id,
        "name": name,
        "location": location,
        "status": "active" if stream_url else "inactive",
        "stream_url": stream_url,
        "created_at": datetime.now().isoformat()
    }
    
    _cameras[camera_id] = camera
    
    return {
        "success": True,
        "message": f"Camera '{name}' added successfully",
        "camera_id": camera_id,
        "camera": camera
    }


@router.get("/cameras/{id}")
async def get_camera(id: str):
    """
    Get camera details
    
    Path Params:
    - id: Camera ID
    """
    if id not in _cameras:
        raise HTTPException(status_code=404, detail=f"Camera '{id}' not found")
    
    return {
        "success": True,
        "camera": _cameras[id]
    }


@router.put("/cameras/{id}")
async def update_camera(
    id: str,
    name: Optional[str] = None,
    location: Optional[str] = None,
    stream_url: Optional[str] = None,
    status: Optional[str] = None
):
    """
    Update camera configuration
    
    Path Params:
    - id: Camera ID
    
    Request body:
    - name: Optional new name
    - location: Optional new location
    - stream_url: Optional new stream URL
    - status: Optional status (active/inactive)
    """
    if id not in _cameras:
        raise HTTPException(status_code=404, detail=f"Camera '{id}' not found")
    
    camera = _cameras[id]
    
    if name is not None:
        camera["name"] = name
    if location is not None:
        camera["location"] = location
    if stream_url is not None:
        camera["stream_url"] = stream_url
    if status is not None:
        if status not in ["active", "inactive"]:
            raise HTTPException(
                status_code=400,
                detail="status must be 'active' or 'inactive'"
            )
        camera["status"] = status
    
    camera["updated_at"] = datetime.now().isoformat()
    
    return {
        "success": True,
        "message": f"Camera '{id}' updated successfully",
        "camera": camera
    }


@router.delete("/cameras/{id}")
async def delete_camera(id: str):
    """
    Delete a camera
    
    Path Params:
    - id: Camera ID
    """
    if id not in _cameras:
        raise HTTPException(status_code=404, detail=f"Camera '{id}' not found")
    
    camera = _cameras.pop(id)
    
    return {
        "success": True,
        "message": f"Camera '{camera['name']}' deleted successfully"
    }
