"""
Alert Schemas
=============
Pydantic models for alerts and real-time notifications.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class AlertCreate(BaseModel):
    """Schema for creating an alert"""
    trip_id: Optional[int] = None
    safety_event_id: Optional[int] = None
    alert_type: str
    severity: str = Field(pattern="^(info|warning|critical)$")
    message: str
    tts_text: Optional[str] = None
    timestamp: datetime
    data: Optional[Dict[str, Any]] = None


class AlertResponse(BaseModel):
    """Schema for alert response"""
    id: int
    trip_id: Optional[int] = None
    safety_event_id: Optional[int] = None
    alert_type: str
    severity: str
    message: str
    tts_text: Optional[str] = None
    status: str
    delivered: bool
    delivered_at: Optional[datetime] = None
    played: bool
    played_at: Optional[datetime] = None
    acknowledged: bool
    acknowledged_at: Optional[datetime] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AlertAcknowledge(BaseModel):
    """Schema for acknowledging an alert"""
    acknowledged_by: int  # user_id


class WebSocketAlertMessage(BaseModel):
    """Schema for WebSocket alert message"""
    alert_id: int
    type: str
    severity: str
    message: str
    tts_text: Optional[str] = None
    timestamp: datetime
    risk_score: Optional[float] = None
    time_to_event: Optional[float] = None
    context: Optional[Dict[str, Any]] = None
    actions: List[str] = []
    snapshot_url: Optional[str] = None
