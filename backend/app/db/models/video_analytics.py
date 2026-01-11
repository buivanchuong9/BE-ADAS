"""
Video Analytics Tracking - ML Self-Learning
===========================================
Tracks video processing metrics to learn optimal parameters over time.

Features:
- Resolution analysis
- Processing time prediction
- Quality metrics
- Auto-optimization recommendations
"""

from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, JSON, Text
from sqlalchemy.sql import func
from ..db.base import Base


class VideoAnalytics(Base):
    """
    Video analytics tracking table for ML self-learning.
    
    Stores processing metrics to learn patterns and optimize parameters.
    """
    __tablename__ = "video_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Video metadata
    job_id = Column(String(255), nullable=False, index=True)
    video_filename = Column(String(512))
    video_format = Column(String(50))  # mp4, avi, mov, mkv
    
    # Resolution
    width = Column(Integer)  # pixels
    height = Column(Integer)  # pixels
    resolution_category = Column(String(50))  # SD, HD, FHD, 2K, 4K, 8K
    
    # File metrics
    file_size_mb = Column(Float)
    duration_seconds = Column(Float)
    fps = Column(Float)
    bitrate_kbps = Column(Float)
    
    # Processing metrics
    processing_time_seconds = Column(Float)
    processing_fps = Column(Float)  # frames processed per second
    device_used = Column(String(20))  # cpu, cuda
    batch_size_used = Column(Integer)
    gpu_memory_mb = Column(Float, nullable=True)
    
    # Quality metrics
    events_detected = Column(Integer, default=0)
    output_codec = Column(String(50))  # h264, mp4v
    encoding_time_seconds = Column(Float, nullable=True)
    
    # Status
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    # Warnings
    had_high_resolution_warning = Column(Boolean, default=False)
    had_encoding_issues = Column(Boolean, default=False)
    
    # Recommendations (JSON)
    # {"recommended_batch_size": 12, "recommended_resize": "1280x720"}
    auto_recommendations = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    def __repr__(self):
        return f"<VideoAnalytics {self.job_id} - {self.resolution_category}>"
    
    @property
    def resolution(self):
        """Get resolution string."""
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return None
    
    @property
    def estimated_processing_time(self) -> float:
        """
        Estimate processing time based on resolution and duration.
        Uses learned coefficients from past data.
        """
        if not self.duration_seconds or not self.width or not self.height:
            return 0.0
        
        # Simple estimation formula (will be improved with ML)
        pixels_per_frame = self.width * self.height
        total_frames = self.duration_seconds * (self.fps or 30)
        
        # ~20 fps processing speed on GPU (from observed data)
        fps_estimate = 20.0 if self.device_used == "cuda" else 6.0
        
        return total_frames / fps_estimate
    
    @classmethod
    def categorize_resolution(cls, width: int, height: int) -> str:
        """Categorize resolution into standard categories."""
        pixels = width * height
        
        if pixels >= 7680 * 4320:  # 8K
            return "8K"
        elif pixels >= 3840 * 2160:  # 4K
            return "4K"
        elif pixels >= 2560 * 1440:  # 2K
            return "2K"
        elif pixels >= 1920 * 1080:  # Full HD
            return "FHD"
        elif pixels >= 1280 * 720:  # HD
            return "HD"
        else:  # SD
            return "SD"
    
    @classmethod
    def should_warn_high_resolution(cls, width: int, height: int) -> bool:
        """Check if resolution is high enough to warrant a warning."""
        # Warn for 2K and above
        return width * height >= 2560 * 1440
