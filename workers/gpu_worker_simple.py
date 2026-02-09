#!/usr/bin/env python3
"""
GPU WORKER - SIMPLE & STABLE (Python Only)
===========================================
Production-ready GPU worker with ZERO zombie processes.

ARCHITECTURE:
- Python ONLY (no C++, no pybind11)
- 1 worker = 1 GPU = 1 process
- Sequential job processing (no multiprocessing)
- FFmpeg NVENC for encoding (safe cleanup)
- OpenCV for overlay (CPU is acceptable for demo)

PERFORMANCE TARGET:
- 1080p @ 30fps: 40-60 FPS processing (1.5-2x realtime)
- VRAM per worker: ~4-5 GB
- Latency: <30s for 60s video

STABILITY:
- ✅ No zombie FFmpeg processes
- ✅ Guaranteed cleanup on exception
- ✅ Web-compatible video output
- ✅ Detailed logging for debugging

Author: Senior Backend + AI Engineer
Date: 2026-02-09
"""

import os
import sys
import time
import signal
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from uuid import UUID

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import dependencies
import asyncio
import asyncpg
import cv2
import numpy as np
from dotenv import load_dotenv

# Load .env explicitly
load_dotenv(PROJECT_ROOT / ".env")

# Import FFmpeg utilities (SAFE)
from backend.core.ffmpeg_utils import FFmpegEncoder, get_video_info

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(process)d] - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('api.log')  # Log to file for tail -f
    ]
)
logger = logging.getLogger(__name__)


class SimpleGPUWorker:
    """
    Simple, stable GPU worker with guaranteed cleanup.
    
    Key features:
    - Python only (no C++ dependencies)
    - Safe FFmpeg subprocess management
    - Web-compatible video encoding
    - PostgreSQL job queue
    """
    
    def __init__(
        self,
        worker_id: str,
        database_url: str,
        device: str = "cuda",
    ):
        self.worker_id = worker_id
        self.database_url = database_url
        self.device = device
        
        # State
        self.running = True
        self.current_job_id: Optional[UUID] = None
        self.pool: Optional[asyncpg.Pool] = None
        
        # AI Pipeline (lazy-loaded)
        self.pipeline = None
        
        # Stats
        self.jobs_processed = 0
        self.total_processing_time = 0.0
        
        # Graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        
        logger.info(
            f"[WORKER] {worker_id} initialized: device={device}, Python-only mode"
        )
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"[WORKER] {self.worker_id} received shutdown signal")
        self.running = False
    
    async def init(self):
        """Initialize database connection pool."""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=5,
            command_timeout=120
        )
        logger.info(f"[WORKER] {self.worker_id} connected to PostgreSQL")
    
    async def shutdown(self):
        """Clean shutdown."""
        if self.pool:
            await self.pool.close()
        logger.info(f"[WORKER] {self.worker_id} shutdown complete")
    
    def _load_pipeline(self):
        """Lazy-load AI pipeline."""
        if self.pipeline is None:
            logger.info(f"[GPU] Loading AI models to {self.device}...")
            
            from backend.perception.object.object_detector_v11 import ObjectDetectorV11
            from backend.perception.distance.distance_estimator import DistanceEstimator
            from backend.perception.lane.lane_detector_v11 import LaneDetectorV11
            
            # Load models
            self.pipeline = {
                'object': ObjectDetectorV11(device=self.device),
                'distance': DistanceEstimator(),
                'lane': LaneDetectorV11(device=self.device),
            }
            
            logger.info(f"[GPU] ✓ AI pipeline loaded successfully")
        
        return self.pipeline
    
    async def claim_job(self) -> Optional[Dict]:
        """Claim next pending job atomically."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    UPDATE job_queue
                    SET 
                        status = 'processing',
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
                    RETURNING 
                        id, job_id, video_path, video_filename, 
                        video_type, device
                """, self.worker_id)
                
                if row:
                    return {
                        'id': row['id'],
                        'job_id': row['job_id'],
                        'video_path': row['video_path'],
                        'video_filename': row['video_filename'],
                        'video_type': row['video_type'],
                        'device': row['device']
                    }
        
        return None
    
    async def process_job(self, job: Dict):
        """
        Process video job with GUARANTEED cleanup.
        
        PIPELINE:
        1. Decode: cv2.VideoCapture (simple, stable)
        2. Inference: PyTorch GPU (YOLO + Lane)
        3. Overlay: OpenCV Python (CPU is OK for demo)
        4. Encode: FFmpeg NVENC (with safe cleanup)
        """
        job_id = job['job_id']
        self.current_job_id = job_id
        start_time = time.time()
        
        logger.info(f"[JOB] {job_id} - Start processing")
        
        try:
            # === VALIDATION ===
            input_path = job['video_path']
            if not input_path or not Path(input_path).exists():
                raise FileNotFoundError(f"Video not found: {input_path}")
            
            logger.info(f"[INPUT] {Path(input_path).name}")
            
            # === SETUP OUTPUT ===
            output_base = Path(os.getenv('VIDEOS_OUTPUT_DIR', './storage/result'))
            job_output_dir = output_base / str(job_id)
            job_output_dir.mkdir(parents=True, exist_ok=True)
            
            result_video_path = job_output_dir / "result.mp4"
            
            # === LOAD PIPELINE ===
            pipeline = self._load_pipeline()
            
            # === OPEN VIDEO ===
            logger.info(f"[DECODE] Opening video...")
            cap = cv2.VideoCapture(str(input_path))
            if not cap.isOpened():
                raise RuntimeError(f"Cannot open video: {input_path}")
            
            # Get video properties (DATA TYPE SAFE)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            logger.info(f"[VIDEO] {width}x{height} @ {fps:.1f}fps, {total_frames} frames")
            
            # === PROCESS VIDEO WITH SAFE ENCODER ===
            frame_idx = 0
            events = []
            
            # Use context manager - GUARANTEED cleanup!
            with FFmpegEncoder(
                output_path=str(result_video_path),
                width=width,
                height=height,
                fps=fps,
                use_nvenc=True,  # GPU encoding
                preset='fast'
            ) as encoder:
                
                logger.info(f"[ENCODE] FFmpeg encoder started")
                
                while True:
                    # === DECODE FRAME ===
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # === INFERENCE ===
                    results = self._run_inference(frame, frame_idx, pipeline)
                    
                    # === DRAW OVERLAY (Python/OpenCV) ===
                    frame_with_overlay = self._draw_overlay(frame, results)
                    
                    # === ENCODE FRAME ===
                    encoder.write(frame_with_overlay)
                    
                    # === COLLECT EVENTS ===
                    if results.get('events'):
                        events.extend(results['events'])
                    
                    # === PROGRESS UPDATE ===
                    frame_idx += 1
                    if frame_idx % 30 == 0:
                        progress = int((frame_idx / total_frames) * 100)
                        await self.update_progress(job_id, progress)
                        logger.info(f"[PROGRESS] {progress}% ({frame_idx}/{total_frames})")
                
                # Encoder automatically closes here (context manager)
            
            # Release video capture
            cap.release()
            
            # === FINALIZE ===
            processing_time = int(time.time() - start_time)
            processing_fps = total_frames / processing_time if processing_time > 0 else 0
            
            logger.info(
                f"[DONE] Job {job_id} completed in {processing_time}s "
                f"({processing_fps:.1f} fps)"
            )
            
            # Store events
            await self._store_events(job['id'], events)
            
            # Complete job
            await self.complete_job(job_id, str(result_video_path), processing_time)
            
            # Stats
            self.jobs_processed += 1
            self.total_processing_time += processing_time
            
        except Exception as e:
            logger.error(f"[ERROR] Job {job_id} failed: {e}", exc_info=True)
            await self.fail_job(job_id, str(e))
        
        finally:
            self.current_job_id = None
            # FFmpeg cleanup is guaranteed by context manager
    
    def _run_inference(self, frame, frame_idx, pipeline) -> Dict:
        """Run AI inference (YOLO + Lane)."""
        results = {}
        
        # === OBJECT DETECTION ===
        try:
            objects = pipeline['object'].detect(frame)
            results['objects'] = objects
        except Exception as e:
            logger.warning(f"Object detection failed: {e}")
            results['objects'] = []
        
        # === LANE DETECTION ===
        try:
            lane_mask = pipeline['lane'].detect(frame)
            results['lane_mask'] = lane_mask
        except Exception as e:
            logger.warning(f"Lane detection failed: {e}")
            results['lane_mask'] = None
        
        # === DISTANCE ESTIMATION ===
        try:
            if results['objects']:
                # Use first object for distance
                obj = results['objects'][0]
                distance_info = pipeline['distance'].process_detection(
                    obj,
                    height=frame.shape[0]
                )
                results['distance'] = distance_info
        except Exception as e:
            logger.warning(f"Distance estimation failed: {e}")
            results['distance'] = None
        
        # === EVENT DETECTION ===
        results['events'] = []
        
        return results
    
    def _draw_overlay(self, frame, results) -> np.ndarray:
        """
        Draw overlay using OpenCV (Python).
        
        Note: This is CPU-based, which is acceptable for demo.
              For production, consider optimizing critical paths only.
        """
        overlay = frame.copy()
        
        # === DRAW LANE MASK ===
        lane_mask = results.get('lane_mask')
        if lane_mask is not None:
            # Convert mask to color (green)
            lane_color = np.zeros_like(frame)
            lane_color[lane_mask > 0] = [0, 255, 0]  # Green BGR
            
            # Blend with original frame
            overlay = cv2.addWeighted(overlay, 0.7, lane_color, 0.3, 0)
        
        # === DRAW BOUNDING BOXES ===
        for obj in results.get('objects', []):
            bbox = obj.get('bbox')
            if bbox:
                x1, y1, x2, y2 = map(int, bbox)
                
                # Draw box
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Draw label
                label = f"{obj.get('class_name', 'object')} {obj.get('confidence', 0):.2f}"
                cv2.putText(
                    overlay, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2
                )
        
        # === DRAW DISTANCE ===
        distance_info = results.get('distance')
        if distance_info:
            text = f"Distance: {distance_info.get('distance_m', 0):.1f}m"
            cv2.putText(
                overlay, text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2
            )
        
        return overlay
    
    # === DATABASE METHODS ===
    
    async def update_progress(self, job_id: UUID, progress: int):
        """Update job progress."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE job_queue SET progress_percent = $1 WHERE job_id = $2",
                min(100, max(0, progress)), job_id
            )
    
    async def complete_job(self, job_id: UUID, result_path: str, processing_time: int):
        """Mark job as completed."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE job_queue
                SET 
                    status = 'completed',
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
                SET 
                    status = 'failed',
                    error_message = $1,
                    completed_at = NOW()
                WHERE job_id = $2
            """, error[:1000], job_id)
    
    async def _store_events(self, job_db_id: int, events: List[Dict]):
        """Store safety events to database."""
        if not events:
            return
        
        async with self.pool.acquire() as conn:
            for event in events:
                try:
                    await conn.execute("""
                        INSERT INTO safety_events
                        (job_id, event_type, severity, timestamp_sec, 
                         frame_number, description, meta_data)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                        job_db_id,
                        event.get('type', 'other'),
                        event.get('level', 'warning'),
                        event.get('time', 0),
                        event.get('frame'),
                        event.get('data', {}).get('message', ''),
                        '{}'
                    )
                except Exception as e:
                    logger.warning(f"Failed to store event: {e}")
    
    async def run(self):
        """Main worker loop."""
        await self.init()
        
        logger.info(f"[WORKER] {self.worker_id} starting main loop (Python-only mode)...")
        
        idle_count = 0
        while self.running:
            try:
                job = await self.claim_job()
                
                if job:
                    idle_count = 0
                    await self.process_job(job)
                else:
                    idle_count += 1
                    backoff = min(10, 2 + idle_count * 0.5)
                    
                    if idle_count == 1:
                        logger.info(f"[QUEUE] No jobs available, sleeping...")
                    
                    await asyncio.sleep(backoff)
            
            except Exception as e:
                logger.error(f"[ERROR] Worker error: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        await self.shutdown()
        
        logger.info(f"[STATS] {self.jobs_processed} jobs processed, avg time: {self.total_processing_time / max(1, self.jobs_processed):.1f}s")


def main():
    """Main entry point."""
    # Load .env
    env_path = PROJECT_ROOT / ".env"
    logger.info(f"Loading .env from: {env_path}")
    
    if env_path.exists():
        load_dotenv(env_path, override=True)
        logger.info("✓ .env file loaded")
    else:
        logger.warning("✗ .env file NOT found")
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='Simple GPU Worker (Python Only)')
    parser.add_argument('--worker-id', default=f"worker_{os.getpid()}")
    parser.add_argument('--device', default='cuda', choices=['cuda', 'cpu'])
    parser.add_argument('--database-url', default=os.getenv('DATABASE_URL'))
    
    args = parser.parse_args()
    
    if not args.database_url:
        logger.error("ERROR: DATABASE_URL required. Check your .env file.")
        sys.exit(1)
    
    # Create worker
    worker = SimpleGPUWorker(
        worker_id=args.worker_id,
        database_url=args.database_url,
        device=args.device,
    )
    
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")


if __name__ == '__main__':
    main()
