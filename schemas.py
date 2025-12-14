# Pydantic V2 Schemas - NO DEPRECATION WARNINGS
# Production-grade validation models

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


# Camera Schemas
class CameraBase(BaseModel):
    name: str
    type: str
    url: Optional[str] = None
    status: Optional[str] = Field(default="disconnected")
    resolution: Optional[str] = None
    frame_rate: Optional[int] = None
    instructions: Optional[str] = None
    model_config = ConfigDict()

class CameraCreate(CameraBase):
    pass

class CameraResponse(CameraBase):
    id: int
    created_at: datetime
    last_active_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Driver Schemas
class DriverBase(BaseModel):
    name: str
    license_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    address: Optional[str] = None
    model_config = ConfigDict()

class DriverCreate(DriverBase):
    pass

class DriverResponse(DriverBase):
    id: int
    total_trips: int = 0
    total_distance_km: float = 0.0
    safety_score: int = 100
    status: str
    created_at: datetime
    last_active_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Trip Schemas
class TripBase(BaseModel):
    start_location: Optional[str] = None
    driver_id: Optional[int] = None
    camera_id: Optional[int] = None
    model_config = ConfigDict()

class TripCreate(TripBase):
    pass

class TripResponse(TripBase):
    id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    distance_km: Optional[float] = None
    duration_minutes: Optional[float] = None
    end_location: Optional[str] = None
    average_speed: Optional[int] = None
    max_speed: Optional[int] = None
    status: str
    total_events: int = 0
    critical_events: int = 0
    model_config = ConfigDict(from_attributes=True)


# Event Schemas
class EventBase(BaseModel):
    event_type: str
    description: Optional[str] = None
    severity: Optional[str] = None
    location: Optional[str] = None
    metadata: Optional[str] = None
    trip_id: Optional[int] = None
    camera_id: Optional[int] = None
    driver_id: Optional[int] = None
    model_config = ConfigDict()

class EventCreate(EventBase):
    timestamp: Optional[datetime] = None

class EventResponse(EventBase):
    id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)


# Detection Schemas
class DetectionBase(BaseModel):
    class_name: str
    confidence: float
    bounding_box: str
    distance_meters: Optional[float] = None
    trip_id: Optional[int] = None
    camera_id: Optional[int] = None
    model_config = ConfigDict()

class DetectionCreate(DetectionBase):
    pass

class DetectionResponse(DetectionBase):
    id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)


# AI Model Schemas
class AIModelBase(BaseModel):
    model_id: str
    name: str
    size: Optional[str] = None
    accuracy: Optional[float] = None
    url: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    model_config = ConfigDict()

class AIModelCreate(AIModelBase):
    pass

class AIModelResponse(AIModelBase):
    id: int
    downloaded: bool = False
    file_path: Optional[str] = None
    created_at: datetime
    last_used_at: Optional[datetime] = None
    is_active: bool = False
    model_config = ConfigDict(from_attributes=True)


# Analytics Schemas
class AnalyticsBase(BaseModel):
    metric_type: str
    value: float
    unit: Optional[str] = None
    category: Optional[str] = None
    metadata: Optional[str] = None
    trip_id: Optional[int] = None
    driver_id: Optional[int] = None
    model_config = ConfigDict()

class AnalyticsCreate(AnalyticsBase):
    pass

class AnalyticsResponse(AnalyticsBase):
    id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)


# Dataset Schemas
class DatasetResponse(BaseModel):
    id: int
    filename: str
    original_filename: Optional[str] = None
    description: Optional[str] = None
    fps: Optional[float] = None
    total_frames: Optional[int] = None
    labeled_frames: Optional[int] = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    status: str
    created_at: datetime
    processed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class LabelResponse(BaseModel):
    id: int
    video_id: int
    frame_number: int
    label_data: str
    has_vehicle: bool
    has_lane: bool
    auto_labeled: bool
    verified: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
