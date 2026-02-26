"""
GPU WORKER V4 — Full ADAS V4 Pipeline
=======================================
Inherits DB/queue/NVDEC/NVENC boilerplate from SimpleGPUWorker.
Overrides only _load_pipeline() and process_job() with the V4 stack:

    NVDEC  →  LaneDetectorV4  →  YOLO + ByteTracker  →  DistanceEstimator
           →  RiskEngineV4   →  VietnameseOverlayRenderer  →  NVENC

Key upgrades over SimplegpuWorker (V3):
  • Classical BEV lane detection (no YOLO-seg wasted on lanes)
  • ByteTrack persistent IDs → smooth distance/TTC history
  • TTC-based risk: SAFE>5s, WARNING<4s, DANGER<2s, CRITICAL<1s
  • PIL Vietnamese banners (correct diacritics, flash on CRITICAL)
  • Ego Danger Zone polygon overlay
  • Tesla-style top HUD strip

Usage::

    python workers/gpu_worker_v4.py --worker-id v4_worker_1 --device cuda

Author  : Senior ADAS Engineer — V4 Architecture
Version : 4.0.0
Date    : 2026-02-25
"""

import os
import sys
import time
import signal
import logging
import argparse
import asyncio
import asyncpg
import subprocess
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from uuid import UUID

import cv2
import numpy as np
from dotenv import load_dotenv

# ── Project root setup ────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from backend.core.ffmpeg_utils import FFmpegEncoder, get_video_info, FFMPEG

# Reuse parent class DB/queue/NVDEC/NVENC helpers
from workers.gpu_worker_simple import SimpleGPUWorker

# V4 perception stack
from backend.perception.lane.lane_detector_v4     import LaneDetectorV4
from backend.perception.object.object_detector_v11 import ObjectDetectorV11
from backend.perception.object.object_tracker      import ByteTracker
from backend.perception.distance.distance_estimator import DistanceEstimator
from backend.perception.risk.risk_engine_v4        import RiskEngineV4, RiskResultV4
from backend.perception.overlay.vietnamese_overlay  import VietnameseOverlayRenderer, render_full_frame

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(process)d] - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('api.log'),
    ]
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GPUWorkerV4
# ---------------------------------------------------------------------------

class GPUWorkerV4(SimpleGPUWorker):
    """
    V4 ADAS pipeline worker.

    Inherits from SimpleGPUWorker:
      + Database pool, claim_job(), complete_job(), fail_job(), _store_events()
      + update_progress(), run() main-loop
      + NVDEC frame producer thread pattern
      + FFmpegEncoder context-managed NVENC output

    Overrides:
      + _load_pipeline()   — replaces YOLO-lane with LaneDetectorV4 + ByteTracker
      + process_job()      — wires V4 pipeline, calls render_full_frame()
      + _run_v4_inference() — new method: full V4 per-frame data flow
    """

    def __init__(
        self,
        worker_id   : str,
        database_url: str,
        device      : str = "cuda",
    ):
        super().__init__(worker_id, database_url, device)

        # V4-specific state
        self._overlay_renderer: Optional[VietnameseOverlayRenderer] = None
        # Separate CUDA stream for lane cv2.cuda ops (runs in parallel with YOLO stream)
        self._stream_lane = None

        # Frame-stride inference cache (avoids running YOLO+Lane on every frame)
        # CPU reuses previous GPU results for skipped frames — still runs
        # ByteTrack / Distance / Risk / Overlay on every frame.
        self._infer_cache: Dict = {
            'lane_result'    : None,
            'obj_result'     : None,
            'last_infer_idx' : -99,
        }
        self.INFER_STRIDE: int = 2     # run GPU inference every N frames

        logger.info(f"[V4WORKER] {worker_id} — V4 pipeline enabled  stride={self.INFER_STRIDE}")

    # -----------------------------------------------------------------------
    # Override: _load_pipeline
    # -----------------------------------------------------------------------

    def _load_pipeline(self, video_type: str = 'dashcam') -> Dict:
        """
        V4 pipeline loader.

        dashcam  →  LaneDetectorV4 + ObjectDetectorV11 + ByteTracker
                     + DistanceEstimator + RiskEngineV4
        in_cabin →  DriverMonitorV11  (unchanged from V3)
        """
        if video_type in self._pipelines:
            return self._pipelines[video_type]

        import torch

        # One-time CUDA flags
        if torch.cuda.is_available() and not self._pipelines:
            torch.backends.cudnn.benchmark        = True
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32        = True
            torch.set_float32_matmul_precision('high')
            torch.cuda.empty_cache()
            props = torch.cuda.get_device_properties(0)
            logger.info(
                f"[GPU] {props.name}  "
                f"VRAM={props.total_memory // 1024**2}MB  "
                f"SM={props.multi_processor_count}"
            )

        pipeline: Dict = {}
        dummy = np.zeros((720, 1280, 3), dtype=np.uint8)

        if video_type == 'dashcam':
            logger.info("[V4] Loading V4 dashcam pipeline …")

            # Classical BEV lane (no GPU model needed)
            pipeline['lane'] = LaneDetectorV4(
                bev_src_ratios=None,   # use class default
                n_windows=12,
                margin_px=80,
                min_pix=50,
                smooth_alpha=0.25,
            )

            # Object detection (YOLO11x, 1 stream)
            pipeline['object'] = ObjectDetectorV11(
                device=self.device,
                conf_threshold=0.45,
            )

            # ByteTrack (pure Python, no GPU)
            pipeline['tracker'] = ByteTracker(
                track_thresh=0.50,
                track_buffer=30,
                match_thresh=0.85,
            )

            # Distance + TTC estimator
            pipeline['distance'] = DistanceEstimator(
                focal_length=700.0,
                camera_height=1.2,
            )

            # Risk engine (frame size set after first frame)
            pipeline['risk'] = RiskEngineV4(
                frame_w=1280, frame_h=720, fps=30.0
            )

            # Overlay renderer (stateful: holds flash timer)
            if self._overlay_renderer is None:
                self._overlay_renderer = VietnameseOverlayRenderer()
            pipeline['overlay'] = self._overlay_renderer

            # CUDA stream for GPU inference
            if torch.cuda.is_available():
                self._stream_obj  = torch.cuda.Stream()   # YOLO inference
                self._stream_lane = torch.cuda.Stream()   # lane cv2.cuda ops
            # 2 workers: thread-0 → YOLO, thread-1 → lane
            self._infer_pool = ThreadPoolExecutor(
                max_workers=2, thread_name_prefix='v4_gpu'
            )

            # ── FP16 YOLO: ~30 % faster inference, same accuracy on A30 ──
            if torch.cuda.is_available():
                try:
                    pipeline['object'].model.model.half()
                    # Tell YOLO to keep using fp16 for subsequent calls
                    pipeline['object'].model.overrides['half'] = True
                    logger.info("[V4] YOLO FP16 ✅")
                except Exception as _fp:
                    logger.warning(f"[V4] FP16 failed (non-fatal): {_fp}")

            # Warm-up
            logger.info("[V4] Warming up V4 dashcam models …")
            for _ in range(2):
                try:
                    pipeline['lane'].process_frame(dummy)
                    pipeline['object'].process_frame(dummy)
                except Exception as e:
                    logger.warning(f"[V4][warmup] {e}")
            logger.info("[V4] ✅ dashcam V4 pipeline ready")

        elif video_type == 'in_cabin':
            # In-cabin unchanged from V3
            from backend.perception.driver.driver_monitor_v11 import DriverMonitorV11
            logger.info("[V4] Loading in_cabin pipeline …")
            pipeline['driver'] = DriverMonitorV11(device=self.device)
            if torch.cuda.is_available():
                self._stream_driver = torch.cuda.Stream()
            self._infer_pool = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix='v4_drv'
            )
            for _ in range(2):
                try:
                    pipeline['driver'].process_frame(dummy)
                except Exception as e:
                    logger.warning(f"[V4][warmup-incabin] {e}")
            logger.info("[V4] ✅ in_cabin V4 pipeline ready")

        else:
            logger.warning(f"[V4] Unknown video_type '{video_type}', fallback → dashcam")
            return self._load_pipeline('dashcam')

        if torch.cuda.is_available():
            torch.cuda.synchronize()

        self._pipelines[video_type] = pipeline
        return pipeline

    # -----------------------------------------------------------------------
    # Override: process_job
    # -----------------------------------------------------------------------

    async def process_job(self, job: Dict):
        """
        Full V4 job pipeline.

        DECODE: FFmpeg NVDEC → raw BGR frames (background thread)
        INFER:  LaneV4 + YOLO→ByteTrack + Distance (CUDA stream)
        ASSESS: RiskEngineV4 (EgoDangerZone + TTC)
        RENDER: VietnameseOverlayRenderer (PIL)
        ENCODE: FFmpegEncoder NVENC
        """
        job_id   = job['job_id']
        self.current_job_id = job_id
        start_ts = time.time()

        logger.info(f"[V4JOB] {job_id} — Starting V4 pipeline")

        try:
            # ── Validate input ────────────────────────────────────────────
            input_path = job.get('video_path', '')
            if not input_path or not Path(input_path).exists():
                raise FileNotFoundError(f"Input video not found: {input_path}")

            # ── Output path ───────────────────────────────────────────────
            out_base = Path(os.getenv('VIDEOS_OUTPUT_DIR', './storage/result'))
            out_dir  = out_base / str(job_id)
            out_dir.mkdir(parents=True, exist_ok=True)
            result_path = out_dir / "result.mp4"

            # ── Load V4 pipeline ──────────────────────────────────────────
            video_type = job.get('video_type', 'dashcam')
            pipeline   = self._load_pipeline(video_type)
            logger.info(f"[V4JOB] type={video_type}  models={list(pipeline.keys())}")

            # ── Probe video ───────────────────────────────────────────────
            cap_p = cv2.VideoCapture(str(input_path))
            if not cap_p.isOpened():
                raise RuntimeError(f"Cannot open: {input_path}")
            fps          = cap_p.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap_p.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
            width        = int(cap_p.get(cv2.CAP_PROP_FRAME_WIDTH))
            height       = int(cap_p.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap_p.release()
            logger.info(f"[V4JOB] {width}×{height} @ {fps:.1f}fps  total={total_frames}")

            # Update risk engine resolution (may differ from default 1280×720)
            if 'risk' in pipeline:
                pipeline['risk'].danger_zone.update_resolution(width, height)

            # ── NVDEC producer ────────────────────────────────────────────
            frame_queue: queue.Queue = queue.Queue(maxsize=16)
            frame_size_bytes = width * height * 3

            def _nvdec_reader(path: str, fq: queue.Queue):
                codecs = ['h264_cuvid', 'hevc_cuvid', None]
                for codec in codecs:
                    cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error']
                    if codec:
                        cmd += ['-hwaccel', 'cuda', '-c:v', codec]
                    cmd += ['-i', path,
                            '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                            '-vsync', '0', 'pipe:1']
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            bufsize=frame_size_bytes * 4,
                        )
                        hw = codec or 'software'
                        logger.info(f"[V4DECODE] codec={hw}")
                        while True:
                            raw = proc.stdout.read(frame_size_bytes)
                            if len(raw) < frame_size_bytes:
                                break
                            frm = np.frombuffer(raw, np.uint8).reshape(height, width, 3).copy()
                            fq.put(frm)
                        proc.stdout.close()
                        proc.wait()
                        break
                    except Exception as e:
                        logger.warning(f"[V4DECODE] {codec} failed: {e}")
                        try: proc.kill()
                        except: pass
                fq.put(None)   # sentinel

            reader = threading.Thread(
                target=_nvdec_reader, args=(str(input_path), frame_queue),
                daemon=True, name='v4_nvdec'
            )
            reader.start()

            # ── Encode + inference loop ───────────────────────────────────
            frame_idx = 0
            all_events: List[Dict] = []

            with FFmpegEncoder(
                output_path=str(result_path),
                width=width, height=height, fps=fps,
                use_nvenc=True, preset='fast'
            ) as encoder:

                logger.info("[V4ENCODE] NVENC encoder started")

                while True:
                    frame = frame_queue.get()
                    if frame is None:
                        break

                    # ── Per-frame V4 inference ─────────────────────────
                    if video_type == 'dashcam':
                        final_frame, risk_result, events = self._run_v4_dashcam(
                            frame, frame_idx, fps, pipeline
                        )
                    else:
                        # in_cabin: reuse V3 overlay (driver only)
                        from workers.gpu_worker_simple import SimpleGPUWorker as _sw
                        results_v3 = self._run_comprehensive_adas_inference(
                            frame, frame_idx, pipeline, video_type
                        )
                        final_frame = self._draw_vietnamese_overlay(frame, results_v3)
                        events = results_v3.get('events', [])

                    encoder.write(final_frame)
                    all_events.extend(events)

                    frame_idx += 1
                    if frame_idx % 30 == 0:
                        pct     = int(frame_idx / total_frames * 100)
                        elapsed = time.time() - start_ts
                        spd     = frame_idx / max(elapsed, 0.01)
                        eta     = (total_frames - frame_idx) / max(spd, 0.01)
                        await self.update_progress(job_id, pct)
                        logger.info(
                            f"[V4PROG] [{job_id}] {pct:3d}%  "
                            f"frame={frame_idx}/{total_frames}  "
                            f"{spd:.1f}fps  ETA={eta:.0f}s"
                        )

            reader.join(timeout=5)

            # ── Finalise ──────────────────────────────────────────────────
            proc_sec = int(time.time() - start_ts)
            await self._store_events(job['id'], all_events)
            await self.complete_job(job_id, str(result_path), proc_sec)

            self.jobs_processed       += 1
            self.total_processing_time += proc_sec
            logger.info(
                f"[V4JOB] ✅ {job_id} done in {proc_sec}s  "
                f"({total_frames / max(proc_sec, 1):.1f}×real-time)"
            )

        except Exception as exc:
            logger.error(f"[V4JOB] ❌ {job_id} failed: {exc}", exc_info=True)
            await self.fail_job(job_id, str(exc))
        finally:
            self.current_job_id = None

    # -----------------------------------------------------------------------
    # V4 per-frame inference (dashcam)
    # -----------------------------------------------------------------------

    def _run_v4_dashcam(
        self,
        frame    : np.ndarray,
        frame_idx: int,
        fps      : float,
        pipeline : Dict,
    ):
        """
        Full V4 data-flow for one dashcam frame.

        Returns
        -------
        final_frame  : np.ndarray  — annotated BGR frame ready for NVENC
        risk_result  : RiskResultV4
        events       : List[Dict]  — for DB storage
        """
        import torch

        # ── Frame-stride cache ────────────────────────────────────────────
        # Run GPU inference (lane + YOLO) only every INFER_STRIDE frames.
        # Skipped frames reuse the previous result — ByteTrack / Distance /
        # Risk / Overlay still execute on every frame.
        cache = self._infer_cache
        run_inference = (
            cache['lane_result'] is None
            or (frame_idx - cache['last_infer_idx']) >= self.INFER_STRIDE
        )

        _safe_lane_default = {
            'annotated_frame': frame.copy(),
            'has_lane'       : False,
            'lane_offset'    : 0.0,
            'offset_level'   : 'SAFE',
        }

        if run_inference:
            # ── 1 ∥ 2. Concurrent GPU: lane cv2.cuda  +  YOLO FP16 ───────
            def _lane():
                try:
                    return pipeline['lane'].process_frame(frame)
                except Exception as exc:
                    logger.warning(f"[V4LANE] {exc}")
                    return _safe_lane_default

            def _detect():
                try:
                    if self._stream_obj and torch.cuda.is_available():
                        with torch.cuda.stream(self._stream_obj):
                            return pipeline['object'].process_frame(frame)
                    return pipeline['object'].process_frame(frame)
                except Exception as exc:
                    logger.warning(f"[V4OBJ] {exc}")
                    return {}

            if self._infer_pool:
                fut_lane = self._infer_pool.submit(_lane)
                fut_obj  = self._infer_pool.submit(_detect)
                lane_result = fut_lane.result()
                obj_result  = fut_obj.result()
            else:
                lane_result = _lane()
                obj_result  = _detect()

            if torch.cuda.is_available():
                torch.cuda.synchronize()

            # Update cache
            cache['lane_result']    = lane_result
            cache['obj_result']     = obj_result
            cache['last_infer_idx'] = frame_idx
        else:
            # ── Stride skip: reuse GPU results, patch annotated_frame ─────
            # Replace annotated_frame with fresh copy of current frame so the
            # corridor overlay is drawn on the correct frame (not a stale copy).
            lane_result = {
                **cache['lane_result'],
                'annotated_frame': frame.copy(),
            }
            obj_result = cache['obj_result']

        detections: List[Dict] = obj_result.get('detections', [])

        # ── 3. ByteTrack update ───────────────────────────────────────────
        tracked_objects: List[Dict] = []
        try:
            tracked_objects = pipeline['tracker'].update(detections)
        except Exception as e:
            logger.warning(f"[V4TRACK] {e}")
            tracked_objects = detections   # fallback: use raw detections

        # ── 4. Distance + TTC per track ───────────────────────────────────
        dist_objects: List[Dict] = []
        try:
            for obj in tracked_objects:
                if not obj.get('bbox'):
                    continue
                enriched = pipeline['distance'].process_tracked_object(
                    tracked_obj  = obj,
                    frame_height = frame.shape[0],
                    frame_number = frame_idx,
                )
                dist_objects.append(enriched)
        except Exception as e:
            logger.warning(f"[V4DIST] {e}")
            dist_objects = tracked_objects

        # ── 5. Risk Assessment ────────────────────────────────────────────
        risk_result: RiskResultV4 = RiskResultV4()
        try:
            risk_result = pipeline['risk'].assess(
                tracked_objects  = dist_objects,
                lane_offset      = lane_result.get('lane_offset', 0.0),
                lane_offset_level= lane_result.get('offset_level', 'SAFE'),
                frame_w          = frame.shape[1],
                frame_h          = frame.shape[0],
                frame_idx        = frame_idx,
            )
        except Exception as e:
            logger.warning(f"[V4RISK] {e}")

        # ── 6. Compose final frame ────────────────────────────────────────
        try:
            final_frame = render_full_frame(
                base_frame      = frame,
                lane_result     = lane_result,
                tracked_objects = dist_objects,
                risk_result     = risk_result,
                fps             = fps,
                frame_idx       = frame_idx,
                renderer        = pipeline.get('overlay'),
            )
        except Exception as e:
            logger.warning(f"[V4RENDER] {e}")
            final_frame = lane_result.get('annotated_frame', frame.copy())

        # ── 7. Build events for DB ────────────────────────────────────────
        events: List[Dict] = []
        for alert in risk_result.alerts:
            events.append({
                'type' : alert.get('type', 'warning'),
                'level': alert.get('severity', 'warning').lower(),
                'time' : frame_idx / max(fps, 1.0),
                'frame': frame_idx,
                'data' : {'message': alert.get('message_vi', '')},
            })

        if frame_idx % 60 == 0:
            logger.info(
                f"[V4FRAME {frame_idx}] "
                f"lane={'OK' if lane_result.get('has_lane') else 'LOST'}  "
                f"offset={lane_result.get('lane_offset', 0):.2f}  "
                f"objs={len(dist_objects)}  "
                f"zone={len(risk_result.objects_in_zone)}  "
                f"risk={risk_result.scene_risk}"
            )

        return final_frame, risk_result, events


    # -----------------------------------------------------------------------
    # Override run(): LISTEN/NOTIFY instead of polling backoff
    # -----------------------------------------------------------------------

    async def run(self):
        """
        V4 main loop with PostgreSQL LISTEN/NOTIFY.

        When the API inserts a new job it sends:
            SELECT pg_notify('adas_new_job', '<job_id>')

        This listener wakes up immediately (instead of sleeping up to 10 s)
        and tries to claim the job.  Falls back to a 30-s timeout poll in
        case the NOTIFY was missed (e.g. worker started after NOTIFY sent).
        """
        await self.init()
        logger.info(f"[V4] {self.worker_id} starting with LISTEN/NOTIFY loop")

        # Dedicated connection for LISTEN (separate from the pool)
        notify_conn = await asyncpg.connect(self.database_url)
        _wakeup = asyncio.Event()

        def _on_notify(conn, pid, channel, payload):
            _wakeup.set()

        await notify_conn.execute("LISTEN adas_new_job")
        await notify_conn.add_listener('adas_new_job', _on_notify)
        logger.info(f"[V4] Listening on PostgreSQL channel 'adas_new_job'")

        try:
            while self.running:
                try:
                    job = await self.claim_job()
                    if job:
                        _wakeup.clear()
                        await self.process_job(job)
                        # After finishing, immediately try to claim next
                        # (there may be more pending jobs queued up)
                    else:
                        # Nothing to do — wait for NOTIFY or 30-s timeout
                        try:
                            await asyncio.wait_for(_wakeup.wait(), timeout=30.0)
                        except asyncio.TimeoutError:
                            pass
                        _wakeup.clear()

                except Exception as exc:
                    logger.error(f"[V4] Worker error: {exc}", exc_info=True)
                    await asyncio.sleep(5)
        finally:
            try:
                await notify_conn.remove_listener('adas_new_job', _on_notify)
                await notify_conn.close()
            except Exception:
                pass
            await self.shutdown()

        logger.info(
            f"[V4STATS] {self.jobs_processed} jobs  "
            f"avg={self.total_processing_time / max(1, self.jobs_processed):.1f}s"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
        logger.info(f"[V4] .env loaded from {env_path}")
    else:
        logger.warning("[V4] .env not found — using environment variables")

    parser = argparse.ArgumentParser(description="GPU Worker V4 — ADAS V4 Pipeline")
    parser.add_argument('--worker-id',    default=f"v4_worker_{os.getpid()}")
    parser.add_argument('--device',       default='cuda', choices=['cuda', 'cpu'])
    parser.add_argument('--database-url', default=os.getenv('DATABASE_URL'))
    args = parser.parse_args()

    if not args.database_url:
        logger.error("[V4] DATABASE_URL missing — check .env")
        sys.exit(1)

    worker = GPUWorkerV4(
        worker_id    = args.worker_id,
        database_url = args.database_url,
        device       = args.device,
    )

    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("[V4] Worker interrupted")


if __name__ == '__main__':
    main()
