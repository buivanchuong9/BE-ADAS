"""
DriverState Model
=================
Represents driver monitoring states (fatigue, distraction, etc.).
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
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
    
    # Timing
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Drowsiness detection
    is_drowsy = Column(Integer, default=0, nullable=False)  # BIT in SQL Server
    drowsy_confidence = Column(Float, nullable=True)
    drowsy_reason = Column(String(50), nullable=True)  # EYE_CLOSED, YAWNING, HEAD_TILT
    ear_value = Column(Float, nullable=True)  # Eye Aspect Ratio
    mar_value = Column(Float, nullable=True)  # Mouth Aspect Ratio
    head_pose = Column(String(100), nullable=True)
    snapshot_path = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    trip = relationship("Trip", back_populates="driver_states")
    
    def __repr__(self):
        return f"<DriverState(id={self.id}, is_drowsy={self.is_drowsy})>"
