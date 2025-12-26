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
    
    # Job identification
    job_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    
    # Foreign keys
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Video details
    filename = Column(String(255), nullable=False)
    video_type = Column(Enum(VideoType), nullable=False, default=VideoType.DASHCAM)
    
    # Paths
    input_path = Column(String(500), nullable=True)
    output_path = Column(String(500), nullable=True)
    
    # Processing
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING, index=True)
    device = Column(String(10), nullable=False, default="cpu")  # cpu or cuda
    
    # Progress
    total_frames = Column(Integer, nullable=True)
    processed_frames = Column(Integer, nullable=False, default=0)
    progress_percent = Column(Float, nullable=False, default=0.0)
    
    # Results
    events_detected = Column(Integer, nullable=False, default=0)
    processing_time_seconds = Column(Float, nullable=True)
    
    # Error handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    trip = relationship("Trip", back_populates="video_jobs")
    safety_events = relationship("SafetyEvent", back_populates="video_job", cascade="all, delete-orphan")
    traffic_signs = relationship("TrafficSign", back_populates="video_job", cascade="all, delete-orphan")
    driver_states = relationship("DriverState", back_populates="video_job", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<VideoJob(id={self.id}, job_id='{self.job_id}', status='{self.status}')>"
