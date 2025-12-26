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
    plate_number = Column(String(20), unique=True, nullable=False, index=True)
    vin = Column(String(17), unique=True, nullable=True)  # Vehicle Identification Number
    
    # Vehicle details
    make = Column(String(50), nullable=True)  # Toyota, Honda, etc.
    model = Column(String(50), nullable=True)  # Camry, Civic, etc.
    year = Column(Integer, nullable=True)
    color = Column(String(30), nullable=True)
    
    # Owner
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Additional info
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    owner = relationship("User", back_populates="vehicles")
    trips = relationship("Trip", back_populates="vehicle", cascade="all, delete-orphan")
    safety_events = relationship("SafetyEvent", back_populates="vehicle", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Vehicle(id={self.id}, plate='{self.plate_number}', model='{self.model}')>"
