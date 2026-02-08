#!/usr/bin/env python3
"""
GPU WORKER V2 - PRODUCTION GRADE
=================================
Multi-process GPU worker với HLS streaming và Optical Flow optimization.

ARCHITECTURE DECISIONS (Explained như Senior Engineer):
----------------------------------------
❌ KHÔNG dùng Celery/Redis vì:
   - Overhead không cần thiết cho usecase này
   - Redis persistence không quan trọng (PostgreSQL đã đủ)
   - Celery adds complexity mà không mang lại lợi ích đáng kể

✅ PostgreSQL Job Queue với SELECT FOR UPDATE SKIP LOCKED vì:
   - Atomic job claiming (không có race condition)
   - Transactional guarantee
   - Dễ debug (view jobs trong pgAdmin)
   - Không cần thêm infrastructure

✅ Multi-Process (không phải Multi-Thread) vì:
   - Mỗi process = 1 GPU worker với models riêng
   - Số workers = floor(GPU_VRAM / VRAM_PER_WORKER)
   - VD: 24GB GPU, 6GB/worker → 3-4 workers an toàn
   - Tránh GIL lock của Python

✅ HLS Progressive Streaming vì:
   - User xem được video ngay ~4s sau khi bắt đầu xử lý
   - Không cần đợi toàn bộ video hoàn thành
   - Professional UX (giống YouTube)

✅ Optical Flow Lane Warping vì:
   - LaneNet là bottleneck lớn nhất (~80ms/frame)
   - Optical Flow chỉ ~5-10ms/frame
   - Tiết kiệm 70-80% computational cost
   - Realtime performance: 60s video → 30-40s processing

PERFORMANCE TARGET:
------------------
- 1080p @ 30fps video
- 4 AI models: YOLO + LaneNet + Depth + Driver Monitor
- Target: 1.2-1.5x realtime (60s video → 40-50s processing)
- First segment ready: <5s
- Concurrent jobs: 3-4 per 24GB GPU

Author: Principal AI Architect  
Date: 2026-02-08
"""

import os
import sys
import time
import signal
import logging
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
from uuid import UUID

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import asyncpg
import cv2
import numpy as np

# Import pipeline components
from backend.perception.pipeline.hls_writer import HLSWriter
from backend.perception.lane.optical_flow_warper import OpticalFlowLaneWarper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(process)d] - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GPUWorkerV2:
    """
    Production GPU Worker với:
    - HLS progressive streaming
    - Optical Flow lane optimization  
    - Multi-process safe
    - Graceful shutdown
    - Comprehensive error handling
    """
    
    def __init__(
        self,
        worker_id: str,
        database_url: str,
        device: str = "cuda",
        vram_limit_gb: float = 6.0
    ):
        """
        Initialize GPU Worker.
        
        Args:
            worker_id: Unique worker ID (e.g., "worker_0", "worker_1")
            database_url: PostgreSQL connection string
            device: "cuda" or "cpu"
            vram_limit_gb: Max VRAM usage for this worker (for monitoring)
        """
        self.worker_id = worker_id
        self.database_url = database_url
        self.device = device
        self.vram_limit_gb = vram_limit_gb
        
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
        
        # Graceful shutdown handlers
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        
        logger.info(
            f"💾 Worker {worker_id} initialized: device={device}, "
            f"VRAM limit={vram_limit_gb}GB"
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
            command_timeout=120  # 2 minutes for long queries
        )
        logger.info(f"✅ Worker {self.worker_id} connected to PostgreSQL")
    
    async def shutdown(self):
        """Clean shutdown."""
        if self.pool:
            await self.pool.close()
        logger.info(f"👋 Worker {self.worker_id} shutdown complete")
    
    def _load_pipeline(self):
        """
        Lazy-load AI pipeline (CRITICAL: keeps models in GPU memory).
        
        WHY lazy loading:
        - Models được load 1 lần duy nhất khi worker khởi động
        - Kept in GPU memory suốt lifetime của worker
        - Không load/unload models giữa các jobs → tránh overhead
        """
        if self.pipeline is None:
            logger.info(f"🔧 [{self.worker_id}] Loading AI pipeline to {self.device}...")
            
            # Import here để tránh load khi không cần
            from backend.perception.object.object_detector_v11 import ObjectDetectorV11
            from backend.perception.distance.distance_estimator_v11 import DistanceEstimatorV11
            from backend.perception.lane.lane_detector_v11 import LaneDetectorV11
            from backend.perception.driver.driver_monitor_v11 import DriverMonitorV11
            
            # Load models
            self.pipeline = {
                'object': ObjectDetectorV11(device=self.device),
                'distance': DistanceEstimatorV11(device=self.device),
                'lane': LaneDetectorV11(device=self.device),
                'driver': DriverMonitorV11(device=self.device)
            }
            
            # Initialize Optical Flow warper
            self.optical_flow_warper = OpticalFlowLaneWarper(
                rerun_interval=5,  # Run LaneNet mỗi 5 frames
                flow_confidence_threshold=0.3
            )
            
            logger.info(f"✅ [{self.worker_id}] AI pipeline loaded successfully")
        
        return self.pipeline
    
    async def claim_job(self) -> Optional[Dict]:
        """
        Claim next pending job atomically.
        
        Uses PostgreSQL row-level locking with SKIP LOCKED.
        This is PRODUCTION-SAFE and prevents race conditions.
        """
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
    
    async def heartbeat(self, job_id: UUID):
        """Update heartbeat to prove worker is alive."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE job_queue SET worker_heartbeat = NOW() WHERE job_id = $1",
                job_id
            )
    
    async def update_progress(self, job_id: UUID, progress: int):
        """Update job progress (0-100)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE job_queue SET progress_percent = $1 WHERE job_id = $2",
                min(100, max(0, progress)),
                job_id
            )
    
    async def mark_hls_ready(self, job_id: UUID, playlist_path: str):
        """
        Mark HLS stream as ready for playback.
        Called when first segment is generated.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE job_queue
                SET hls_ready = TRUE,
                    hls_playlist_path = $1
                WHERE job_id = $2
            """, playlist_path, job_id)
        
        logger.info(f"🎉 [{self.worker_id}] HLS stream ready: {job_id}")
    
    async def update_hls_segments(self, job_id: UUID, segments_done: int, total_segments: int):
        """Update HLS segment count."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE job_queue
                SET segments_generated = $1,
                    total_segments = $2
                WHERE job_id = $3
            """, segments_done, total_segments, job_id)
    
    async def complete_job(
        self,
        job_id: UUID,
        result_path: str,
        processing_time: int,
        hls_playlist_path: str
    ):
        """Mark job as completed."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE job_queue
                SET 
                    status = 'completed',
                    result_path = $1,
                    processing_time_seconds = $2,
                    hls_playlist_path = $3,
                    completed_at = NOW(),
                    progress_percent = 100,
                    hls_ready = TRUE
                WHERE job_id = $4
            """, result_path, processing_time, hls_playlist_path, job_id)
    
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
    
    async def process_job(self, job: Dict):
        """
        Process một video job với HLS streaming.
        
        PIPELINE:
        1. Validate input
        2. Setup HLS output directory
        3. Initialize HLS writer
        4. Process video frame-by-frame:
           - Run AI models
           - Use Optical Flow for lane optimization
           - Write to HLS segments
        5. Finalize HLS stream
        6. Mark job complete
        """
        job_id = job['job_id']
        self.current_job_id = job_id
        start_time = datetime.now()
        
        logger.info(f"🚀 [{self.worker_id}] Processing job {job_id}")
        
        try:
            # === 1. VALIDATE INPUT ===
            input_path = job['video_path']
            if not input_path or not Path(input_path).exists():
                raise FileNotFoundError(f"Video not found: {input_path}")
            
            # === 2. SETUP OUTPUT ===
            output_base = Path(os.getenv('VIDEOS_OUTPUT_DIR', '/hdd3/adas/videos/output'))
            job_output_dir = output_base / str(job_id)
            job_output_dir.mkdir(parents=True, exist_ok=True)
            
            hls_dir = job_output_dir / "hls"
            hls_dir.mkdir(parents=True, exist_ok=True)
            
            fallback_video_path = job_output_dir / "result.mp4"
            
            logger.info(f"  Input: {input_path}")
            logger.info(f"  HLS Output: {hls_dir}")
            logger.info(f"  Fallback MP4: {fallback_video_path}")
            
            # === 3. LOAD PIPELINE ===
            pipeline = self._load_pipeline()
            
            # Reset Optical Flow state for new video
            self.optical_flow_warper.reset()
            
            # === 4. OPEN VIDEO ===
            cap = cv2.VideoCapture(str(input_path))
            if not cap.isOpened():
                raise RuntimeError(f"Cannot open video: {input_path}")
            
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            logger.info(f"  Video: {width}x{height} @ {fps:.1f}fps, {total_frames} frames")
            
            # === 5. INITIALIZE HLS WRITER ===
            hls_writer = HLSWriter(
                output_dir=str(hls_dir),
                fps=fps,
                width=width,
                height=height,
                segment_duration=2.0,
                on_first_segment_ready=lambda: asyncio.create_task(
                    self.mark_hls_ready(job_id, str(hls_dir / "playlist.m3u8"))
                ),
                on_segment_generated=lambda idx, total: asyncio.create_task(
                    self.update_hls_segments(job_id, idx, total)
                )
            )
            
            # === 6. START HEARTBEAT TASK ===
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_id))
            
            # === 7. PROCESS VIDEO ===
            frame_idx = 0
            events = []
            
            # Optional: Fallback MP4 writer (nếu cần)
            mp4_writer = cv2.VideoWriter(
                str(fallback_video_path),
                cv2.VideoWriter_fourcc(*'mp4v'),
                fps,
                (width, height)
            )
            
            try:
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # Convert to grayscale for optical flow
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    
                    # === AI INFERENCE ===
                    results = self._run_inference(frame, gray, frame_idx, pipeline)
                    
                    # === DRAW OVERLAY ===
                    frame_with_overlay = self._draw_overlay(frame, results)
                    
                    # === WRITE TO HLS ===
                    hls_writer.write_frame(frame_with_overlay)
                    
                    # === WRITE TO MP4 (fallback) ===
                    mp4_writer.write(frame_with_overlay)
                    
                    # === COLLECT EVENTS ===
                    if results.get('events'):
                        events.extend(results['events'])
                    
                    # === UPDATE PROGRESS ===
                    frame_idx += 1
                    if frame_idx % 30 == 0:  # Update every second
                        progress = int((frame_idx / total_frames) * 100)
                        await self.update_progress(job_id, progress)
                    
                    # === HEARTBEAT (mỗi 10s) ===
                    if frame_idx % int(fps * 10) == 0:
                        await self.heartbeat(job_id)
                
            finally:
                cap.release()
                mp4_writer.release()
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            
            # === 8. FINALIZE HLS ===
            hls_writer.finalize()
            
            # HLS stats
            hls_stats = hls_writer.get_stats()
            logger.info(f"  HLS: {hls_stats['segments_completed']} segments")
            
            # Optical Flow stats
            flow_stats = self.optical_flow_warper.get_stats()
            logger.info(f"  Optical Flow Savings: {flow_stats['savings_percent']:.1f}%")
            
            # === 9. STORE EVENTS ===
            await self._store_events(job['id'], events)
            
            # === 10. COMPLETE JOB ===
            processing_time = int((datetime.now() - start_time).total_seconds())
            await self.complete_job(
                job_id,
                str(fallback_video_path),
                processing_time,
                str(hls_dir / "playlist.m3u8")
            )
            
            # Stats
            self.jobs_processed += 1
            self.total_processing_time += processing_time
            
            logger.info(
                f"✅ [{self.worker_id}] Job {job_id} completed in {processing_time}s "
                f"({total_frames / processing_time:.1f} fps)"
            )
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_id}] Job {job_id} failed: {e}", exc_info=True)
            await self.fail_job(job_id, str(e))
        
        finally:
            self.current_job_id = None
    
    def _run_inference(
        self,
        frame: np.ndarray,
        gray: np.ndarray,
        frame_idx: int,
        pipeline: Dict
    ) -> Dict:
        """
        Run AI inference on one frame.
        
        Uses Optical Flow optimization for lane detection.
        """
        results = {}
        
        # === OBJECT DETECTION (every frame) ===
        try:
            objects = pipeline['object'].detect(frame)
            results['objects'] = objects
        except Exception as e:
            logger.warning(f"Object detection failed: {e}")
            results['objects'] = []
        
        # === LANE DETECTION (with Optical Flow optimization) ===
        try:
            should_run_lanenet, reason = self.optical_flow_warper.should_run_lanenet(gray)
            
            if should_run_lanenet:
                # Run full LaneNet inference
                lane_mask = pipeline['lane'].detect(frame)
                final_lane_mask = self.optical_flow_warper.update(gray, lane_mask)
            else:
                # Warp previous mask (FAST)
                final_lane_mask = self.optical_flow_warper.update(gray, None)
            
            results['lane_mask'] = final_lane_mask
            results['lane_method'] = 'lanenet' if should_run_lanenet else 'warped'
        except Exception as e:
            logger.warning(f"Lane detection failed: {e}")
            results['lane_mask'] = np.zeros_like(gray)
            results['lane_method'] = 'failed'
        
        # === DISTANCE ESTIMATION (every frame) ===
        try:
            distance_map = pipeline['distance'].estimate(frame)
            results['distance_map'] = distance_map
        except Exception as e:
            logger.warning(f"Distance estimation failed: {e}")
            results['distance_map'] = None
        
        # === DRIVER MONITORING (if in_cabin video) ===
        # TODO: Add driver monitoring based on video_type
        
        # === EVENT DETECTION ===
        results['events'] = self._detect_events(results, frame_idx)
        
        return results
    
    def _detect_events(self, results: Dict, frame_idx: int) -> list:
        """Detect safety events from inference results."""
        events = []
        
        # Example: Forward collision warning
        if results.get('objects'):
            for obj in results['objects']:
                if obj.get('class') == 'car' and obj.get('distance', float('inf')) < 10.0:
                    events.append({
                        'type': 'forward_collision_warning',
                        'level': 'critical',
                        'frame': frame_idx,
                        'time': frame_idx / 30.0,  # Assume 30fps
                        'data': {
                            'message': 'Xe phía trước quá gần',
                            'distance': obj.get('distance')
                        }
                    })
        
        return events
    
    def _draw_overlay(self, frame: np.ndarray, results: Dict) -> np.ndarray:
        """Draw AI results on frame."""
        overlay = frame.copy()
        
        # Draw lane mask
        if results.get('lane_mask') is not None:
            lane_mask = results['lane_mask']
            if len(lane_mask.shape) == 2:
                lane_colored = cv2.applyColorMap(lane_mask, cv2.COLORMAP_JET)
                overlay = cv2.addWeighted(overlay, 0.7, lane_colored, 0.3, 0)
        
        # Draw objects
        if results.get('objects'):
            for obj in results['objects']:
                bbox = obj.get('bbox')
                if bbox:
                    x1, y1, x2, y2 = map(int, bbox)
                    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"{obj.get('class', 'unknown')} {obj.get('confidence', 0):.2f}"
                    cv2.putText(overlay, label, (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # Draw method indicator (debug)
        method = results.get('lane_method', '')
        color = (0, 255, 0) if method == 'warped' else (0, 0, 255)
        cv2.putText(overlay, f"Lane: {method}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        return overlay
    
    async def _heartbeat_loop(self, job_id: UUID):
        """Send periodic heartbeats."""
        while True:
            await asyncio.sleep(30)
            await self.heartbeat(job_id)
    
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
                        json.dumps(event.get('data', {}))
                    )
                except Exception as e:
                    logger.warning(f"Failed to store event: {e}")
    
    async def run(self):
        """
        Main worker loop.
        
        FIFO queue processing with backoff when idle.
        """
        await self.init()
        
        logger.info(f"🚀 [{self.worker_id}] Starting main loop...")
        logger.info(f"    Device: {self.device}")
        logger.info(f"    VRAM Limit: {self.vram_limit_gb}GB")
        
        idle_count = 0
        
        while self.running:
            try:
                # Claim next job
                job = await self.claim_job()
                
                if job:
                    idle_count = 0
                    await self.process_job(job)
                else:
                    # No jobs - backoff
                    idle_count += 1
                    backoff = min(10, 2 + idle_count * 0.5)
                    
                    if idle_count == 1:
                        logger.info(f"⏸️  [{self.worker_id}] No jobs available, sleeping...")
                    
                    await asyncio.sleep(backoff)
            
            except Exception as e:
                logger.error(f"❌ [{self.worker_id}] Worker error: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        # Shutdown
        await self.shutdown()
        
        # Print stats
        logger.info(f"📊 [{self.worker_id}] Final stats:")
        logger.info(f"    Jobs processed: {self.jobs_processed}")
        if self.jobs_processed > 0:
            avg_time = self.total_processing_time / self.jobs_processed
            logger.info(f"    Avg processing time: {avg_time:.1f}s")


# ============================================
# MAIN
# ============================================
def main():
    parser = argparse.ArgumentParser(description='ADAS GPU Worker V2')
    parser.add_argument('--worker-id', default=f"worker_{os.getpid()}")
    parser.add_argument('--device', default='cuda', choices=['cuda', 'cpu'])
    parser.add_argument('--vram-limit', type=float, default=6.0, help='VRAM limit in GB')
    parser.add_argument('--database-url', default=os.getenv('DATABASE_URL'))
    
    args = parser.parse_args()
    
    if not args.database_url:
        print("❌ ERROR: DATABASE_URL environment variable required")
        print("   Example: export DATABASE_URL='postgresql://user:pass@localhost/adas'")
        sys.exit(1)
    
    # Create and run worker
    worker = GPUWorkerV2(
        worker_id=args.worker_id,
        database_url=args.database_url,
        device=args.device,
        vram_limit_gb=args.vram_limit
    )
    
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("👋 Worker interrupted by user")


if __name__ == '__main__':
    main()
