"""
Video Model - v3.0 with SHA256 Deduplication
============================================
"""

from sqlalchemy import Column, Integer, String, BigInteger, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..base import Base


class Video(Base):
    """
    Video file with SHA256 hash for deduplication.
    
    Same video uploaded multiple times will reuse storage.
    """
    __tablename__ = "videos"
    
    id = Column(Integer, primary_key=True, index=True)
    sha256_hash = Column(String(64), unique=True, nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    duration_seconds = Column(Float)
    fps = Column(Float)
    resolution = Column(String(20))
    upload_count = Column(Integer, default=1)
    uploader_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    uploader = relationship("User", back_populates="videos")
    jobs = relationship("JobQueue", back_populates="video")
    
    def __repr__(self):
        return f"<Video {self.sha256_hash[:8]}... ({self.original_filename})>"
