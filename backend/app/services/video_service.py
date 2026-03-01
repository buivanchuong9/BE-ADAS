"""
Video Service
=============
Handles video upload, validation, and storage.
"""

import os
import uuid
import asyncio
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import logging
import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from fastapi import UploadFile

from ..core.config import settings
from ..core.exceptions import ValidationError
from ..db.repositories.job_queue_repo import JobQueueRepository
from ..db.models.job_queue import JobQueue, JobStatus
from ..schemas.video import VideoJobCreate, VideoJobResponse

logger = logging.getLogger(__name__)


class VideoService:
    """Service for video operations"""
    
    # Allowed video formats
    ALLOWED_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv'}
    
    # Max file size in bytes
    MAX_SIZE_BYTES = settings.MAX_VIDEO_SIZE_MB * 1024 * 1024
    
    def __init__(self, session: AsyncSession):
        """Initialize video service
        
        Args:
            session: Database session
        """
        self.session = session
        
        # Create storage directories
        # Use same env var as GPU worker for consistency
        self.raw_dir = Path(settings.RAW_VIDEO_DIR)
        self.processed_dir = Path(os.getenv('VIDEOS_OUTPUT_DIR', settings.PROCESSED_VIDEO_DIR))
        self.snapshot_dir = Path(settings.SNAPSHOT_DIR)
        
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"VideoService initialized with storage: {self.raw_dir}")
    
    async def validate_video(self, file: 'UploadFile') -> None:
        """
        Validate video file WITHOUT reading entire content (fast validation).
        
        Args:
            file: Uploaded video file
            
        Raises:
            ValidationError: If validation fails
        """
        filename = file.filename
        
        # Check filename
        if not filename:
            raise ValidationError(
                "Filename is required",
                details={"error": "missing_filename"}
            )
        
        # Check extension
        ext = Path(filename).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Invalid video format. Allowed formats: {', '.join(self.ALLOWED_EXTENSIONS)}",
                details={"filename": filename, "extension": ext}
            )
        
        logger.info(f"[Validation] Checking file size for: {filename}")
        
        # FAST SIZE CHECK: Try to get size WITHOUT reading entire file
        file_size = None
        
        # Method 1: Check if UploadFile has size attribute
        if hasattr(file, 'size') and file.size is not None:
            file_size = file.size
            logger.info(f"[Validation] Got size from attribute: {file_size / 1024 / 1024:.2f} MB")
        
        # Method 2: Check from underlying SpooledTemporaryFile
        elif hasattr(file, 'file') and hasattr(file.file, 'tell'):
            try:
                current_pos = file.file.tell()
                file.file.seek(0, 2)  # Seek to end
                file_size = file.file.tell()
                file.file.seek(current_pos)  # Restore position
                logger.info(f"[Validation] Got size from file.tell(): {file_size / 1024 / 1024:.2f} MB")
            except Exception as e:
                logger.warning(f"[Validation] Could not get size from tell(): {e}")
        
        # Method 3: Skip chunk reading for performance/stability
        # Reading chunks and seeking back can cause timeouts on large files
        if file_size is None:
            logger.info(f"[Validation] Size checking skipped for stream/spooled file")
            file_size = 0  # Will be validated during streaming upload
        
        # Check size if we have it
        if file_size > 0 and file_size > self.MAX_SIZE_BYTES:
            size_mb = file_size / 1024 / 1024
            raise ValidationError(
                f"Video too large! Your file: {size_mb:.1f} MB. Maximum allowed: {settings.MAX_VIDEO_SIZE_MB} MB",
                details={
                    "filename": filename,
                    "size_mb": round(size_mb, 2),
                    "max_size_mb": settings.MAX_VIDEO_SIZE_MB
                }
            )
        
        logger.info(f"[Validation] ✓ File validation passed: {filename}")
    
    async def create_job(
        self,
        filename: str,
        video_type: str = "dashcam",
        trip_id: Optional[int] = None,
        device: str = "cuda",  # GPU by default for ADAS
        user_id: Optional[int] = None,
        priority: int = 1  # 1=normal, 2=high, 3=urgent
    ) -> VideoJobResponse:
        """
        Tạo job xử lý video ADAS hoàn chỉnh.
        
        Job sẽ được GPU worker xử lý với:
        - Nhận diện vật thể (YOLOv11x)
        - Phát hiện làn đường (Segmentation)  
        - Tính khoảng cách & TTC
        - Giám sát tài xế
        - Nhận diện biển báo
        - Overlay tiếng Việt
        
        Args:
            filename: Tên file video
            video_type: "dashcam" (camera trước) hoặc "in_cabin" (camera trong cabin)
            trip_id: ID chuyến đi (optional)
            device: "cuda" (GPU) hoặc "cpu" 
            user_id: ID người dùng
            priority: Độ ưu tiên (1=thường, 2=cao, 3=khẩn cấp)
            
        Returns:
            Thông tin job đã tạo
        """
        # Validate device
        if device not in ["cuda", "cpu"]:
            device = "cuda"  # Default to GPU for better performance
        
        # Generate job ID
        job_id_uuid = str(uuid.uuid4())
        
        # Validate video type cho ADAS
        if video_type not in ["dashcam", "in_cabin"]:
            logger.warning(f"Invalid video_type '{video_type}', defaulting to 'dashcam'")
            video_type = "dashcam"
        
        # Prepare paths (MUST match _stream_upload_file format: {job_id}{ext})
        ext = Path(filename).suffix or ".mp4"
        input_path = str(self.raw_dir / f"{job_id_uuid}{ext}")
        output_path = str(self.processed_dir / f"{job_id_uuid}_result.mp4")
        
        # Create Video record first (required for foreign key)
        from app.db.models.video import Video
        import hashlib
        
        # Generate SHA256 hash for video (using filename as placeholder for now)
        # Will be updated with actual hash after file upload
        temp_hash = hashlib.sha256(f"{job_id_uuid}_{filename}".encode()).hexdigest()
        
        video = Video(
            sha256_hash=temp_hash,
            original_filename=filename,
            storage_path=input_path,
            size_bytes=0,  # Will be updated after upload
            uploader_id=user_id
        )
        self.session.add(video)
        await self.session.flush()  # Get video.id without committing
        
        # Create job record với ADAS processing info
        repo = JobQueueRepository(self.session)
        job_data = {
            "job_id": job_id_uuid,
            "video_id": video.id,  # Required foreign key
            "trip_id": trip_id,
            "video_type": video_type,
            "device": device,
            "status": "pending",
            "progress_percent": 0,
            "priority": priority,  # Higher priority for urgent processing
            "max_attempts": 3,     # Retry up to 3 times if fails
        }
        
        # Thêm metadata cho ADAS processing
        processing_config = {
            "adas_features": {
                "object_detection": True,
                "lane_detection": True,
                "distance_estimation": True,
                "driver_monitoring": video_type == "in_cabin",  # Chỉ bật nếu camera trong cabin
                "traffic_signs": True,
                "vietnamese_overlay": True
            },
            "confidence_thresholds": {
                "object_detection": 0.5,
                "lane_detection": 0.4,
                "traffic_signs": 0.6
            },
            "output_settings": {
                "resolution": "1280x720",  # HD output
                "fps_preserve": True,      # Giữ nguyên FPS input
                "compression": "h264_nvenc" if device == "cuda" else "h264"
            }
        }
        
        try:
            job = await repo.create(**job_data)
            await self.session.commit()  # Commit both video and job

            # ── Instant worker wakeup: PostgreSQL NOTIFY ──────────────────
            # Workers LISTEN on 'adas_new_job' instead of polling;
            # this fires them immediately instead of waiting up to 10 s.
            try:
                from sqlalchemy import text as _text
                await self.session.execute(
                    _text("SELECT pg_notify('adas_new_job', :jid)"),
                    {"jid": job_id_uuid}
                )
                await self.session.commit()
            except Exception as _ne:
                logger.warning(f"[Job] NOTIFY failed (non-fatal): {_ne}")

            # CRITICAL: Refresh job with eager loading to prevent MissingGreenlet
            await self.session.refresh(job)
            
            # Eager load video relationship
            from sqlalchemy import select
            from sqlalchemy.orm import joinedload
            result = await self.session.execute(
                select(JobQueue)
                .options(joinedload(JobQueue.video))
                .where(JobQueue.id == job.id)
            )
            job = result.scalar_one()
            
        except Exception as e:
            logger.error(f"Failed to create job: {e}", exc_info=True)
            await self.session.rollback()
            raise ValidationError(
                f"Failed to create job: {str(e)}",
                details={"error": str(e)}
            )
        
        logger.info(
            f"[ADAS JOB] Tạo job {job_id_uuid}:\n"
            f"  - Video: {filename} ({video_type})\n"
            f"  - Device: {device.upper()}\n" 
            f"  - Priority: {priority}\n"
            f"  - Features: Object+Lane+Distance+Driver+Traffic+VN_Overlay\n"
            f"  - User ID: {user_id}"
        )
        
        return job
    
    async def save_uploaded_video(
        self,
        job_id: str,
        file: 'UploadFile'
    ) -> str:
        """
        Save uploaded video file using streaming to avoid blocking event loop.
        
        Args:
            job_id: Job ID
            file: Uploaded video file
            
        Returns:
            Path to saved file
        """
        repo = JobQueueRepository(self.session)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise ValidationError(f"Job {job_id} not found")
        
        # Get video record
        from app.db.models.video import Video
        from sqlalchemy import select
        
        result = await self.session.execute(
            select(Video).where(Video.id == job.video_id)
        )
        video = result.scalar_one_or_none()
        
        # Generate unique filename
        ext = Path(video.original_filename if video else "video.mp4").suffix
        safe_filename = f"{job_id}{ext}"
        input_path = self.raw_dir / safe_filename
        
        # Stream file in chunks to avoid blocking event loop
        # CRITICAL: Validate size during streaming to catch oversized files early
        CHUNK_SIZE = 1024 * 1024  # 1MB chunks
        file_size = 0
        max_size = self.MAX_SIZE_BYTES
        
        logger.info(f"[Job {job_id}] Starting streaming upload to {input_path} (max {settings.MAX_VIDEO_SIZE_MB}MB)")
        
        try:
            # Save file asynchronously with chunked streaming
            async with aiofiles.open(input_path, 'wb') as f:
                while True:
                    chunk = await file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    # Check size during streaming
                    file_size += len(chunk)
                    if file_size > max_size:
                        # Stop immediately if exceeding limit
                        logger.warning(f"[Job {job_id}] File exceeded size limit during upload: {file_size / 1024 / 1024:.1f} MB")
                        # Clean up partial file
                        await f.close()
                        if input_path.exists():
                            input_path.unlink()
                        raise ValidationError(
                            f"File too large! Upload stopped at {file_size / 1024 / 1024:.1f} MB. Maximum: {settings.MAX_VIDEO_SIZE_MB} MB",
                            details={
                                "uploaded_mb": round(file_size / 1024 / 1024, 2),
                                "max_mb": settings.MAX_VIDEO_SIZE_MB
                            }
                        )
                    
                    await f.write(chunk)
                    # Event loop can process other requests between chunks
                    
        except ValidationError:
            raise  # Re-raise validation errors
        except Exception as e:
            logger.error(f"[Job {job_id}] Upload failed: {e}", exc_info=True)
            # Clean up partial file
            if input_path.exists():
                input_path.unlink()
            raise ValidationError(
                f"Failed to save video: {str(e)}",
                details={"error": str(e)}
            )
        
        # Update video record with actual file size and storage path
        # Note: In v3.0, video path is stored in Video.storage_path, not JobQueue.video_path
        if video:
            video.size_bytes = file_size
            video.storage_path = str(input_path)
            await self.session.commit()
        
        file_size_mb = file_size / (1024 * 1024)
        logger.info(
            f"[Job {job_id}] Saved video ({file_size_mb:.2f} MB) to {input_path}"
        )
        
        return str(input_path)
    
    async def get_job(
        self,
        job_id: str
    ) -> Optional[VideoJobResponse]:
        """
        Get job by job_id.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job or None
        """
        repo = JobQueueRepository(self.session)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            return None
        
        return VideoJobResponse.model_validate(job)
    
    def get_output_path(self, job_id: str, ext: str = ".mp4") -> str:
        """
        Generate output path for processed video.
        
        GPU worker saves result at: storage/result/{job_id}/result.mp4
        
        Args:
            job_id: Job ID
            ext: File extension (not used, kept for backwards compatibility)
            
        Returns:
            Output file path
        """
        # Match GPU worker output path: storage/result/{job_id}/result.mp4
        return str(self.processed_dir / job_id / "result.mp4")
    
    async def analyze_video(
        self,
        input_path: str,
        output_path: str,
        device: str = "cuda",
        video_type: str = "dashcam",
        on_progress: Optional[callable] = None
    ) -> dict:
        """
        Analyze video using AI perception pipeline.
        
        Args:
            input_path: Path to input video
            output_path: Path to save output video
            device: "cuda" or "cpu"
            video_type: "dashcam" or "in_cabin"
            on_progress: Progress callback (ignored - for API compatibility)
            
        Returns:
            Analysis results dictionary
        """
        import sys
        from pathlib import Path
        
        # Import AI pipeline
        sys.path.append(str(Path(__file__).parent.parent.parent))
        from perception.pipeline.video_pipeline_v11 import process_video
        
        logger.info(f"[AI] Starting video analysis: {input_path}")
        logger.info(f"[AI] Device: {device}, Type: {video_type}")
        
        try:
            # Call AI pipeline (synchronous) - Note: on_progress not supported by pipeline
            result = await asyncio.to_thread(
                process_video,
                input_path=input_path,
                output_path=output_path,
                device=device,
                video_type=video_type
            )
            
            logger.info(f"[AI] Analysis completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"[AI] Analysis failed: {e}", exc_info=True)
            raise
