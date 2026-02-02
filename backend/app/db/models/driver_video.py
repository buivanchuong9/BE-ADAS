"""
DriverMonitoringVideo Model
===========================
Stores processed driver monitoring videos specifically for the "Sample Gallery" 
or "History" section.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..base import Base


class DriverMonitoringVideo(Base):
    """
    Table specifically for Driver Monitoring Samples/History.
    Users can view these in the 'Video Mẫu' (Sample Videos) section.
    """
    __tablename__ = "driver_monitoring_videos"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Link to the original processing job (optional)
    job_id = Column(String(50), index=True, nullable=True)
    
    # Display Info
    title = Column(String(200), nullable=True)  # e.g. "Scenario: Drowsy Driver at Night"
    description = Column(Text, nullable=True)
    
    # File Paths
    original_video_path = Column(String(500), nullable=False)
    processed_video_path = Column(String(500), nullable=True)
    thumbnail_path = Column(String(500), nullable=True)
    
    # Stats / Metadata
    duration_seconds = Column(Float, nullable=True)
    fps = Column(Float, nullable=True)
    
    # Analysis Summary (JSON)
    # Ex: {"fatigue_events": 5, "distraction_events": 2, "driver_name": "Unknown"}
    analysis_summary = Column(JSON, nullable=True)
    
    # Admin Control
    is_sample = Column(Boolean, default=False)  # If True, shows up in public "Sample" section
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<DriverMonitoringVideo(id={self.id}, title='{self.title}')>"
