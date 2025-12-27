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
    
    # Video details
    video_filename: str
    video_path: str
    video_size_mb: Optional[float] = None
    duration_seconds: Optional[int] = None
    fps: Optional[float] = None
    resolution: Optional[str] = None
    
    # Processing
    status: str
    progress_percent: int = 0
    result_path: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_seconds: Optional[int] = None
    
    # Foreign keys
    trip_id: Optional[int] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
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
