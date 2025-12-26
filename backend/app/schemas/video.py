"""
Video Job Schemas
=================
Pydantic models for video job requests and responses.
"""

from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Dict, Any
from datetime import datetime


class VideoJobCreate(BaseModel):
    """Schema for creating a video job"""
    filename: str
    video_type: str = Field(default="dashcam", pattern="^(dashcam|in_cabin)$")
    trip_id: Optional[int] = None
    device: str = Field(default="cpu", pattern="^(cpu|cuda)$")


class VideoJobUpdate(BaseModel):
    """Schema for updating a video job"""
    status: Optional[str] = None
    progress_percent: Optional[float] = Field(None, ge=0, le=100)
    processed_frames: Optional[int] = None
    total_frames: Optional[int] = None
    error_message: Optional[str] = None


class VideoJobResponse(BaseModel):
    """Schema for video job response"""
    id: int
    job_id: str
    filename: str
    video_type: str
    status: str
    device: str
    trip_id: Optional[int] = None
    
    # Progress
    total_frames: Optional[int] = None
    processed_frames: int
    progress_percent: float
    
    # Results
    events_detected: int
    processing_time_seconds: Optional[float] = None
    
    # Paths
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    
    # Error
    error_message: Optional[str] = None
    retry_count: int
    
    # Timestamps
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime
    
    class Config:
        from_attributes = True


class VideoUploadResponse(BaseModel):
    """Schema for video upload response"""
    job_id: str
    status: str
    message: str


class VideoJobListResponse(BaseModel):
    """Schema for paginated job list"""
    jobs: List[VideoJobResponse]
    total: int
    page: int
    page_size: int
