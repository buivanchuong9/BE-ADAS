"""
Job Queue Repository - v3.0
===========================
PostgreSQL-backed job queue with SELECT FOR UPDATE SKIP LOCKED.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, update, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.job_queue import JobQueue, JobStatus
from ..models.video import Video

logger = logging.getLogger(__name__)


class JobQueueRepository:
    """
    Repository for job queue operations with PostgreSQL locking.
    
    Supports distributed workers with atomic job claiming.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_job(
        self,
        video_id: int,
        video_type: str = "dashcam",
        device: str = "cuda",
        priority: int = 0,
        trip_id: Optional[int] = None
    ) -> JobQueue:
        """Create a new job in pending state."""
        job = JobQueue(
            video_id=video_id,
            video_type=video_type,
            device=device,
            priority=priority,
            trip_id=trip_id,
            status=JobStatus.PENDING
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job
    
    async def claim_job(self, worker_id: str) -> Optional[JobQueue]:
        """
        Atomically claim the next available job.
        
        Uses SELECT FOR UPDATE SKIP LOCKED to prevent conflicts
        between multiple workers.
        
        Args:
            worker_id: Unique identifier for the claiming worker
            
        Returns:
            Claimed job or None if no jobs available
        """
        # Raw SQL for proper FOR UPDATE SKIP LOCKED
        claim_sql = text("""
            UPDATE job_queue 
            SET status = :processing,
                worker_id = :worker_id,
                worker_heartbeat = NOW(),
                started_at = NOW(),
                attempts = attempts + 1
            WHERE id = (
                SELECT id FROM job_queue
                WHERE status = :pending
                  AND attempts < max_attempts
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *
        """)
        
        result = await self.session.execute(
            claim_sql,
            {
                "processing": JobStatus.PROCESSING,
                "pending": JobStatus.PENDING,
                "worker_id": worker_id
            }
        )
        
        row = result.fetchone()
        if row:
            logger.info(f"Worker {worker_id} claimed job {row.job_id}")
            # Convert row to JobQueue object
            job = await self.get_by_id(row.id)
            return job
        
        return None
    
    async def update_heartbeat(self, job_id: UUID) -> bool:
        """Update worker heartbeat for a job."""
        result = await self.session.execute(
            update(JobQueue)
            .where(JobQueue.job_id == job_id)
            .values(worker_heartbeat=datetime.utcnow())
        )
        return result.rowcount > 0
    
    async def update_progress(self, job_id: UUID, progress: int) -> bool:
        """Update job progress percentage."""
        result = await self.session.execute(
            update(JobQueue)
            .where(JobQueue.job_id == job_id)
            .values(progress_percent=min(100, max(0, progress)))
        )
        return result.rowcount > 0
    
    async def complete_job(
        self,
        job_id: UUID,
        result_path: str,
        processing_time: int
    ) -> bool:
        """Mark job as completed."""
        result = await self.session.execute(
            update(JobQueue)
            .where(JobQueue.job_id == job_id)
            .values(
                status=JobStatus.COMPLETED,
                result_path=result_path,
                processing_time_seconds=processing_time,
                completed_at=datetime.utcnow(),
                progress_percent=100
            )
        )
        return result.rowcount > 0
    
    async def fail_job(self, job_id: UUID, error: str) -> bool:
        """Mark job as failed."""
        result = await self.session.execute(
            update(JobQueue)
            .where(JobQueue.job_id == job_id)
            .values(
                status=JobStatus.FAILED,
                error_message=error,
                completed_at=datetime.utcnow()
            )
        )
        return result.rowcount > 0
    
    async def get_by_id(self, id: int) -> Optional[JobQueue]:
        """Get job by internal ID."""
        result = await self.session.execute(
            select(JobQueue).where(JobQueue.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_job_id(self, job_id: UUID) -> Optional[JobQueue]:
        """Get job by UUID."""
        result = await self.session.execute(
            select(JobQueue).where(JobQueue.job_id == job_id)
        )
        return result.scalar_one_or_none()
    
    async def get_pending_count(self) -> int:
        """Get count of pending jobs."""
        result = await self.session.execute(
            text("SELECT COUNT(*) FROM job_queue WHERE status = :status"),
            {"status": JobStatus.PENDING}
        )
        return result.scalar() or 0
    
    async def recover_stale_jobs(self, timeout_minutes: int = 15) -> int:
        """
        Recover jobs from workers that died (no heartbeat).
        
        Args:
            timeout_minutes: Consider job stale if no heartbeat in this time
            
        Returns:
            Number of jobs recovered
        """
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        
        result = await self.session.execute(
            update(JobQueue)
            .where(
                and_(
                    JobQueue.status == JobStatus.PROCESSING,
                    JobQueue.worker_heartbeat < cutoff
                )
            )
            .values(
                status=JobStatus.PENDING,
                worker_id=None,
                worker_heartbeat=None
            )
        )
        
        if result.rowcount > 0:
            logger.warning(f"Recovered {result.rowcount} stale jobs")
        
        return result.rowcount
    
    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[JobQueue]:
        """List jobs with optional filtering."""
        query = select(JobQueue).order_by(JobQueue.created_at.desc())
        
        if status:
            query = query.where(JobQueue.status == status)
        
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())
