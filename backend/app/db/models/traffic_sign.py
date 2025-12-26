"""
TrafficSign Model
=================
Represents detected traffic signs.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from ..base import Base


class SignType(str, enum.Enum):
    """Traffic sign types"""
    SPEED_LIMIT = "speed_limit"
    STOP = "stop"
    YIELD = "yield"
    NO_ENTRY = "no_entry"
    NO_PARKING = "no_parking"
    PEDESTRIAN_CROSSING = "pedestrian_crossing"
    SCHOOL_ZONE = "school_zone"
    CONSTRUCTION = "construction"
    WARNING = "warning"
    TRAFFIC_LIGHT = "traffic_light"
    OTHER = "other"


class TrafficSign(Base):
    """Traffic sign detection table"""
    __tablename__ = "traffic_signs"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=True, index=True)
    video_job_id = Column(Integer, ForeignKey("video_jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Sign details
    sign_type = Column(Enum(SignType), nullable=False, index=True)
    sign_value = Column(String(50), nullable=True)  # e.g., "50" for speed limit 50 km/h
    confidence = Column(Float, nullable=False)  # Detection confidence 0.0-1.0
    
    # Timing
    timestamp = Column(DateTime, nullable=False, index=True)
    frame_number = Column(Integer, nullable=True)
    
    # Bounding box
    bbox_x1 = Column(Float, nullable=True)
    bbox_y1 = Column(Float, nullable=True)
    bbox_x2 = Column(Float, nullable=True)
    bbox_y2 = Column(Float, nullable=True)
    
    # Additional info
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    trip = relationship("Trip", back_populates="traffic_signs")
    video_job = relationship("VideoJob", back_populates="traffic_signs")
    
    def __repr__(self):
        return f"<TrafficSign(id={self.id}, type='{self.sign_type}', value='{self.sign_value}')>"
