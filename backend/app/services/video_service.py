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
        Validate video file.
        
        Args:
            file: Uploaded video file
            
        Raises:
            ValidationError: If validation fails
        """
        filename = file.filename
        
        # Check extension
        ext = Path(filename).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Invalid video format. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}",
                details={"filename": filename, "extension": ext}
            )
        
        # Get file size - FastAPI UploadFile exposes size attribute or we read content
        # Note: We validate size here, actual file is streamed during save_uploaded_video
        if hasattr(file, 'size') and file.size is not None:
            file_size = file.size
        else:
            # Peek at content to get size, then seek back
            # This is only for validation - actual upload is streamed
            content = await file.read()
            file_size = len(content)
            await file.seek(0)
        
        # Check size
        if file_size > self.MAX_SIZE_BYTES:
            raise ValidationError(
                f"Video file too large. Max size: {settings.MAX_VIDEO_SIZE_MB} MB",
                details={
                    "filename": filename,
                    "size_mb": file_size / 1024 / 1024,
                    "max_size_mb": settings.MAX_VIDEO_SIZE_MB
                }
            )
    
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
        
        # Create job record
        repo = JobQueueRepository(self.session)
        job_data = {
            "job_id": job_id_uuid,
            "trip_id": trip_id,
            "video_filename": filename,
            "video_path": input_path,
            "result_path": output_path,
            "status": "pending",
            "progress_percent": 0,
        }
        
        try:
            job = await repo.create(**job_data)
        except Exception as e:
            error_msg = str(e).lower()
            if "invalid column name" in error_msg or "column" in error_msg:
                logger.error(f"Database schema mismatch: {e}")
                raise ValidationError(
                    "Database schema is outdated. Please run: python apply_migration.py",
                    details={
                        "error": str(e),
                        "solution": "Run migration script to update database schema",
                        "command": "python apply_migration.py"
                    }
                )
            raise
        
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
        
        # Generate unique filename
        ext = Path(job.video_filename).suffix
        safe_filename = f"{job_id}{ext}"
        input_path = self.raw_dir / safe_filename
        
        # Stream file in chunks to avoid blocking event loop
        # CRITICAL FIX: Don't load entire file into memory at once
        CHUNK_SIZE = 1024 * 1024  # 1MB chunks
        file_size = 0
        
        logger.info(f"[Job {job_id}] Starting streaming upload to {input_path}")
        
        # Save file asynchronously with chunked streaming
        async with aiofiles.open(input_path, 'wb') as f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                await f.write(chunk)
                file_size += len(chunk)
                # Event loop can process other requests between chunks
        
        # Update job with input path AND file size
        await repo.update(
            job.id, 
            video_path=str(input_path),
            file_size=file_size
        )
        
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
