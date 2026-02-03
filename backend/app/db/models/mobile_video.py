from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.sql import func
from ..base import Base

class MobileVideo(Base):
    """
    Mobile Video Model
    ==================
    Stores videos uploaded via the Mobile App to keep them separate from
    the main ADAS dataset and Driver Monitoring dataset.
    """
    __tablename__ = "mobile_videos"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(50), index=True, unique=True)
    user_id = Column(Integer, index=True, nullable=True)
    
    # File Info
    filename = Column(String(255))
    original_video_path = Column(String(500))
    processed_video_path = Column(String(500), nullable=True)
    thumbnail_path = Column(String(500), nullable=True)
    
    # Metadata
    duration_seconds = Column(Float, nullable=True)
    file_size_mb = Column(Float, nullable=True)
    resolution = Column(String(20), nullable=True)
    
    # Analysis Results (Cached for quick history view)
    safety_score = Column(Integer, nullable=True)
    alert_count = Column(Integer, default=0)
    status = Column(String(20), default="pending") # pending, processing, completed, failed
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<MobileVideo {self.id} job={self.job_id}>"
