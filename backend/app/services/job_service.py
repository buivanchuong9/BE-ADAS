"""
Job Service - Phase 2: Async Processing
========================================
Handles background video processing with asyncio and ThreadPoolExecutor.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.exceptions import JobNotFoundError
from ..db.repositories.video_job_repo import VideoJobRepository
from ..db.repositories.safety_event_repo import SafetyEventRepository
from ..db.models.video_job import JobStatus
from ..schemas.video import VideoJobResponse

logger = logging.getLogger(__name__)


class JobService:
    """
    Service for managing video processing jobs.
    
    Features:
    - Non-blocking job submission
    - Background processing with ThreadPoolExecutor
    - Progress tracking
    - Error handling and retry logic
    """
    
    def __init__(self):
        """Initialize job service"""
        self.executor = ThreadPoolExecutor(
            max_workers=settings.MAX_CONCURRENT_JOBS,
            thread_name_prefix="video_processor"
        )
        self.active_jobs: Dict[str, asyncio.Future] = {}
        
        logger.info(
            f"JobService initialized with {settings.MAX_CONCURRENT_JOBS} "
            f"concurrent workers"
        )
    
    async def submit_job(
        self,
        session: AsyncSession,
        job_id: str,
        input_path: str,
        output_path: str,
        video_type: str = "dashcam",
        device: str = "cpu"
    ) -> None:
        """
        Submit job for background processing.
        
        This is NON-BLOCKING - returns immediately.
        
        Args:
            session: Database session
            job_id: Job ID
            input_path: Path to input video
            output_path: Path for output video
            video_type: "dashcam" or "in_cabin"
            device: "cpu" or "cuda"
        """
        repo = VideoJobRepository(session)
        
        # Update status to PROCESSING
        await repo.update_status(job_id, JobStatus.PROCESSING)
        await session.commit()
        
        logger.info(f"Submitting job {job_id} for processing")
        
        # Create async task
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            self.executor,
            self._process_video_sync,
            job_id,
            input_path,
            output_path,
            video_type,
            device
        )
        
        # Store future
        self.active_jobs[job_id] = future
        
        # Add callback to clean up when done
        future.add_done_callback(lambda f: self._on_job_complete(job_id, f))
        
        logger.info(f"Job {job_id} submitted to executor")
    
    def _process_video_sync(
        self,
        job_id: str,
        input_path: str,
        output_path: str,
        video_type: str,
        device: str
    ) -> Dict[str, Any]:
        """
        Synchronous video processing (runs in thread pool).
        
        This method BLOCKS and performs CPU-intensive AI processing.
        """
        logger.info(f"[Job {job_id}] Starting video processing")
        start_time = datetime.now()
        
        try:
            # Import AI pipeline
            import sys
            from pathlib import Path as PathlibPath
            sys.path.insert(0, str(PathlibPath(__file__).parent.parent.parent))
            
            from perception.pipeline.video_pipeline_v11 import process_video
            
            # Process video
            result = process_video(
                input_path=input_path,
                output_path=output_path,
                video_type=video_type,
                device=device
            )
            
            processing_time = (datetime.now() - start_time).total_seconds()
            result['processing_time'] = processing_time
            result['job_id'] = job_id
            
            logger.info(
                f"[Job {job_id}] Processing complete in {processing_time:.2f}s. "
                f"Events: {len(result.get('events', []))}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[Job {job_id}] Processing failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'job_id': job_id
            }
    
    def _on_job_complete(self, job_id: str, future: asyncio.Future):
        """
        Callback when job completes.
        
        CRITICAL FIX: This runs in thread pool context, not event loop.
        Must use loop.create_task() instead of asyncio.create_task().
        """
        # Remove from active jobs
        if job_id in self.active_jobs:
            del self.active_jobs[job_id]
        
        try:
            result = future.result()
            
            # CRITICAL FIX: Get event loop and schedule task properly
            # asyncio.create_task() fails in thread pool callback
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self._update_job_result(job_id, result))
                logger.info(f"[Job {job_id}] Scheduled database update task")
            except Exception as task_error:
                logger.error(
                    f"[Job {job_id}] Failed to schedule update task: {task_error}",
                    exc_info=True
                )
            
        except Exception as e:
            logger.error(f"[Job {job_id}] Future exception: {e}", exc_info=True)
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self._update_job_error(job_id, str(e)))
            except Exception as task_error:
                logger.error(
                    f"[Job {job_id}] Failed to schedule error task: {task_error}",
                    exc_info=True
                )
    
    async def _update_job_result(self, job_id: str, result: Dict[str, Any]):
        """
        Update job with processing results.
        
        This runs in the async event loop.
        """
        from ..db.session import async_session_maker
        
        async with async_session_maker() as session:
            try:
                repo = VideoJobRepository(session)
                
                if result.get('success'):
                    # Success
                    await repo.update_status(job_id, JobStatus.COMPLETED)
                    
                    # Update additional fields that exist in the model
                    job = await repo.get_by_job_id(job_id)
                    if job:
                        update_data = {}
                        
                        if result.get('output_path'):
                            update_data['result_path'] = result.get('output_path')
                        
                        if result.get('processing_time'):
                            update_data['processing_time_seconds'] = int(result.get('processing_time'))
                        
                        if update_data:
                            await repo.update(job.id, **update_data)
                    
                    # Store events in database
                    await self._store_events(session, job_id, result.get('events', []))
                    
                    await session.commit()
                    logger.info(f"[Job {job_id}] Database updated with results")
                else:
                    # Failure
                    error_msg = result.get('error', 'Unknown error')
                    await repo.update_status(job_id, JobStatus.FAILED, error_msg)
                    await session.commit()
                    logger.error(f"[Job {job_id}] Marked as failed: {error_msg}")
                    
            except Exception as e:
                logger.error(f"[Job {job_id}] Failed to update database: {e}")
                await session.rollback()
    
    async def _update_job_error(self, job_id: str, error: str):
        """Update job as failed"""
        from ..db.session import async_session_maker
        
        async with async_session_maker() as session:
            try:
                repo = VideoJobRepository(session)
                await repo.update_status(job_id, JobStatus.FAILED, error)
                await session.commit()
                logger.error(f"[Job {job_id}] Marked as failed: {error}")
            except Exception as e:
                logger.error(f"[Job {job_id}] Failed to update error: {e}")
                await session.rollback()
    
    async def _store_events(
        self,
        session: AsyncSession,
        job_id: str,
        events: list
    ):
        """
        Store safety events from video processing.
        
        Args:
            session: Database session
            job_id: Job ID
            events: List of event dicts from AI pipeline
        """
        if not events:
            return
        
        job_repo = VideoJobRepository(session)
        event_repo = SafetyEventRepository(session)
        
        job = await job_repo.get_by_job_id(job_id)
        if not job:
            logger.warning(f"Job {job_id} not found, skipping event storage")
            return
        
        logger.info(f"[Job {job_id}] Storing {len(events)} events")
        
        for event_data in events:
            try:
                # Map event data to database schema
                from ..db.models.safety_event import EventType, EventSeverity
                
                event_type_map = {
                    'lane_departure': EventType.LANE_DEPARTURE,
                    'collision_warning': EventType.COLLISION_WARNING,
                    'forward_collision': EventType.FORWARD_COLLISION,
                    'fatigue': EventType.DRIVER_FATIGUE,
                    'distraction': EventType.DRIVER_DISTRACTION,
                }
                
                severity_map = {
                    'info': EventSeverity.INFO,
                    'warning': EventSeverity.WARNING,
                    'critical': EventSeverity.CRITICAL,
                }
                
                event_type_str = event_data.get('type', 'other')
                event_type = event_type_map.get(event_type_str, EventType.OTHER)
                
                severity_str = event_data.get('level', 'warning')
                severity = severity_map.get(severity_str, EventSeverity.WARNING)
                
                # Create timestamp from frame number
                timestamp = datetime.fromtimestamp(
                    event_data.get('time', 0)
                )
                
                await event_repo.create_event(
                    trip_id=job.trip_id,
                    video_job_id=job.id,
                    event_type=event_type,
                    severity=severity,
                    description=event_data.get('data', {}).get('message', 'Event detected'),
                    risk_score=event_data.get('data', {}).get('risk', 0.5),
                    timestamp=timestamp,
                    frame_number=event_data.get('frame'),
                    context_data=event_data.get('data')
                )
                
            except Exception as e:
                logger.error(f"Failed to store event: {e}")
                continue
        
        logger.info(f"[Job {job_id}] Stored events successfully")
    
    async def get_job_status(
        self,
        session: AsyncSession,
        job_id: str
    ) -> VideoJobResponse:
        """
        Get job status.
        
        Args:
            session: Database session
            job_id: Job ID
            
        Returns:
            Job response
            
        Raises:
            JobNotFoundError: If job not found
        """
        repo = VideoJobRepository(session)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise JobNotFoundError(job_id)
        
        return VideoJobResponse.model_validate(job)
    
    async def cancel_job(self, session: AsyncSession, job_id: str) -> bool:
        """
        Cancel a pending or processing job.
        
        Args:
            session: Database session
            job_id: Job ID
            
        Returns:
            True if cancelled, False otherwise
        """
        repo = VideoJobRepository(session)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            return False
        
        if job.status not in [JobStatus.PENDING, JobStatus.PROCESSING]:
            return False
        
        # Cancel future if exists
        if job_id in self.active_jobs:
            future = self.active_jobs[job_id]
            future.cancel()
            del self.active_jobs[job_id]
        
        # Update status
        await repo.update_status(job_id, JobStatus.CANCELLED)
        await session.commit()
        
        logger.info(f"Job {job_id} cancelled")
        return True
    
    def shutdown(self):
        """Shutdown executor gracefully"""
        logger.info("Shutting down JobService executor")
        self.executor.shutdown(wait=True)


# Global service instance
_job_service: Optional[JobService] = None


def get_job_service() -> JobService:
    """Get singleton job service instance"""
    global _job_service
    
    if _job_service is None:
        _job_service = JobService()
    
    return _job_service
