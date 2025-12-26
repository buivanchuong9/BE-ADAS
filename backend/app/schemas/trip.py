"""
Trip Schemas
============
Pydantic models for trip requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class TripCreate(BaseModel):
    """Schema for creating a trip"""
    driver_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    start_time: datetime
    start_location: Optional[str] = None
    start_lat: Optional[float] = Field(None, ge=-90, le=90)
    start_lon: Optional[float] = Field(None, ge=-180, le=180)


class TripUpdate(BaseModel):
    """Schema for updating a trip"""
    end_time: Optional[datetime] = None
    end_location: Optional[str] = None
    end_lat: Optional[float] = Field(None, ge=-90, le=90)
    end_lon: Optional[float] = Field(None, ge=-180, le=180)
    distance_km: Optional[float] = Field(None, ge=0)
    safety_score: Optional[float] = Field(None, ge=0, le=100)
    status: Optional[str] = None


class TripComplete(BaseModel):
    """Schema for completing a trip"""
    end_time: datetime
    distance_km: float = Field(ge=0)
    end_location: Optional[str] = None


class TripResponse(BaseModel):
    """Schema for trip response"""
    id: int
    driver_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str
    
    # Location
    start_location: Optional[str] = None
    end_location: Optional[str] = None
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    end_lat: Optional[float] = None
    end_lon: Optional[float] = None
    
    # Metrics
    distance_km: float
    duration_minutes: int
    avg_speed_kmh: Optional[float] = None
    max_speed_kmh: Optional[float] = None
    
    # Safety
    safety_score: float
    events_count: int
    critical_events_count: int
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TripListResponse(BaseModel):
    """Schema for paginated trip list"""
    trips: List[TripResponse]
    total: int
    page: int
    page_size: int


class TripStats(BaseModel):
    """Schema for trip statistics"""
    total_trips: int
    total_distance_km: float
    total_duration_minutes: int
    avg_safety_score: float
    total_events: int
