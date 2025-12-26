"""
Trip Model
==========
Represents driving trips.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from ..base import Base


class TripStatus(str, enum.Enum):
    """Trip status"""
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Trip(Base):
    """Trip table"""
    __tablename__ = "trips"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    driver_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Trip details
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(Enum(TripStatus), nullable=False, default=TripStatus.ONGOING, index=True)
    
    # Location
    start_location = Column(String(200), nullable=True)
    end_location = Column(String(200), nullable=True)
    start_lat = Column(Float, nullable=True)
    start_lon = Column(Float, nullable=True)
    end_lat = Column(Float, nullable=True)
    end_lon = Column(Float, nullable=True)
    
    # Metrics
    distance_km = Column(Float, nullable=False, default=0.0)
    duration_minutes = Column(Integer, nullable=False, default=0)
    avg_speed_kmh = Column(Float, nullable=True)
    max_speed_kmh = Column(Float, nullable=True)
    
    # Safety
    safety_score = Column(Float, nullable=False, default=100.0)  # 0-100
    events_count = Column(Integer, nullable=False, default=0)
    critical_events_count = Column(Integer, nullable=False, default=0)
    
    # Additional info
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    driver = relationship("User", back_populates="trips")
    vehicle = relationship("Vehicle", back_populates="trips")
    video_jobs = relationship("VideoJob", back_populates="trip", cascade="all, delete-orphan")
    safety_events = relationship("SafetyEvent", back_populates="trip", cascade="all, delete-orphan")
    traffic_signs = relationship("TrafficSign", back_populates="trip", cascade="all, delete-orphan")
    driver_states = relationship("DriverState", back_populates="trip", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="trip", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Trip(id={self.id}, driver_id={self.driver_id}, status='{self.status}')>"
