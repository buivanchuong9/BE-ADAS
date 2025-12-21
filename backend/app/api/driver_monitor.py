"""
Driver Monitoring API endpoints - Phase 2 High Priority
Handles driver status monitoring and fatigue detection
"""
from fastapi import APIRouter, HTTPException, Form, UploadFile, File
from typing import Optional
from datetime import datetime, timedelta
import random

from ..models import storage, DriverStatus, DriverStatusRequest

router = APIRouter(prefix="/api", tags=["driver-monitoring"])


@router.post("/driver-monitor/analyze")
async def analyze_driver_frame(
    frame: str = Form(...),
    camera_id: str = Form(...)
):
    """
    Analyze driver face frame for fatigue/distraction
    
    FormData:
    - frame: Base64 encoded image
    - camera_id: Camera identifier
    
    Returns:
    - fatigue_level: 0-100 (higher = more fatigued)
    - distraction_level: 0-100 (higher = more distracted)
    - eyes_closed: Boolean
    - head_pose: Yaw, pitch, roll angles
    - alert_triggered: Whether an alert should be shown
    - recommendations: Array of recommendations
    """
    # Generate dummy analysis results
    fatigue_level = random.randint(0, 100)
    distraction_level = random.randint(0, 100)
    eyes_closed = random.choice([True, False]) if fatigue_level > 60 else False
    
    # Head pose angles (degrees)
    head_pose = {
        "yaw": round(random.uniform(-30, 30), 2),
        "pitch": round(random.uniform(-20, 20), 2),
        "roll": round(random.uniform(-15, 15), 2)
    }
    
    # Determine alert status
    alert_triggered = False
    recommendations = []
    
    if fatigue_level > 70:
        alert_triggered = True
        recommendations.append("Take a break - high fatigue detected")
        recommendations.append("Consider stopping for rest")
    elif fatigue_level > 50:
        recommendations.append("Monitor fatigue level - consider taking a break soon")
    
    if distraction_level > 70:
        alert_triggered = True
        recommendations.append("Focus on the road - distraction detected")
    elif distraction_level > 50:
        recommendations.append("Minimize distractions")
    
    if eyes_closed:
        alert_triggered = True
        recommendations.append("Eyes closed detected - stay alert!")
    
    # Store in history
    history_entry = {
        "timestamp": datetime.now().isoformat(),
        "fatigue_level": fatigue_level,
        "distraction_level": distraction_level,
        "eyes_closed": eyes_closed,
        "head_pose": head_pose,
        "camera_id": camera_id,
        "alert_triggered": alert_triggered
    }
    storage.driver_status_history.append(history_entry)
    
    # Keep only last 1000 entries
    if len(storage.driver_status_history) > 1000:
        storage.driver_status_history = storage.driver_status_history[-1000:]
    
    return {
        "success": True,
        "fatigue_level": fatigue_level,
        "distraction_level": distraction_level,
        "eyes_closed": eyes_closed,
        "head_pose": head_pose,
        "alert_triggered": alert_triggered,
        "recommendations": recommendations
    }


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
