"""
Vehicle Model
=============
Represents vehicles in the fleet.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..base import Base


class Vehicle(Base):
    """Vehicle table"""
    __tablename__ = "vehicles"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Vehicle identification
    license_plate = Column(String(20), unique=True, nullable=False, index=True)
    
    # Vehicle details
    vehicle_type = Column(String(50), nullable=True)  # car, truck, bus, motorcycle
    manufacturer = Column(String(100), nullable=True)  # Toyota, Honda, etc.
    model = Column(String(100), nullable=True)  # Camry, Civic, etc.
    year = Column(Integer, nullable=True)
    
    # Owner
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    owner = relationship("User", back_populates="vehicles")
    trips = relationship("Trip", back_populates="vehicle", cascade="all, delete-orphan")
    safety_events = relationship("SafetyEvent", back_populates="vehicle", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Vehicle(id={self.id}, plate='{self.license_plate}', model='{self.model}')>"
