"""
Video Job Repository
====================
Data access layer for video processing jobs.
"""

from typing import Optional, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from .base import BaseRepository
from ..models.video_job import VideoJob, JobStatus


class VideoJobRepository(BaseRepository[VideoJob]):
    """Repository for video job operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(VideoJob, session)
    
    async def get_by_job_id(self, job_id: str) -> Optional[VideoJob]:
        """Get job by UUID job_id"""
        result = await self.session.execute(
            select(VideoJob).where(VideoJob.job_id == job_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_status(
        self,
        status: JobStatus,
        limit: int = 10
    ) -> List[VideoJob]:
        """Get jobs by status"""
        result = await self.session.execute(
            select(VideoJob)
            .where(VideoJob.status == status)
            .order_by(desc(VideoJob.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_pending_jobs(self, limit: int = 10) -> List[VideoJob]:
        """Get pending jobs for processing"""
        return await self.get_by_status(JobStatus.PENDING, limit)
    
    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None
    ) -> Optional[VideoJob]:
        """Update job status"""
        job = await self.get_by_job_id(job_id)
        if not job:
            return None
        
        update_data = {"status": status}
        
        if status == JobStatus.PROCESSING and not job.started_at:
            update_data["started_at"] = datetime.utcnow()
        elif status == JobStatus.COMPLETED:
            update_data["completed_at"] = datetime.utcnow()
        elif status == JobStatus.FAILED:
            update_data["completed_at"] = datetime.utcnow()
            if error_message:
                update_data["error_message"] = error_message
        
        return await self.update(job.id, **update_data)
    
    async def update_progress(
        self,
        job_id: str,
        processed_frames: int,
        total_frames: int
    ) -> Optional[VideoJob]:
        """Update job progress"""
        job = await self.get_by_job_id(job_id)
        if not job:
            return None
        
        progress_percent = (processed_frames / total_frames * 100) if total_frames > 0 else 0
        
        return await self.update(
            job.id,
            processed_frames=processed_frames,
            total_frames=total_frames,
            progress_percent=progress_percent
        )
    
    async def get_by_trip(self, trip_id: int) -> List[VideoJob]:
        """Get all jobs for a trip"""
        result = await self.session.execute(
            select(VideoJob)
            .where(VideoJob.trip_id == trip_id)
            .order_by(desc(VideoJob.created_at))
        )
        return list(result.scalars().all())
