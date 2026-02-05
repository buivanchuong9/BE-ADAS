"""
Job Queue Model - v3.0 PostgreSQL-backed Queue
===============================================
Uses SELECT FOR UPDATE SKIP LOCKED for worker coordination.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from enum import Enum

from ..base import Base


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobQueue(Base):
    """
    Job queue with PostgreSQL locking for distributed workers.
    
    Workers claim jobs with:
        SELECT * FROM job_queue 
        WHERE status = 'pending' 
        ORDER BY priority DESC, created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    """
    __tablename__ = "job_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(UUID(as_uuid=True), unique=True, default=uuid.uuid4, index=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="SET NULL"))
    video_type = Column(String(20), default="dashcam")
    device = Column(String(10), default="cuda")
    
    # Job status
    status = Column(String(20), default=JobStatus.PENDING, index=True)
    priority = Column(Integer, default=0)  # Higher = process first
    progress_percent = Column(Integer, default=0)
    
    # Worker tracking
    worker_id = Column(String(50))
    worker_heartbeat = Column(DateTime(timezone=True))
    
    # Retry logic
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    
    # Results
    result_path = Column(String(500))
    error_message = Column(Text)
    processing_time_seconds = Column(Integer)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    video = relationship("Video", back_populates="jobs")
    trip = relationship("Trip", back_populates="jobs")
    events = relationship("SafetyEvent", back_populates="job", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="job", cascade="all, delete-orphan")
    
    def __repr__(self):
        """Safe repr that works even when detached from session."""
        try:
            # Use object.__getattribute__ to avoid triggering lazy loading
            job_id = object.__getattribute__(self, '__dict__').get('job_id', 'unknown')
            status = object.__getattribute__(self, '__dict__').get('status', 'unknown')
            return f"<JobQueue {job_id} status={status}>"
        except Exception:
            return f"<JobQueue at {hex(id(self))}>"
    
    @property
    def is_claimable(self) -> bool:
        """Check if job can be claimed by a worker."""
        return (
            self.status == JobStatus.PENDING and 
            self.attempts < self.max_attempts
        )
    
    # Backward compatibility properties for v2.0 code
    @property
    def video_path(self) -> str:
        """Get video storage path from related Video record."""
        return self.video.storage_path if self.video else ""
    
    @property
    def video_filename(self) -> str:
        """Get original video filename from related Video record."""
        return self.video.original_filename if self.video else ""
    
    @property
    def video_size_mb(self) -> float:
        """Get video size in MB from related Video record."""
        if self.video and self.video.size_bytes:
            return round(self.video.size_bytes / (1024 * 1024), 2)
        return 0.0
    
    @property
    def duration_seconds(self) -> float:
        """Get video duration from related Video record."""
        return self.video.duration_seconds if self.video else None
    
    @property
    def fps(self) -> float:
        """Get video FPS from related Video record."""
        return self.video.fps if self.video else None
    
    @property
    def resolution(self) -> str:
        """Get video resolution from related Video record."""
        return self.video.resolution if self.video else None

