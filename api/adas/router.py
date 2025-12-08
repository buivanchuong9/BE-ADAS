"""
ADAS REST API Endpoints
HTTP endpoints for ADAS configuration and data
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from database import get_db
from models import ADASEvent, ADASSession
import schemas

router = APIRouter(prefix="/api/adas", tags=["ADAS"])


# =====================================================
# Pydantic Schemas
# =====================================================

class ADASConfigSchema(BaseModel):
    """ADAS Configuration"""
    enable_tsr: bool = True
    enable_fcw: bool = True
    enable_ldw: bool = True
    tsr_confidence: float = 0.45
    fcw_danger_distance: float = 15.0
    fcw_warning_distance: float = 30.0
    ldw_departure_threshold: float = 0.15
    
    class Config:
        from_attributes = True


class ADASEventSchema(BaseModel):
    """ADAS Event (alert/detection)"""
    id: Optional[int] = None
    session_id: int
    event_type: str  # 'speeding', 'collision_warning', 'lane_departure', 'sign_detected'
    severity: str  # 'info', 'warning', 'danger'
    message: str
    data: Optional[dict] = None
    timestamp: datetime
    
    class Config:
        from_attributes = True


class ADASSessionSchema(BaseModel):
    """ADAS Session"""
    id: Optional[int] = None
    driver_id: Optional[int] = None
    camera_id: Optional[int] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    total_frames: int = 0
    total_events: int = 0
    avg_speed: Optional[float] = None
    max_speed: Optional[float] = None
    statistics: Optional[dict] = None
    
    class Config:
        from_attributes = True


class ADASStatsResponse(BaseModel):
    """ADAS Statistics Response"""
    total_sessions: int
    total_events: int
    events_by_type: dict
    events_by_severity: dict
    avg_session_duration: Optional[float] = None
    recent_events: List[ADASEventSchema]


# =====================================================
# Configuration Endpoints
# =====================================================

@router.get("/config", response_model=ADASConfigSchema)
async def get_adas_config():
    """
    Get current ADAS configuration
    """
    # TODO: Load from database or config file
    from adas.config import (
        TSR_CONF_THRESHOLD,
        FCW_DANGER_DISTANCE,
        FCW_WARNING_DISTANCE,
        DEPARTURE_THRESHOLD,
    )
    
    return ADASConfigSchema(
        enable_tsr=True,
        enable_fcw=True,
        enable_ldw=True,
        tsr_confidence=TSR_CONF_THRESHOLD,
        fcw_danger_distance=FCW_DANGER_DISTANCE,
        fcw_warning_distance=FCW_WARNING_DISTANCE,
        ldw_departure_threshold=DEPARTURE_THRESHOLD,
    )


@router.post("/config", response_model=ADASConfigSchema)
async def update_adas_config(config: ADASConfigSchema):
    """
    Update ADAS configuration
    """
    # TODO: Save to database
    return config


# =====================================================
# Session Management
# =====================================================

@router.post("/sessions", response_model=ADASSessionSchema)
async def create_adas_session(
    driver_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Create new ADAS session
    """
    try:
        session = ADASSession(
            driver_id=driver_id,
            camera_id=camera_id,
            start_time=datetime.utcnow(),
            total_frames=0,
            total_events=0,
        )
        
        db.add(session)
        db.commit()
        db.refresh(session)
        
        return session
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}", response_model=ADASSessionSchema)
async def get_adas_session(
    session_id: int,
    db: Session = Depends(get_db)
):
    """
    Get ADAS session details
    """
    session = db.query(ADASSession).filter(ADASSession.id == session_id).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session


@router.put("/sessions/{session_id}/end")
async def end_adas_session(
    session_id: int,
    statistics: Optional[dict] = None,
    db: Session = Depends(get_db)
):
    """
    End ADAS session
    """
    session = db.query(ADASSession).filter(ADASSession.id == session_id).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session.end_time = datetime.utcnow()
    if statistics:
        session.statistics = statistics
    
    db.commit()
    
    return {"message": "Session ended", "session_id": session_id}


# =====================================================
# Events/Alerts
# =====================================================

@router.post("/events", response_model=ADASEventSchema)
async def create_adas_event(
    event: ADASEventSchema,
    db: Session = Depends(get_db)
):
    """
    Create ADAS event (alert/detection)
    """
    try:
        db_event = ADASEvent(**event.dict(exclude={'id'}))
        
        db.add(db_event)
        db.commit()
        db.refresh(db_event)
        
        # Update session event count
        session = db.query(ADASSession).filter(
            ADASSession.id == event.session_id
        ).first()
        
        if session:
            session.total_events += 1
            db.commit()
        
        return db_event
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events", response_model=List[ADASEventSchema])
async def get_adas_events(
    session_id: Optional[int] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get ADAS events with filters
    """
    query = db.query(ADASEvent)
    
    if session_id:
        query = query.filter(ADASEvent.session_id == session_id)
    
    if event_type:
        query = query.filter(ADASEvent.event_type == event_type)
    
    if severity:
        query = query.filter(ADASEvent.severity == severity)
    
    events = query.order_by(ADASEvent.timestamp.desc()).limit(limit).all()
    
    return events


# =====================================================
# Statistics & Analytics
# =====================================================

@router.get("/stats", response_model=ADASStatsResponse)
async def get_adas_stats(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """
    Get ADAS statistics
    """
    from sqlalchemy import func
    
    # Date range
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Total sessions
    total_sessions = db.query(func.count(ADASSession.id)).filter(
        ADASSession.start_time >= start_date
    ).scalar() or 0
    
    # Total events
    total_events = db.query(func.count(ADASEvent.id)).filter(
        ADASEvent.timestamp >= start_date
    ).scalar() or 0
    
    # Events by type
    events_by_type_query = db.query(
        ADASEvent.event_type,
        func.count(ADASEvent.id)
    ).filter(
        ADASEvent.timestamp >= start_date
    ).group_by(ADASEvent.event_type).all()
    
    events_by_type = {event_type: count for event_type, count in events_by_type_query}
    
    # Events by severity
    events_by_severity_query = db.query(
        ADASEvent.severity,
        func.count(ADASEvent.id)
    ).filter(
        ADASEvent.timestamp >= start_date
    ).group_by(ADASEvent.severity).all()
    
    events_by_severity = {severity: count for severity, count in events_by_severity_query}
    
    # Recent events
    recent_events = db.query(ADASEvent).filter(
        ADASEvent.timestamp >= start_date
    ).order_by(ADASEvent.timestamp.desc()).limit(10).all()
    
    return ADASStatsResponse(
        total_sessions=total_sessions,
        total_events=total_events,
        events_by_type=events_by_type,
        events_by_severity=events_by_severity,
        recent_events=recent_events
    )


@router.get("/sessions/{session_id}/events", response_model=List[ADASEventSchema])
async def get_session_events(
    session_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all events for a specific session
    """
    events = db.query(ADASEvent).filter(
        ADASEvent.session_id == session_id
    ).order_by(ADASEvent.timestamp.asc()).all()
    
    return events


# =====================================================
# Health Check
# =====================================================

@router.get("/health")
async def adas_health():
    """
    ADAS system health check
    """
    from adas.config import MODELS_DIR
    
    # Check if YOLO model exists
    model_path = MODELS_DIR / "yolo11n.pt"
    model_available = model_path.exists()
    
    return {
        "status": "healthy",
        "model_available": model_available,
        "model_path": str(model_path),
        "timestamp": datetime.utcnow().isoformat(),
    }
