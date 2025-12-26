"""
Safety Event Schemas
====================
Pydantic models for safety events.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class SafetyEventCreate(BaseModel):
    """Schema for creating a safety event"""
    trip_id: int
    video_job_id: int
    vehicle_id: Optional[int] = None
    event_type: str
    severity: str = Field(pattern="^(info|warning|critical)$")
    risk_score: float = Field(ge=0.0, le=1.0)
    description: str
    explanation: Optional[str] = None
    timestamp: datetime
    frame_number: Optional[int] = None
    time_to_event: Optional[float] = None
    context_data: Optional[Dict[str, Any]] = None
    snapshot_path: Optional[str] = None


class SafetyEventResponse(BaseModel):
    """Schema for safety event response"""
    id: int
    trip_id: int
    video_job_id: int
    vehicle_id: Optional[int] = None
    event_type: str
    severity: str
    risk_score: float
    description: str
    explanation: Optional[str] = None
    timestamp: datetime
    frame_number: Optional[int] = None
    time_to_event: Optional[float] = None
    context_data: Optional[Dict[str, Any]] = None
    snapshot_path: Optional[str] = None
    video_clip_path: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class SafetyEventListResponse(BaseModel):
    """Schema for paginated event list"""
    events: List[SafetyEventResponse]
    total: int
    page: int
    page_size: int


class EventStats(BaseModel):
    """Schema for event statistics"""
    total_events: int
    critical_events: int
    warning_events: int
    info_events: int
    events_by_type: Dict[str, int]
