"""
Job Queue Repository - PostgreSQL v3.0
======================================
Repository pattern for job_queue table operations.

Author: Senior ADAS Engineer
Date: 2026-01-03
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.db.models.job_queue import JobQueue


class JobQueueRepository(BaseRepository[JobQueue]):
    """Repository for job queue operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(JobQueue, session)
    
    async def get_all(self) -> List[JobQueue]:
        """Get all jobs"""
        result = await self.session.execute(
            select(JobQueue).order_by(JobQueue.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def get_by_job_id(self, job_id: str) -> Optional[JobQueue]:
        """Get job by UUID job_id"""
        result = await self.session.execute(
            select(JobQueue).where(JobQueue.job_id == job_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_status(self, status: str) -> List[JobQueue]:
        """Get jobs by status"""
        result = await self.session.execute(
            select(JobQueue)
            .where(JobQueue.status == status)
            .order_by(JobQueue.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def get_pending_jobs(self, limit: int = 10) -> List[JobQueue]:
        """Get pending jobs ordered by priority and creation time"""
        result = await self.session.execute(
            select(JobQueue)
            .where(JobQueue.status == 'pending')
            .order_by(JobQueue.priority.desc(), JobQueue.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics from job queue.
        
        Returns:
            Dictionary with storage stats including total size, counts by status
        """
        # Count jobs by status
        status_counts = await self.session.execute(
            select(
                JobQueue.status,
                func.count(JobQueue.id).label('count')
            )
            .group_by(JobQueue.status)
        )
        
        stats = {
            'total_jobs': 0,
            'pending': 0,
            'processing': 0,
            'completed': 0,
            'failed': 0
        }
        
        for row in status_counts:
            stats['total_jobs'] += row.count
            stats[row.status] = row.count
        
        return stats
    
    async def update_progress(
        self,
        job_id: str,
        progress_percent: int,
        current_step: Optional[str] = None
    ) -> Optional[JobQueue]:
        """Update job progress"""
        job = await self.get_by_job_id(job_id)
        if not job:
            return None
        
        job.progress_percent = progress_percent
        if current_step:
            job.current_step = current_step
        job.updated_at = datetime.utcnow()
        
        await self.session.commit()
        await self.session.refresh(job)
        return job
    
    async def mark_completed(
        self,
        job_id: str,
        result_path: str,
        processing_time_seconds: int
    ) -> Optional[JobQueue]:
        """Mark job as completed"""
        job = await self.get_by_job_id(job_id)
        if not job:
            return None
        
        job.status = 'completed'
        job.progress_percent = 100
        job.result_path = result_path
        job.processing_time_seconds = processing_time_seconds
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        
        await self.session.commit()
        await self.session.refresh(job)
        return job
    
    async def mark_failed(
        self,
        job_id: str,
        error_message: str
    ) -> Optional[JobQueue]:
        """Mark job as failed"""
        job = await self.get_by_job_id(job_id)
        if not job:
            return None
        
        job.status = 'failed'
        job.error_message = error_message
        job.updated_at = datetime.utcnow()
        job.attempts += 1
        
        await self.session.commit()
        await self.session.refresh(job)
        return job
    
    async def cleanup_old_jobs(self, days: int = 90) -> int:
        """
        Delete jobs older than specified days.
        
        Args:
            days: Number of days to keep
            
        Returns:
            Number of deleted jobs
        """
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        result = await self.session.execute(
            select(JobQueue).where(JobQueue.created_at < cutoff_date)
        )
        old_jobs = list(result.scalars().all())
        
        for job in old_jobs:
            await self.session.delete(job)
        
        await self.session.commit()
        return len(old_jobs)
