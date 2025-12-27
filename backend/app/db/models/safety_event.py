"""
SafetyEvent Model
=================
Represents detected safety events (lane departure, collision warning, etc.).
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from ..base import Base


class EventType(str, enum.Enum):
    """Safety event types"""
    LANE_DEPARTURE = "lane_departure"
    COLLISION_WARNING = "collision_warning"
    FORWARD_COLLISION = "forward_collision"
    PEDESTRIAN_DETECTED = "pedestrian_detected"
    SPEED_LIMIT_VIOLATION = "speed_limit_violation"
    TRAFFIC_SIGN_VIOLATION = "traffic_sign_violation"
    DRIVER_FATIGUE = "driver_fatigue"
    DRIVER_DISTRACTION = "driver_distraction"
    UNSAFE_DISTANCE = "unsafe_distance"
    HARD_BRAKING = "hard_braking"
    SHARP_TURN = "sharp_turn"
    OTHER = "other"


class EventSeverity(str, enum.Enum):
    """Event severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SafetyEvent(Base):
    """Safety event table"""
    __tablename__ = "safety_events"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=True, index=True)
    video_job_id = Column(Integer, ForeignKey("video_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Event details
    event_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)  # CRITICAL, WARNING, INFO
    timestamp = Column(DateTime, nullable=False, index=True)
    frame_number = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    
    # Location
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    speed_kmh = Column(Float, nullable=True)
    
    # Metadata (JSON string)
    meta_data = Column(Text, nullable=True)
    snapshot_path = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    trip = relationship("Trip", back_populates="safety_events")
    video_job = relationship("VideoJob")
    
    def __repr__(self):
        return f"<SafetyEvent(id={self.id}, type='{self.event_type}', severity='{self.severity}')>"
