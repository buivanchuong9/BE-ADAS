"""
Events and Alerts API endpoints - Phase 2 High Priority
Handles safety events and real-time alerts
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime, timedelta
import random

from ..models import (
    storage, 
    Event, 
    Alert, 
    EventCreateRequest, 
    EventSeverity,
    AlertSeverity
)

router = APIRouter(prefix="/api", tags=["events", "alerts"])


# ============================================================================
# EVENTS ENDPOINTS
# ============================================================================

@router.post("/events")
async def create_event(request: EventCreateRequest):
    """
    Create a new event (collision, lane departure, etc.)
    
    Request body:
    - type: "collision", "lane_departure", "fatigue", "distraction", "speed", "driver_status"
    - severity: "critical", "warning", "info"
    - description: Event description
    - timestamp: ISO timestamp
    - location: Optional location string
    - metadata: Optional metadata
    - video_id: Optional video ID
    - camera_id: Optional camera ID
    """
    event_id = storage.event_counter
    storage.event_counter += 1
    
    # Create title from type
    title_map = {
        "collision": "Forward Collision Warning",
        "lane_departure": "Lane Departure Warning",
        "fatigue": "Driver Fatigue Detected",
        "distraction": "Driver Distraction Alert",
        "speed": "Speed Limit Exceeded",
        "driver_status": "Driver Status Alert"
    }
    title = title_map.get(request.type.value, f"{request.type.value.title()} Event")
    
    event = Event(
        id=event_id,
        type=request.type.value,
        severity=request.severity.value,
        title=title,
        description=request.description,
        timestamp=request.timestamp,
        location=request.location,
        metadata=request.metadata,
        acknowledged=False
    )
    
    storage.events[event_id] = event
    
    # Also create an alert if severity is critical or warning
    if request.severity in [EventSeverity.CRITICAL, EventSeverity.WARNING]:
        alert_id = storage.alert_counter
        storage.alert_counter += 1
        
        alert = Alert(
            id=alert_id,
            type=request.type.value,
            severity=AlertSeverity(request.severity.value),
            message=request.description,
            timestamp=request.timestamp,
            played=False,
            data={
                "event_id": event_id,
                "location": request.location,
                "metadata": request.metadata
            }
        )
        storage.alerts[alert_id] = alert
    
    return {
        "success": True,
        "event_id": event_id,
        "message": "Event created successfully"
    }


@router.get("/events/list")
async def get_events(
    type: Optional[str] = None,
    limit: int = 50,
    page: int = 1,
    severity: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    """
    Get list of events
    
    Query Params:
    - type: Filter by event type
    - limit: Number of events per page (default: 50)
    - page: Page number (default: 1)
    - severity: Filter by severity
    - from_date: Start date filter (ISO format)
    - to_date: End date filter (ISO format)
    """
    events = list(storage.events.values())
    
    # Apply filters
    if type:
        events = [e for e in events if e.type == type]
    
    if severity:
        events = [e for e in events if e.severity == severity]
    
    if from_date:
        events = [e for e in events if e.timestamp >= from_date]
    
    if to_date:
        events = [e for e in events if e.timestamp <= to_date]
    
    # Sort by timestamp (most recent first)
    events.sort(key=lambda x: x.timestamp, reverse=True)
    
    # Pagination
    total = len(events)
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_events = events[start_idx:end_idx]
    
    return {
        "success": True,
        "events": [e.model_dump() for e in paginated_events],
        "total": total
    }


@router.put("/events/{id}/acknowledge")
async def acknowledge_event(id: int):
    """
    Mark an event as acknowledged/viewed
    
    Path Params:
    - id: Event ID
    """
    if id not in storage.events:
        raise HTTPException(status_code=404, detail=f"Event {id} not found")
    
    storage.events[id].acknowledged = True
    
    return {
        "success": True,
        "message": "Event acknowledged"
    }


@router.delete("/events/{id}")
async def delete_event(id: int):
    """
    Delete an event
    
    Path Params:
    - id: Event ID
    """
    if id not in storage.events:
        raise HTTPException(status_code=404, detail=f"Event {id} not found")
    
    event = storage.events.pop(id)
    
    return {
        "success": True,
        "message": f"Event '{event.title}' deleted successfully"
    }


# ============================================================================
# ALERTS ENDPOINTS
# ============================================================================

@router.get("/alerts/latest")
async def get_latest_alerts(
    limit: int = 10,
    severity: Optional[str] = None,
    unplayed_only: bool = False
):
    """
    Get latest alerts for real-time warnings
    
    Query Params:
    - limit: Number of alerts to return (default: 10)
    - severity: Filter by severity
    - unplayed_only: Only return alerts that haven't been played
    """
    alerts = list(storage.alerts.values())
    
    # Apply filters
    if severity:
        alerts = [a for a in alerts if a.severity.value == severity]
    
    if unplayed_only:
        alerts = [a for a in alerts if not a.played]
    
    # Sort by timestamp (most recent first)
    alerts.sort(key=lambda x: x.timestamp, reverse=True)
    
    # Limit results
    alerts = alerts[:limit]
    
    return {
        "success": True,
        "alerts": [a.model_dump() for a in alerts]
    }


@router.get("/alerts/stats")
async def get_alert_stats():
    """
    Get alert statistics
    
    Returns:
    - total: Total number of alerts
    - by_severity: Count by severity level
    - recent_24h: Alerts in last 24 hours
    - unplayed: Number of unplayed alerts
    """
    alerts = list(storage.alerts.values())
    
    # Count by severity
    severity_counts = {
        "critical": 0,
        "warning": 0,
        "info": 0
    }
    
    for alert in alerts:
        severity_counts[alert.severity.value] = severity_counts.get(alert.severity.value, 0) + 1
    
    # Count recent (last 24 hours)
    now = datetime.now()
    twenty_four_hours_ago = (now - timedelta(hours=24)).isoformat()
    recent_24h = len([a for a in alerts if a.timestamp >= twenty_four_hours_ago])
    
    # Count unplayed
    unplayed = len([a for a in alerts if not a.played])
    
    return {
        "success": True,
        "total": len(alerts),
        "by_severity": severity_counts,
        "recent_24h": recent_24h,
        "unplayed": unplayed
    }


@router.put("/alerts/{id}/played")
async def mark_alert_played(id: int):
    """
    Mark an alert as played
    
    Path Params:
    - id: Alert ID
    """
    if id not in storage.alerts:
        raise HTTPException(status_code=404, detail=f"Alert {id} not found")
    
    storage.alerts[id].played = True
    
    return {
        "success": True,
        "message": "Alert marked as played"
    }
