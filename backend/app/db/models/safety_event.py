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
    video_job_id = Column(Integer, ForeignKey("video_jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Event details
    event_type = Column(Enum(EventType), nullable=False, index=True)
    severity = Column(Enum(EventSeverity), nullable=False, default=EventSeverity.WARNING, index=True)
    
    # Risk assessment
    risk_score = Column(Float, nullable=False, default=0.0)  # 0.0-1.0
    time_to_event = Column(Float, nullable=True)  # seconds (predictive)
    
    # Timing
    timestamp = Column(DateTime, nullable=False, index=True)
    frame_number = Column(Integer, nullable=True)
    
    # Description
    description = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)  # Why this event was triggered
    
    # Context data (JSON)
    # Example: {"lane_quality": 0.85, "traffic_density": "medium", "closest_vehicle_distance": 15.0}
    context_data = Column(JSON, nullable=True)
    
    # Media
    snapshot_path = Column(String(500), nullable=True)
    video_clip_path = Column(String(500), nullable=True)
    
    # Location (if available)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    trip = relationship("Trip", back_populates="safety_events")
    video_job = relationship("VideoJob", back_populates="safety_events")
    vehicle = relationship("Vehicle", back_populates="safety_events")
    alerts = relationship("Alert", back_populates="safety_event", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<SafetyEvent(id={self.id}, type='{self.event_type}', severity='{self.severity}')>"
