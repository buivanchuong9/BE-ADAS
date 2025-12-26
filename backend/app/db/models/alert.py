"""
Alert Models
============
Represents real-time alerts and alert history.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from ..base import Base


class AlertSeverity(str, enum.Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    """Alert status"""
    PENDING = "pending"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


class Alert(Base):
    """Alert table - active alerts"""
    __tablename__ = "alerts"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=True, index=True)
    safety_event_id = Column(Integer, ForeignKey("safety_events.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Alert details
    alert_type = Column(String(50), nullable=False, index=True)
    severity = Column(Enum(AlertSeverity), nullable=False, default=AlertSeverity.WARNING, index=True)
    
    # Message
    message = Column(Text, nullable=False)
    tts_text = Column(Text, nullable=True)  # Text-to-speech message
    
    # Status
    status = Column(Enum(AlertStatus), nullable=False, default=AlertStatus.PENDING, index=True)
    
    # Delivery
    delivered = Column(Integer, default=0, nullable=False)  # Boolean as Integer
    delivered_at = Column(DateTime, nullable=True)
    played = Column(Integer, default=0, nullable=False)  # TTS played
    played_at = Column(DateTime, nullable=True)
    
    # Acknowledgement
    acknowledged = Column(Integer, default=0, nullable=False)  # Boolean as Integer
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Additional data (JSON)
    data = Column(JSON, nullable=True)
    
    # Timestamps
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    trip = relationship("Trip", back_populates="alerts")
    safety_event = relationship("SafetyEvent", back_populates="alerts")
    
    def __repr__(self):
        return f"<Alert(id={self.id}, type='{self.alert_type}', severity='{self.severity}', status='{self.status}')>"


class AlertHistory(Base):
    """Alert history table - archived alerts"""
    __tablename__ = "alert_history"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Original alert ID
    alert_id = Column(Integer, nullable=False, index=True)
    
    # Foreign keys (may be null if related records deleted)
    trip_id = Column(Integer, nullable=True, index=True)
    safety_event_id = Column(Integer, nullable=True)
    
    # Alert details (denormalized for archival)
    alert_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    message = Column(Text, nullable=False)
    tts_text = Column(Text, nullable=True)
    
    # Status
    final_status = Column(String(20), nullable=False)
    
    # Timing
    timestamp = Column(DateTime, nullable=False, index=True)
    delivered_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    
    # Data snapshot
    data_snapshot = Column(JSON, nullable=True)
    
    # Archival
    archived_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    
    def __repr__(self):
        return f"<AlertHistory(id={self.id}, alert_id={self.alert_id}, type='{self.alert_type}')>"
