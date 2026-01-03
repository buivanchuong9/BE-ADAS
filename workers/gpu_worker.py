#!/usr/bin/env python3
"""
GPU Worker - v3.0
==================
Supervisor-managed worker that polls PostgreSQL job queue.

Usage:
    supervisorctl start adas-worker:*
    
Or manually:
    python gpu_worker.py --worker-id worker_01
"""

import os
import sys
import time
import signal
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import asyncpg
from uuid import UUID

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GPUWorker:
    """
    GPU worker that processes video jobs from PostgreSQL queue.
    
    Features:
    - Atomic job claiming with SELECT FOR UPDATE SKIP LOCKED
    - Heartbeat monitoring
    - Graceful shutdown
    - Model persistence (keeps AI models loaded)
    """
    
    def __init__(
        self,
        worker_id: str,
        database_url: str,
        device: str = "cuda"
    ):
        self.worker_id = worker_id
        self.database_url = database_url
        self.device = device
        self.running = True
        self.current_job: Optional[UUID] = None
        self.pool: Optional[asyncpg.Pool] = None
        self.pipeline = None  # Lazy-loaded AI pipeline
        
        # Graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Worker {self.worker_id} received shutdown signal")
        self.running = False
    
    async def init(self):
        """Initialize database connection pool."""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=5,
            command_timeout=60
        )
        logger.info(f"Worker {self.worker_id} connected to database")
    
    async def shutdown(self):
        """Clean shutdown."""
        if self.pool:
            await self.pool.close()
        logger.info(f"Worker {self.worker_id} shutdown complete")
    
    def _load_pipeline(self):
        """Lazy-load AI pipeline (keeps models in memory)."""
        if self.pipeline is None:
            logger.info("Loading AI pipeline...")
            from backend.perception.pipeline.video_pipeline_v11 import VideoPipelineV11
            self.pipeline = VideoPipelineV11(device=self.device)
            logger.info("AI pipeline loaded")
        return self.pipeline
    
    async def claim_job(self) -> Optional[dict]:
        """
        Atomically claim the next pending job.
        
        Uses FOR UPDATE SKIP LOCKED to prevent race conditions.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    UPDATE job_queue 
                    SET status = 'processing',
                        worker_id = $1,
                        worker_heartbeat = NOW(),
                        started_at = NOW(),
                        attempts = attempts + 1
                    WHERE id = (
                        SELECT id FROM job_queue
                        WHERE status = 'pending'
                          AND attempts < max_attempts
                        ORDER BY priority DESC, created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING id, job_id, video_path, video_filename, video_type, device
                """, self.worker_id)
                
                if row:
                    return {
                        'id': row['id'],
                        'job_id': row['job_id'],
                        'video_type': row['video_type'],
                        'device': row['device'],
                        'input_path': row['video_path'],
                        'filename': row['video_filename']
                    }
        
        return None
    
    async def send_heartbeat(self, job_id: UUID):
        """Update heartbeat to indicate worker is alive."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE job_queue SET worker_heartbeat = NOW() WHERE job_id = $1",
                job_id
            )
    
    async def update_progress(self, job_id: UUID, progress: int):
        """Update job progress percentage."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE job_queue SET progress_percent = $1 WHERE job_id = $2",
                min(100, max(0, progress)),
                job_id
            )
    
    async def complete_job(self, job_id: UUID, result_path: str, processing_time: int):
        """Mark job as completed."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE job_queue 
                SET status = 'completed',
                    result_path = $1,
                    processing_time_seconds = $2,
                    completed_at = NOW(),
                    progress_percent = 100
                WHERE job_id = $3
            """, result_path, processing_time, job_id)
    
    async def fail_job(self, job_id: UUID, error: str):
        """Mark job as failed."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE job_queue 
                SET status = 'failed',
                    error_message = $1,
                    completed_at = NOW()
                WHERE job_id = $2
            """, error[:1000], job_id)  # Truncate error message
    
    async def process_job(self, job: dict):
        """
        Process a single video job.
        
        Runs AI pipeline and stores results.
        """
        job_id = job['job_id']
        self.current_job = job_id
        start_time = datetime.now()
        
        logger.info(f"[{self.worker_id}] Processing job {job_id}")
        
        try:
            # Validate input
            input_path = job['input_path']
            if not input_path or not Path(input_path).exists():
                raise FileNotFoundError(f"Video not found: {input_path}")
            
            # Generate output path
            output_dir = Path(os.getenv('VIDEOS_OUTPUT_DIR', '/hdd3/adas/videos/output'))
            output_dir = output_dir / str(job_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / "result.mp4")
            
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_id))
            
            try:
                # Run AI pipeline (blocking)
                pipeline = self._load_pipeline()
                
                # Progress callback
                async def progress_callback(frame_idx, total_frames, events):
                    progress = int((frame_idx / total_frames) * 100)
                    await self.update_progress(job_id, progress)
                
                # Process video
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    pipeline.process_video,
                    input_path,
                    output_path
                )
                
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            
            # Calculate processing time
            processing_time = int((datetime.now() - start_time).total_seconds())
            
            # Store events
            await self._store_events(job['id'], result.get('events', []))
            
            # Mark as completed
            await self.complete_job(job_id, output_path, processing_time)
            
            logger.info(
                f"[{self.worker_id}] Completed job {job_id} in {processing_time}s, "
                f"events: {len(result.get('events', []))}"
            )
            
        except Exception as e:
            logger.error(f"[{self.worker_id}] Job {job_id} failed: {e}", exc_info=True)
            await self.fail_job(job_id, str(e))
        
        finally:
            self.current_job = None
    
    async def _heartbeat_loop(self, job_id: UUID):
        """Send heartbeats every 30 seconds."""
        while True:
            await asyncio.sleep(30)
            await self.send_heartbeat(job_id)
            logger.debug(f"Heartbeat sent for job {job_id}")
    
    async def _store_events(self, job_id: int, events: list):
        """Store detected safety events."""
        if not events:
            return
        
        async with self.pool.acquire() as conn:
            for event in events:
                await conn.execute("""
                    INSERT INTO safety_events 
                    (job_id, event_type, severity, timestamp_sec, frame_number, description, meta_data)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                    job_id,
                    event.get('type', 'other'),
                    event.get('level', 'warning'),
                    event.get('time', 0),
                    event.get('frame'),
                    event.get('data', {}).get('message', ''),
                    str(event.get('data', {}))
                )
    
    async def run(self):
        """Main worker loop."""
        await self.init()
        logger.info(f"Worker {self.worker_id} starting main loop")
        
        idle_count = 0
        
        while self.running:
            try:
                # Claim next job
                job = await self.claim_job()
                
                if job:
                    idle_count = 0
                    await self.process_job(job)
                else:
                    # No jobs available - backoff
                    idle_count += 1
                    backoff = min(10, 2 + idle_count * 0.5)  # 2-10 seconds
                    await asyncio.sleep(backoff)
                
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        await self.shutdown()


def main():
    parser = argparse.ArgumentParser(description='ADAS GPU Worker')
    parser.add_argument('--worker-id', default=f"worker_{os.getpid()}")
    parser.add_argument('--device', default='cuda', choices=['cuda', 'cpu'])
    parser.add_argument('--database-url', default=os.getenv('DATABASE_URL'))
    args = parser.parse_args()
    
    if not args.database_url:
        print("ERROR: DATABASE_URL environment variable required")
        sys.exit(1)
    
    worker = GPUWorker(
        worker_id=args.worker_id,
        database_url=args.database_url,
        device=args.device
    )
    
    asyncio.run(worker.run())


if __name__ == '__main__':
    main()
