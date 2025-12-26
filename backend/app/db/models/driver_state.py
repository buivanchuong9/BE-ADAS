"""
DriverState Model
=================
Represents driver monitoring states (fatigue, distraction, etc.).
"""

from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..base import Base


class DriverState(Base):
    """Driver state monitoring table"""
    __tablename__ = "driver_states"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=True, index=True)
    video_job_id = Column(Integer, ForeignKey("video_jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Timing
    timestamp = Column(DateTime, nullable=False, index=True)
    frame_number = Column(Integer, nullable=True)
    
    # Fatigue indicators
    fatigue_score = Column(Float, nullable=False, default=0.0)  # 0.0-1.0
    eyes_closed = Column(Integer, default=0, nullable=False)  # Boolean as Integer
    yawning = Column(Integer, default=0, nullable=False)  # Boolean as Integer
    eye_aspect_ratio = Column(Float, nullable=True)  # EAR metric
    mouth_aspect_ratio = Column(Float, nullable=True)  # MAR metric
    
    # Distraction indicators
    distraction_score = Column(Float, nullable=False, default=0.0)  # 0.0-1.0
    looking_away = Column(Integer, default=0, nullable=False)  # Boolean as Integer
    phone_usage = Column(Integer, default=0, nullable=False)  # Boolean as Integer
    
    # Head pose
    head_pose_yaw = Column(Float, nullable=True)  # degrees
    head_pose_pitch = Column(Float, nullable=True)  # degrees
    head_pose_roll = Column(Float, nullable=True)  # degrees
    
    # Additional metrics (JSON)
    # Example: {"blink_rate": 15, "gaze_direction": "forward"}
    metrics = Column(JSON, nullable=True)
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    trip = relationship("Trip", back_populates="driver_states")
    video_job = relationship("VideoJob", back_populates="driver_states")
    
    def __repr__(self):
        return f"<DriverState(id={self.id}, fatigue={self.fatigue_score:.2f}, distraction={self.distraction_score:.2f})>"
