"""
Video Service
=============
Handles video upload, validation, and storage.
"""

import os
import uuid
from pathlib import Path
from typing import Optional
import logging
import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.exceptions import ValidationError
from ..db.repositories.video_job_repo import VideoJobRepository
from ..db.models.video_job import JobStatus, VideoType
from ..schemas.video import VideoJobCreate, VideoJobResponse

logger = logging.getLogger(__name__)


class VideoService:
    """Service for video operations"""
    
    # Allowed video formats
    ALLOWED_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv'}
    
    # Max file size in bytes
    MAX_SIZE_BYTES = settings.MAX_VIDEO_SIZE_MB * 1024 * 1024
    
    def __init__(self):
        """Initialize video service"""
        # Create storage directories
        self.raw_dir = Path(settings.RAW_VIDEO_DIR)
        self.processed_dir = Path(settings.PROCESSED_VIDEO_DIR)
        self.snapshot_dir = Path(settings.SNAPSHOT_DIR)
        
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"VideoService initialized with storage: {self.raw_dir}")
    
    def validate_video(self, filename: str, file_size: int) -> None:
        """
        Validate video file.
        
        Args:
            filename: Video filename
            file_size: File size in bytes
            
        Raises:
            ValidationError: If validation fails
        """
        # Check extension
        ext = Path(filename).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Invalid video format. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}",
                details={"filename": filename, "extension": ext}
            )
        
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
        session: AsyncSession,
        filename: str,
        video_type: str = "dashcam",
        trip_id: Optional[int] = None,
        device: str = "cpu"
    ) -> VideoJobResponse:
        """
        Create a new video processing job.
        
        Args:
            session: Database session
            filename: Video filename
            video_type: "dashcam" or "in_cabin"
            trip_id: Optional trip ID
            device: "cpu" or "cuda"
            
        Returns:
            Created job
        """
        # Generate job ID
        job_id_uuid = str(uuid.uuid4())
        
        # Prepare paths
        input_path = str(self.raw_dir / f"{job_id_uuid}_{filename}")
        output_path = str(self.processed_dir / f"{job_id_uuid}_result.mp4")
        
        # Create job record
        repo = VideoJobRepository(session)
        job_data = {
            "job_id": job_id_uuid,
            "trip_id": trip_id,
            "video_filename": filename,
            "video_path": input_path,
            "result_path": output_path,
            "status": "pending",
            "progress_percent": 0,
        }
        
        job = await repo.create(**job_data)
        
        logger.info(f"Created job {job_id_uuid} for video: {filename}")
        
        return job
    
    async def save_uploaded_video(
        self,
        session: AsyncSession,
        job_id: str,
        file_content: bytes
    ) -> str:
        """
        Save uploaded video file.
        
        Args:
            session: Database session
            job_id: Job ID
            file_content: Video file bytes
            
        Returns:
            Path to saved file
        """
        repo = VideoJobRepository(session)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise ValidationError(f"Job {job_id} not found")
        
        # Generate unique filename
        ext = Path(job.filename).suffix
        safe_filename = f"{job_id}{ext}"
        input_path = self.raw_dir / safe_filename
        
        # Save file asynchronously
        async with aiofiles.open(input_path, 'wb') as f:
            await f.write(file_content)
        
        # Update job with input path
        await repo.update(job.id, input_path=str(input_path))
        
        logger.info(f"Saved video for job {job_id} to {input_path}")
        
        return str(input_path)
    
    async def get_job(
        self,
        session: AsyncSession,
        job_id: str
    ) -> Optional[VideoJobResponse]:
        """
        Get job by job_id.
        
        Args:
            session: Database session
            job_id: Job ID
            
        Returns:
            Job or None
        """
        repo = VideoJobRepository(session)
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
