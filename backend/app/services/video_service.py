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
        if hasattr(file, 'size') and file.size is not None:
            file_size = file.size
        else:
            # Read file to get size, then seek back
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
        repo = VideoJobRepository(self.session)
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
        job_id: str,
        file: 'UploadFile'
    ) -> str:
        """
        Save uploaded video file.
        
        Args:
            job_id: Job ID
            file: Uploaded video file
            
        Returns:
            Path to saved file
        """
        repo = VideoJobRepository(self.session)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise ValidationError(f"Job {job_id} not found")
        
        # Generate unique filename
        ext = Path(job.video_filename).suffix
        safe_filename = f"{job_id}{ext}"
        input_path = self.raw_dir / safe_filename
        
        # Read file content
        file_content = await file.read()
        
        # Save file asynchronously
        async with aiofiles.open(input_path, 'wb') as f:
            await f.write(file_content)
        
        # Update job with input path
        await repo.update(job.id, video_path=str(input_path))
        
        logger.info(f"Saved video for job {job_id} to {input_path}")
        
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
        repo = VideoJobRepository(self.session)
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
