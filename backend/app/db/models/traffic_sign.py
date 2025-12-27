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
    
    # Timing
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Sign details
    sign_type = Column(String(50), nullable=False, index=True)  # SPEED_30, SPEED_50, STOP, etc.
    confidence = Column(Float, nullable=False)
    speed_limit = Column(Integer, nullable=True)  # For speed limit signs
    current_speed = Column(Float, nullable=True)
    is_violation = Column(Integer, default=0, nullable=False)  # BIT in SQL Server
    
    # Location
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    snapshot_path = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    trip = relationship("Trip", back_populates="traffic_signs")
    
    def __repr__(self):
        return f"<TrafficSign(id={self.id}, type='{self.sign_type}', confidence={self.confidence:.2f})>"
