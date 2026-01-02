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
    
    def __repr__(self):
        return f"<JobQueue {self.job_id} status={self.status}>"
    
    @property
    def is_claimable(self) -> bool:
        """Check if job can be claimed by a worker."""
        return (
            self.status == JobStatus.PENDING and 
            self.attempts < self.max_attempts
        )
