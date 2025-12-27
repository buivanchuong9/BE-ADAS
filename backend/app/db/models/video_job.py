"""
VideoJob Model
==============
Represents video processing jobs.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from ..base import Base


class VideoType(str, enum.Enum):
    """Video type"""
    DASHCAM = "dashcam"
    IN_CABIN = "in_cabin"


class JobStatus(str, enum.Enum):
    """Job processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoJob(Base):
    """Video job table"""
    __tablename__ = "video_jobs"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Job identification (for API compatibility)
    job_id = Column(String(36), unique=True, nullable=True, index=True)  # UUID for legacy API
    
    # Foreign keys
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Video details
    video_filename = Column(String(255), nullable=False)
    video_path = Column(String(500), nullable=False)
    video_size_mb = Column(Float, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    fps = Column(Float, nullable=True)
    resolution = Column(String(50), nullable=True)  # e.g., 1920x1080
    
    # Processing
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending, processing, completed, failed
    progress_percent = Column(Integer, nullable=False, default=0)
    result_path = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    processing_time_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    trip = relationship("Trip", back_populates="video_jobs")
    
    def __repr__(self):
        return f"<VideoJob(id={self.id}, status='{self.status}')>"
