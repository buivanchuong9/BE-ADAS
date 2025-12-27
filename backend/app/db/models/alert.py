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
    
    # Alert details
    alert_type = Column(String(50), nullable=False, index=True)  # FCW, LDW, DMS, SPEED
    severity = Column(String(20), nullable=False, index=True)  # CRITICAL, WARNING, INFO
    message = Column(String(255), nullable=False)
    message_vi = Column(String(255), nullable=True)  # Vietnamese message
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Acknowledgement
    is_acknowledged = Column(Integer, default=0, nullable=False)  # BIT
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Metadata (JSON string in NVARCHAR(MAX))
    metadata = Column(Text, nullable=True)
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    trip = relationship("Trip", back_populates="alerts")
    
    def __repr__(self):
        return f"<Alert(id={self.id}, type='{self.alert_type}', severity='{self.severity}')>"


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
