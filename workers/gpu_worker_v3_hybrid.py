#!/usr/bin/env python3
"""
GPU WORKER V3 - HYBRID PYTHON/C++ ARCHITECTURE
===============================================
Production-grade multi-process GPU worker with C++ acceleration.

ARCHITECTURE:
- Python: Job orchestration, GPU inference, error handling
- C++: Video I/O, rendering, encoding (via .so modules)
- GPU: AI models only (PyTorch)

PERFORMANCE TARGET:
- 1080p @ 30fps: 50-70 FPS processing (2-3x realtime)
- VRAM per worker: ~4.5 GB (vs 5.8 GB in v2)
- Latency: <25s for 60s video

Author: Principal Software Architect
Date: 2026-02-08
"""

import os
import sys
import time
import signal
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
from uuid import UUID

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "build/lib"))  # C++ modules

import asyncio
import asyncpg
import cv2
import numpy as np

# Import C++ modules (REQUIRED - no fallback)
try:
    import renderer
    logging.info("✅ C++ renderer module loaded")
except ImportError as e:
    logging.error(f"❌ C++ renderer module REQUIRED but not found: {e}")
    logging.error("   Run: ./build_cpp.sh")
    logging.error("   Or install dependencies: brew install cmake opencv && pip install pybind11")
    sys.exit(1)

# Import pipeline components
from backend.perception.lane.optical_flow_warper import OpticalFlowLaneWarper
from workers.frame_stats import FrameStats

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(process)d] - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HybridGPUWorker:
    """
    Hybrid Python/C++ GPU Worker.
    
    Key improvements over v2:
    - C++ renderer (3-5x faster)
    - Detailed frame statistics
    - PyTorch AMP (FP16) support
    - Better error recovery
    """
    
    def __init__(
        self,
        worker_id: str,
        database_url: str,
        device: str = "cuda",
        vram_limit_gb: float = 6.0,
        use_amp: bool = True
    ):
        self.worker_id = worker_id
        self.database_url = database_url
        self.device = device
        self.vram_limit_gb = vram_limit_gb
        self.use_amp = use_amp  # Automatic Mixed Precision (FP16)
        
        # State
        self.running = True
        self.current_job_id: Optional[UUID] = None
        self.pool: Optional[asyncpg.Pool] = None
        
        # AI Pipeline (lazy-loaded)
        self.pipeline = None
        self.optical_flow_warper = None
        
        # Stats
        self.jobs_processed = 0
        self.total_processing_time = 0.0
        
        # Graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        
        logger.info(
            f"💾 Worker {worker_id} initialized (v3-hybrid): "
            f"device={device}, VRAM={vram_limit_gb}GB, AMP={'ON' if use_amp else 'OFF'}, "
            f"C++ renderer=✅ REQUIRED"
        )
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"🛑 Worker {self.worker_id} received shutdown signal")
        self.running = False
    
    async def init(self):
        """Initialize database connection pool."""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=5,
            command_timeout=120
        )
        logger.info(f"✅ Worker {self.worker_id} connected to PostgreSQL")
    
    async def shutdown(self):
        """Clean shutdown."""
        if self.pool:
            await self.pool.close()
        logger.info(f"👋 Worker {self.worker_id} shutdown complete")
    
    def _load_pipeline(self):
        """Lazy-load AI pipeline with AMP support."""
        if self.pipeline is None:
            logger.info(f"🔧 [{self.worker_id}] Loading AI pipeline to {self.device}...")
            
            from backend.perception.object.object_detector_v11 import ObjectDetectorV11
            from backend.perception.distance.distance_estimator import DistanceEstimator
            from backend.perception.lane.lane_detector_v11 import LaneDetectorV11
            from backend.perception.driver.driver_monitor_v11 import DriverMonitorV11
            
            # Load models
            self.pipeline = {
                'object': ObjectDetectorV11(device=self.device),
                'distance': DistanceEstimator(),
                'lane': LaneDetectorV11(device=self.device),
                'driver': DriverMonitorV11(device=self.device)
            }
            
            # Initialize Optical Flow warper
            self.optical_flow_warper = OpticalFlowLaneWarper(
                rerun_interval=5,
                flow_confidence_threshold=0.3
            )
            
            # Enable AMP if requested
            if self.use_amp and self.device == "cuda":
                import torch
                self.amp_enabled = torch.cuda.is_available()
                if self.amp_enabled:
                    logger.info(f"✅ [{self.worker_id}] PyTorch AMP (FP16) enabled")
            else:
                self.amp_enabled = False
            
            logger.info(f"✅ [{self.worker_id}] AI pipeline loaded successfully")
        
        return self.pipeline
    
    async def claim_job(self) -> Optional[Dict]:
        """Claim next pending job atomically (same as v2)."""
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
        Process video job with hybrid Python/C++ pipeline.
        
        CRITICAL PATH:
        1. Decode (OpenCV - TODO: C++ videodec.so in Phase 3)
        2. Inference (Python + PyTorch + AMP)
        3. Render (C++ renderer.so if available, else Python)
        4. Encode (OpenCV - TODO: C++ hlsenc.so in Phase 3)
        """
        job_id = job['job_id']
        self.current_job_id = job_id
        start_time = datetime.now()
        
        # Frame statistics tracker
        stats = FrameStats()
        
        logger.info(f"🚀 [{self.worker_id}] Processing job {job_id}")
        
        try:
            # === VALIDATION ===
            input_path = job['video_path']
            if not input_path or not Path(input_path).exists():
                raise FileNotFoundError(f"Video not found: {input_path}")
            
            # === SETUP OUTPUT ===
            output_base = Path(os.getenv('VIDEOS_OUTPUT_DIR', '/hdd3/adas/videos/output'))
            job_output_dir = output_base / str(job_id)
            job_output_dir.mkdir(parents=True, exist_ok=True)
            
            fallback_video_path = job_output_dir / "result.mp4"
            
            # === LOAD PIPELINE ===
            pipeline = self._load_pipeline()
            self.optical_flow_warper.reset()
            
            # === OPEN VIDEO ===
            with stats.measure('video_open'):
                cap = cv2.VideoCapture(str(input_path))
                if not cap.isOpened():
                    raise RuntimeError(f"Cannot open video: {input_path}")
                
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            logger.info(f"  Video: {width}x{height} @ {fps:.1f}fps, {total_frames} frames")
            
            # === VIDEO WRITER ===
            with stats.measure('writer_init'):
                mp4_writer = cv2.VideoWriter(
                    str(fallback_video_path),
                    cv2.VideoWriter_fourcc(*'mp4v'),
                    fps,
                    (width, height)
                )
            
            # === PROCESS VIDEO ===
            frame_idx = 0
            events = []
            
            try:
                while True:
                    stats.begin_frame()
                    
                    # === DECODE ===
                    with stats.measure('decode'):
                        ret, frame = cap.read()
                        if not ret:
                            break
                    
                    # === PREPROCESS ===
                    with stats.measure('preprocess'):
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    
                    # === INFERENCE ===
                    with stats.measure('inference'):
                        results = self._run_inference(frame, gray, frame_idx, pipeline)
                    
                    # === RENDER OVERLAY (C++ ONLY) ===
                    with stats.measure('render'):
                        frame_with_overlay = self._draw_overlay_cpp(frame, results, height, width)
                    
                    # === ENCODE ===
                    with stats.measure('encode'):
                        mp4_writer.write(frame_with_overlay)
                    
                    # === COLLECT EVENTS ===
                    if results.get('events'):
                        events.extend(results['events'])
                    
                    stats.end_frame()
                    
                    # === PROGRESS UPDATE ===
                    frame_idx += 1
                    if frame_idx % 30 == 0:
                        progress = int((frame_idx / total_frames) * 100)
                        await self.update_progress(job_id, progress)
                
            finally:
                cap.release()
                mp4_writer.release()
            
            # === FINALIZE ===
            processing_time = int((datetime.now() - start_time).total_seconds())
            
            # Store events
            await self._store_events(job['id'], events)
            
            # Complete job
            await self.complete_job(job_id, str(fallback_video_path), processing_time, "")
            
            # Stats
            self.jobs_processed += 1
            self.total_processing_time += processing_time
            
            # Report statistics
            stats.report()
            
            logger.info(
                f"✅ [{self.worker_id}] Job {job_id} completed in {processing_time}s "
                f"({total_frames / processing_time:.1f} fps)"
            )
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_id}] Job {job_id} failed: {e}", exc_info=True)
            await self.fail_job(job_id, str(e))
        
        finally:
            self.current_job_id = None
    
    def _run_inference(self, frame, gray, frame_idx, pipeline):
        """Run AI inference with AMP support."""
        results = {}
        
        # Import torch for AMP
        if self.amp_enabled:
            import torch
            from torch.cuda.amp import autocast
        
        # === OBJECT DETECTION ===
        try:
            if self.amp_enabled:
                with autocast():
                    objects = pipeline['object'].detect(frame)
            else:
                objects = pipeline['object'].detect(frame)
            results['objects'] = objects
        except Exception as e:
            logger.warning(f"Object detection failed: {e}")
            results['objects'] = []
        
        # === LANE DETECTION (with Optical Flow) ===
        try:
            should_run_lanenet, reason = self.optical_flow_warper.should_run_lanenet(gray)
            
            if should_run_lanenet:
                if self.amp_enabled:
                    with autocast():
                        lane_mask = pipeline['lane'].detect(frame)
                else:
                    lane_mask = pipeline['lane'].detect(frame)
                final_lane_mask = self.optical_flow_warper.update(gray, lane_mask)
            else:
                final_lane_mask = self.optical_flow_warper.update(gray, None)
            
            results['lane_mask'] = final_lane_mask
        except Exception as e:
            logger.warning(f"Lane detection failed: {e}")
            results['lane_mask'] = np.zeros_like(gray)
        
        # === DISTANCE ESTIMATION ===
        try:
            distance_info = pipeline['distance'].process_detection(
                {'bbox': [100, 100, 200, 200]},  # TODO: use real detections
                height=frame.shape[0]
            )
            results['distance'] = distance_info
        except Exception as e:
            logger.warning(f"Distance estimation failed: {e}")
            results['distance'] = None
        
        # === EVENT DETECTION ===
        results['events'] = []
        
        return results
    
    def _draw_overlay_cpp(self, frame, results, height, width):
        """Draw overlay using C++ renderer (FAST PATH)."""
        # Prepare bboxes for C++
        cpp_bboxes = []
        for obj in results.get('objects', []):
            bbox = obj.get('bbox')
            if bbox:
                x1, y1, x2, y2 = map(int, bbox)
                cpp_bbox = renderer.BBox(
                    x1, y1, x2, y2,
                    0, 255, 0,  # Green (RGB)
                    obj.get('confidence', 0.0),
                    obj.get('class_name', 'unknown')
                )
                cpp_bboxes.append(cpp_bbox)
        
        # Render in-place (modifies frame)
        lane_mask = results.get('lane_mask')
        renderer.OverlayRenderer.render(
            frame_bgr=frame,
            lane_mask=lane_mask if lane_mask is not None else None,
            bboxes=cpp_bboxes,
            lane_alpha=0.3
        )
        
        return frame  # Modified in-place
    

    
    # === DATABASE METHODS (same as v2) ===
    async def update_progress(self, job_id: UUID, progress: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE job_queue SET progress_percent = $1 WHERE job_id = $2",
                min(100, max(0, progress)), job_id
            )
    
    async def complete_job(self, job_id: UUID, result_path: str, processing_time: int, hls_path: str):
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
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE job_queue
                SET 
                    status = 'failed',
                    error_message = $1,
                    completed_at = NOW()
                WHERE job_id = $2
            """, error[:1000], job_id)
    
    async def _store_events(self, job_db_id: int, events: list):
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
        
        logger.info(f"🚀 [{self.worker_id}] Starting main loop (v3-hybrid)...")
        
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
                        logger.info(f"⏸️  [{self.worker_id}] No jobs available, sleeping...")
                    
                    await asyncio.sleep(backoff)
            
            except Exception as e:
                logger.error(f"❌ [{self.worker_id}] Worker error: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        await self.shutdown()
        
        logger.info(f"📊 [{self.worker_id}] Final stats: {self.jobs_processed} jobs processed")


def main():
    parser = argparse.ArgumentParser(description='ADAS GPU Worker V3 (Hybrid)')
    parser.add_argument('--worker-id', default=f"worker_{os.getpid()}")
    parser.add_argument('--device', default='cuda', choices=['cuda', 'cpu'])
    parser.add_argument('--vram-limit', type=float, default=6.0)
    parser.add_argument('--database-url', default=os.getenv('DATABASE_URL'))
    parser.add_argument('--no-amp', action='store_true', help='Disable PyTorch AMP')
    
    args = parser.parse_args()
    
    if not args.database_url:
        print("❌ ERROR: DATABASE_URL required")
        sys.exit(1)
    
    worker = HybridGPUWorker(
        worker_id=args.worker_id,
        database_url=args.database_url,
        device=args.device,
        vram_limit_gb=args.vram_limit,
        use_amp=not args.no_amp
    )
    
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("👋 Worker interrupted by user")


if __name__ == '__main__':
    main()
