"""
Video Resolution Validator & Analytics Tracker
==============================================
Validates video resolution and tracks analytics for ML optimization.
"""

import cv2
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ValidationError
from ..db.models.video_analytics import VideoAnalytics

logger = logging.getLogger(__name__)


class VideoResolutionValidator:
    """
    Validates video resolution and provides warnings for high-res videos.
    """
    
    # Resolution thresholds
    WARN_THRESHOLD_PIXELS = 2560 * 1440  # 2K (Quad HD)
    MAX_RECOMMENDED_PIXELS = 1920 * 1080  # Full HD
    
    @classmethod
    def validate_and_get_info(cls, video_path: str) -> Dict[str, Any]:
        """
        Validate video and extract resolution info.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dict with video info and warnings
            
        Raises:
            ValidationError: If video cannot be opened
        """
        if not Path(video_path).exists():
            raise ValidationError(f"Video file not found: {video_path}")
        
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise ValidationError(
                "Không thể mở video. File có thể bị hỏng hoặc định dạng không hỗ trợ."
            )
        
        try:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0
            
            pixels = width * height
            resolution_category = VideoAnalytics.categorize_resolution(width, height)
            should_warn = cls.should_warn_high_resolution(width, height)
            
            # Get codec info
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
            
            info = {
                "width": width,
                "height": height,
                "fps": fps,
                "frame_count": frame_count,
                "duration_seconds": duration,
                "resolution": f"{width}x{height}",
                "resolution_category": resolution_category,
                "pixels": pixels,
                "codec": codec,
                "should_warn": should_warn,
                "warning_message": None,
                "estimated_time": None
            }
            
            if should_warn:
                # Estimate processing time
                estimated_fps = 20.0  # GPU processing speed
                estimated_time = frame_count / estimated_fps
                
                info["warning_message"] = (
                    f"⚠️ Video có độ phân giải cao ({width}x{height} - {resolution_category}). "
                    f"Thời gian xử lý ước tính: ~{int(estimated_time)}s. "
                    f"Hệ thống sẽ phân tích và tối ưu hóa cho lần sau."
                )
                info["estimated_time"] = estimated_time
                
                logger.warning(
                    f"High resolution video: {width}x{height} ({resolution_category}), "
                    f"{frame_count} frames, estimated {estimated_time:.1f}s"
                )
            
            return info
            
        finally:
            cap.release()
    
    @classmethod
    def should_warn_high_resolution(cls, width: int, height: int) -> bool:
        """Check if should warn about high resolution."""
        return width * height >= cls.WARN_THRESHOLD_PIXELS
    
    @classmethod
    async def track_analytics(
        cls,
        session: AsyncSession,
        job_id: str,
        video_info: Dict[str, Any],
        processing_result: Optional[Dict[str, Any]] = None
    ):
        """
        Track video analytics for ML optimization.
        
        Args:
            session: Database session
            job_id: Job ID
            video_info: Video information dict
            processing_result: Processing result (optional, updated after completion)
        """
        try:
            # Create or update analytics record
            analytics = VideoAnalytics(
                job_id=job_id,
                video_filename=video_info.get("filename"),
                video_format=video_info.get("format", "mp4"),
                width=video_info.get("width"),
                height=video_info.get("height"),
                resolution_category=video_info.get("resolution_category"),
                file_size_mb=video_info.get("file_size_mb"),
                duration_seconds=video_info.get("duration_seconds"),
                fps=video_info.get("fps"),
                bitrate_kbps=video_info.get("bitrate_kbps"),
                had_high_resolution_warning=video_info.get("should_warn", False)
            )
            
            # Add processing results if available
            if processing_result:
                analytics.processing_time_seconds = processing_result.get("processing_time")
                analytics.processing_fps = processing_result.get("processing_fps")
                analytics.device_used = processing_result.get("device", "cuda")
                analytics.batch_size_used = processing_result.get("batch_size")
                analytics.gpu_memory_mb = processing_result.get("gpu_memory_mb")
                analytics.events_detected = processing_result.get("events_count", 0)
                analytics.output_codec = processing_result.get("output_codec", "h264")
                analytics.encoding_time_seconds = processing_result.get("encoding_time")
                analytics.success = processing_result.get("success", True)
                analytics.error_message = processing_result.get("error")
                analytics.had_encoding_issues = processing_result.get("encoding_failed", False)
                
                # Generate auto-recommendations based on results
                recommendations = cls._generate_recommendations(video_info, processing_result)
                analytics.auto_recommendations = recommendations
            
            session.add(analytics)
            await session.commit()
            
            logger.info(f"📊 Analytics tracked for job {job_id}: {video_info.get('resolution')}, {video_info.get('resolution_category')}")
            
        except Exception as e:
            logger.error(f"Failed to track analytics for {job_id}: {e}")
            await session.rollback()
    
    @classmethod
    def _generate_recommendations(
        cls,
        video_info: Dict[str, Any],
        processing_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate auto-optimization recommendations based on processing results.
        
        Returns:
            Dict with recommendations
        """
        recommendations = {}
        
        # Recommend batch size based on GPU memory usage
        gpu_mem = processing_result.get("gpu_memory_mb", 0)
        if gpu_mem > 0:
            if gpu_mem < 500:
                recommendations["recommended_batch_size"] = 32
            elif gpu_mem < 1000:
                recommendations["recommended_batch_size"] = 24
            else:
                recommendations["recommended_batch_size"] = 16
        
        # Recommend resize for very high resolution
        pixels = video_info.get("pixels", 0)
        if pixels > 3840 * 2160:  # 4K
            recommendations["recommended_resize"] = "1920x1080"
            recommendations["reason"] = "4K+ resolution, recommend downscale to FHD for faster processing"
        elif pixels > 2560 * 1440:  # 2K
            recommendations["recommended_resize"] = "1280x720"
            recommendations["reason"] = "2K resolution, recommend downscale to HD for optimal speed/quality balance"
        
        return recommendations
