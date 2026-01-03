"""
Video Service
=============
Handles video upload, validation, and storage.
"""

import os
import uuid
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
        self.raw_dir = Path(settings.RAW_VIDEO_DIR)
        self.processed_dir = Path(settings.PROCESSED_VIDEO_DIR)
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
        
        # Method 3: Only read small chunk to validate (DON'T read entire file!)
        if file_size is None:
            try:
                # Read only first 1MB to validate file is readable
                chunk = await file.read(1024 * 1024)  # 1MB only
                if len(chunk) == 1024 * 1024:
                    # File is at least 1MB, will validate full size during streaming
                    logger.warning(f"[Validation] Could not determine size, will validate during upload")
                    file_size = 0  # Placeholder - will check during streaming
                else:
                    file_size = len(chunk)
                await file.seek(0)  # Reset to beginning
                logger.info(f"[Validation] Got size from chunk read: {file_size / 1024 / 1024:.2f} MB")
            except Exception as e:
                logger.error(f"[Validation] Failed to read file: {e}")
                raise ValidationError(
                    f"Cannot read uploaded file: {str(e)}",
                    details={"filename": filename, "error": str(e)}
                )
        
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
        device: str = "cpu",
        user_id: Optional[int] = None
    ) -> VideoJobResponse:
        """
        Create a new video processing job.
        
        Args:
            filename: Video filename
            video_type: "dashcam" or "in_cabin"
            trip_id: Optional trip ID
            device: "cpu" or "cuda"
            user_id: Optional user ID
            
        Returns:
            Created job
        """
        # Generate job ID
        job_id_uuid = str(uuid.uuid4())
        
        # Prepare paths
        input_path = str(self.raw_dir / f"{job_id_uuid}_{filename}")
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
        
        # Create job record with video_id
        repo = JobQueueRepository(self.session)
        job_data = {
            "job_id": job_id_uuid,
            "video_id": video.id,  # Required foreign key
            "trip_id": trip_id,
            "video_type": video_type,
            "device": device,
            "status": "pending",
            "progress_percent": 0,
        }
        
        try:
            job = await repo.create(**job_data)
            await self.session.commit()  # Commit both video and job
        except Exception as e:
            logger.error(f"Failed to create job: {e}", exc_info=True)
            await self.session.rollback()
            raise ValidationError(
                f"Failed to create job: {str(e)}",
                details={"error": str(e)}
            )
        
        logger.info(f"Created job {job_id_uuid} for video: {filename}")
        
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
        
        # Update job with input path
        await repo.update(
            job.id, 
            video_path=str(input_path)
        )
        
        # Update video record with actual file size
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
        
        Args:
            job_id: Job ID
            ext: File extension
            
        Returns:
            Output file path
        """
        output_filename = f"{job_id}_result{ext}"
        return str(self.processed_dir / output_filename)
