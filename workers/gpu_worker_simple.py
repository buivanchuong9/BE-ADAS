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

# ── MUST be before any cv2 import ──────────────────────────────────────────
# Injects OpenCV CUDA build paths so cv2 resolves to the GPU build even when
# the process is started via nohup (no ~/.bashrc, no LD_LIBRARY_PATH).
import backend.core.cv2_loader   # noqa: F401, E402
# ───────────────────────────────────────────────────────────────────────────

# Import dependencies
import asyncio
import asyncpg
import subprocess
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
from dotenv import load_dotenv

# Load .env explicitly
load_dotenv(PROJECT_ROOT / ".env")

# Import FFmpeg utilities (SAFE)
from backend.core.ffmpeg_utils import FFmpegEncoder, get_video_info, FFMPEG

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
        
        # AI Pipelines (lazy-loaded per video_type, cached after first load)
        # Keys: 'dashcam' | 'in_cabin'
        self._pipelines: Dict[str, Dict] = {}

        # GPU inference: CUDA streams + thread pool (set during _load_pipeline)
        self._stream_obj:    object = None   # torch.cuda.Stream (dashcam)
        self._stream_driver: object = None   # torch.cuda.Stream (in_cabin)
        self._infer_pool: Optional[ThreadPoolExecutor] = None

        # Whether cv2.cuda.addWeighted is available for GPU-accelerated overlay blending
        self._cuda_overlay: bool = False

        # Voice warnings (TTS hook)
        self.voice_enabled = True
        self.last_warning_time = 0
        self.warning_cooldown = 3.0  # seconds between warnings
        
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
    
    def _load_pipeline(self, video_type: str = 'dashcam') -> Dict:
        """
        Lazy-load AI pipeline theo loại video.

        dashcam  → ObjectDetectorV11 (yolo11x) + LaneDetectorV11 (BEV) + DistanceEstimator
        in_cabin → DriverMonitorV11 (yolo11x-pose)

        Pipeline được cache sau lần đầu → job thứ 2 cùng loại không mất thời gian load lại.
        """
        if video_type in self._pipelines:
            return self._pipelines[video_type]

        import torch

        # A30 flags - chỉ set 1 lần khi load pipeline đầu tiên
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
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)

        if video_type == 'dashcam':
            from backend.perception.object.object_detector_v11  import ObjectDetectorV11
            from backend.perception.distance.distance_estimator import DistanceEstimator
            from backend.perception.lane.lane_detector_v4        import LaneDetectorV4 as LaneDetectorV11

            logger.info("[GPU] Loading pipeline 'dashcam': ObjectDetector + Lane + Distance...")
            pipeline['object']   = ObjectDetectorV11(device=self.device, conf_threshold=0.5, imgsz=416)
            pipeline['lane']     = LaneDetectorV11(device=self.device)
            pipeline['distance'] = DistanceEstimator(focal_length=700.0, camera_height=1.2)

            if torch.cuda.is_available():
                self._stream_obj = torch.cuda.Stream()
            self._infer_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='adas_obj')

            logger.info("[GPU] Warming up dashcam models (2 passes)...")
            for _ in range(2):
                try:
                    pipeline['object'].process_frame(dummy)
                    pipeline['lane'].process_frame(dummy)
                except Exception as e:
                    logger.warning(f"[GPU] Warmup (non-fatal): {e}")

            # Probe cv2.cuda.addWeighted — available only with the CUDA-built OpenCV
            try:
                if hasattr(cv2, 'cuda') and cv2.cuda.getCudaEnabledDeviceCount() > 0:
                    _t = cv2.cuda_GpuMat()
                    _t.upload(dummy)
                    _t2 = cv2.cuda_GpuMat()
                    _t2.upload(dummy)
                    cv2.cuda.addWeighted(_t, 0.5, _t2, 0.5, 0)
                    self._cuda_overlay = True
                    logger.info("[GPU] ✅ cv2.cuda.addWeighted available — overlay blending on GPU")
            except Exception as _cv:
                self._cuda_overlay = False
                logger.info(f"[GPU] cv2.cuda.addWeighted not available, overlay on CPU ({_cv})")

            logger.info("[GPU] ✅ dashcam pipeline ready (1 YOLO + BEV lane)")

        elif video_type == 'in_cabin':
            from backend.perception.driver.driver_monitor_v11 import DriverMonitorV11

            logger.info("[GPU] Loading pipeline 'in_cabin': DriverMonitor...")
            pipeline['driver'] = DriverMonitorV11(device=self.device)

            if torch.cuda.is_available():
                self._stream_driver = torch.cuda.Stream()
            self._infer_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='adas_drv')

            logger.info("[GPU] Warming up in_cabin model (2 passes)...")
            for _ in range(2):
                try:
                    pipeline['driver'].process_frame(dummy)
                except Exception as e:
                    logger.warning(f"[GPU] Warmup (non-fatal): {e}")
            logger.info("[GPU] ✅ in_cabin pipeline ready (driver monitor)")

        else:
            logger.warning(f"[GPU] Unknown video_type '{video_type}', fallback to dashcam")
            return self._load_pipeline('dashcam')

        if torch.cuda.is_available():
            torch.cuda.synchronize()

        self._pipelines[video_type] = pipeline
        return pipeline
    
    async def claim_job(self) -> Optional[Dict]:
        """Claim next pending job atomically."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    UPDATE job_queue jq
                    SET 
                        status = 'processing',
                        worker_id = $1,
                        worker_heartbeat = NOW(),
                        started_at = NOW(),
                        attempts = attempts + 1
                    WHERE jq.id = (
                        SELECT id FROM job_queue
                        WHERE status = 'pending'
                          AND attempts < max_attempts
                        ORDER BY priority DESC, created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING 
                        jq.id, jq.job_id, jq.video_id,
                        jq.video_filename, jq.video_type, jq.device
                """, self.worker_id)
                
                if row:
                    # Lấy storage_path từ bảng videos
                    video_path = None
                    video_filename = row['video_filename']
                    if row['video_id']:
                        vrow = await conn.fetchrow(
                            "SELECT storage_path, original_filename FROM videos WHERE id = $1",
                            row['video_id']
                        )
                        if vrow:
                            video_path = vrow['storage_path']
                            if not video_filename:
                                video_filename = vrow['original_filename']
                    
                    return {
                        'id': row['id'],
                        'job_id': row['job_id'],
                        'video_path': video_path,
                        'video_filename': video_filename,
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
            
            # === LOAD PIPELINE (chỉ load models cần thiết cho video_type) ===
            video_type = job.get('video_type', 'dashcam')
            pipeline = self._load_pipeline(video_type)
            logger.info(f"[JOB] video_type='{video_type}' | models: {list(pipeline.keys())}")

            # ── Probe video metadata (CPU-light, 1 call only) ───────────
            logger.info("[DECODE] Probing video metadata...")
            cap_probe = cv2.VideoCapture(str(input_path))
            if not cap_probe.isOpened():
                raise RuntimeError(f"Cannot open video: {input_path}")
            fps          = cap_probe.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap_probe.get(cv2.CAP_PROP_FRAME_COUNT))
            width        = int(cap_probe.get(cv2.CAP_PROP_FRAME_WIDTH))
            height       = int(cap_probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap_probe.release()
            logger.info(f"[VIDEO] {width}x{height} @ {fps:.1f}fps, {total_frames} frames")

            # ── NVDEC producer thread ─────────────────────────────────────
            # FFmpeg -hwaccel cuda -c:v h264_cuvid → GPU hardware decoder (NVDEC)
            # giải phóng CPU hoàn toàn khỏi H.264 decoding.
            # Frames được pipe ra raw BGR24 bytes, đẩy vào bounded queue.
            frame_queue: queue.Queue = queue.Queue(maxsize=16)
            frame_size = width * height * 3  # bytes per BGR24 frame

            def _nvdec_reader(path: str, fq: queue.Queue):
                """
                Chạy FFmpeg NVDEC trong background thread.
                Thử h264_cuvid → hevc_cuvid → software fallback.
                CPU chỉ read từ pipe, không decode bitstream.
                """
                codecs_to_try = ['h264_cuvid', 'hevc_cuvid', None]
                for codec in codecs_to_try:
                    cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error']
                    if codec:
                        # NVDEC hardware decode
                        cmd += ['-hwaccel', 'cuda', '-c:v', codec]
                    cmd += ['-i', path,
                            '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                            '-vsync', '0', 'pipe:1']
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            bufsize=frame_size * 4,   # 4-frame read buffer
                        )
                        hw_label = codec if codec else 'software'
                        logger.info(f"[DECODE] FFmpeg decoder: {hw_label}")
                        while True:
                            raw = proc.stdout.read(frame_size)
                            if len(raw) < frame_size:
                                break
                            frame = np.frombuffer(raw, dtype=np.uint8
                                                  ).reshape(height, width, 3).copy()
                            fq.put(frame)       # blocks when queue is full (back-pressure)
                        proc.stdout.close()
                        proc.wait()
                        break                    # success → stop trying fallbacks
                    except Exception as e:
                        logger.warning(f"[DECODE] {codec} failed: {e}, trying next...")
                        try:
                            proc.kill()
                        except Exception:
                            pass
                fq.put(None)  # sentinel: stream finished

            reader_thread = threading.Thread(
                target=_nvdec_reader,
                args=(str(input_path), frame_queue),
                daemon=True,
                name='nvdec_reader',
            )
            reader_thread.start()

            # === PROCESS VIDEO WITH SAFE ENCODER ===
            frame_idx = 0
            events = []

            with FFmpegEncoder(
                output_path=str(result_video_path),
                width=width,
                height=height,
                fps=fps,
                use_nvenc=True,   # NVENC GPU encode
                preset='fast'
            ) as encoder:

                logger.info("[ENCODE] FFmpeg NVENC encoder started")

                # ── Separate encode thread ───────────────────────────────
                # CPU libx264 encode (~3-5ms/frame) chạy trong background thread
                # → GPU không phải chờ → tăng throughput đáng kể
                _encode_q: queue.Queue = queue.Queue(maxsize=8)

                def _encode_worker():
                    while True:
                        item = _encode_q.get()
                        if item is None:   # sentinel
                            break
                        encoder.write(item)

                _encode_thread = threading.Thread(
                    target=_encode_worker, daemon=True, name='encode_worker'
                )
                _encode_thread.start()
                logger.info("[ENCODE] Async encode thread started")

                while True:
                    # ── Pull decoded frame from NVDEC queue ─────────────
                    frame = frame_queue.get()
                    if frame is None:
                        break                    # end of video

                    # === INFERENCE ADAS HOÀN CHỈNH (GPU parallel) ===
                    results = self._run_comprehensive_adas_inference(frame, frame_idx, pipeline, video_type)

                    # === DRAW OVERLAY ===
                    frame_with_overlay = self._draw_overlay(frame, results)

                    # === VOICE WARNINGS ===
                    self._handle_voice_warnings(results)

                    # === ENCODE FRAME — async (libx264 in bg thread) ===
                    _encode_q.put(frame_with_overlay)   # non-blocking; 8-frame buffer

                    # === COLLECT EVENTS ===
                    if results.get('events'):
                        events.extend(results['events'])

                    # === PROGRESS UPDATE (DB write + detailed log) ===
                    frame_idx += 1
                    if frame_idx % 30 == 0:
                        progress   = int((frame_idx / max(1, total_frames)) * 100)
                        elapsed    = time.time() - start_time
                        fps_proc   = frame_idx / max(elapsed, 0.001)
                        remaining  = (total_frames - frame_idx) / max(fps_proc, 0.001)
                        await self.update_progress(job_id, progress)
                        logger.info(
                            f"[PROGRESS] [{job_id}] "
                            f"{progress:3d}%  frame={frame_idx}/{total_frames}  "
                            f"speed={fps_proc:.1f}fps  ETA={remaining:.0f}s"
                        )

                # Drain encode queue — flush tất cả frames trước khi FFmpegEncoder đóng pipe
                _encode_q.put(None)   # sentinel: dừng encode thread
                _encode_thread.join(timeout=60)
                logger.info("[ENCODE] All frames written, closing encoder")

            reader_thread.join(timeout=5)
            
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
    
    def _run_comprehensive_adas_inference(
        self, frame: np.ndarray, frame_idx: int, pipeline: Dict,
        video_type: str = 'dashcam'
    ) -> Dict:
        """
        ADAS inference - chỉ chạy models đã load theo video_type.
        dashcam  → object(GPU) + lane(BEV) + distance
        in_cabin → driver monitoring
        """
        import torch
        results: Dict = {'frame_idx': frame_idx, 'warnings': []}

        if video_type == 'dashcam':
            # 1. Object detection trên CUDA stream
            def _run_objects():
                try:
                    if self._stream_obj and torch.cuda.is_available():
                        with torch.cuda.stream(self._stream_obj):
                            return pipeline['object'].process_frame(frame)
                    return pipeline['object'].process_frame(frame)
                except Exception as e:
                    logger.warning(f"[INFER] object: {e}")
                    return {}

            # Submit object detection → chạy song song với lane detection bên dưới
            fut_obj = self._infer_pool.submit(_run_objects) if self._infer_pool else None

            # 2. Lane detection (stride=3) — chỉ chạy mỗi 3 frame, cache kết quả giữa các frame
            _LANE_STRIDE = 3
            try:
                if frame_idx % _LANE_STRIDE == 0:
                    lane_result = pipeline['lane'].process_frame(frame)
                    # LaneDetectorV4 returns: annotated_frame (frame+corridor), bev_debug (binary mask)
                    lane_result['_colored'] = lane_result.get('annotated_frame')
                    lane_result['mask']     = lane_result.get('bev_debug')
                    pipeline['_cached_lane'] = lane_result
                else:
                    lane_result = pipeline.get('_cached_lane', {})
                results['lane_mask']       = lane_result.get('mask')
                results['has_lane']        = lane_result.get('has_lane', False)
                results['lane_colored']    = lane_result.get('_colored')
                results['lane_offset']     = lane_result.get('lane_offset', 0.0)
                results['offset_level']    = lane_result.get('offset_level', 'SAFE')
            except Exception as e:
                logger.warning(f"[INFER] lane: {e}")
                results['lane_mask'] = None; results['has_lane'] = False
                results['lane_offset'] = 0.0; results['offset_level'] = 'SAFE'

            # 3. Lấy kết quả object (xong lúc lane đang chạy → song song thực sự)
            obj_result = fut_obj.result() if fut_obj else _run_objects()
            if torch.cuda.is_available():
                torch.cuda.synchronize()

            results['objects']      = obj_result.get('detections', [])
            results['object_stats'] = obj_result.get('stats', {})

            # 4. Distance + TTC + risk (CPU)
            distances = []
            try:
                for obj in results['objects']:
                    if not obj.get('bbox'):
                        continue
                    dist_info  = pipeline['distance'].estimate_distance_bbox(
                        bbox=obj['bbox'],
                        vehicle_type=obj.get('class_name', 'car'),
                        frame_height=frame.shape[0]
                    )
                    # Simple TTC: assume ego vehicle approaching at ~13 m/s (~50 km/h)
                    # Negative velocity = approaching
                    ttc = pipeline['distance'].compute_ttc(dist_info, -13.0) or float('inf')
                    risk_level = self._assess_risk(dist_info, ttc, obj.get('class_name', ''))
                    obj_d = {**obj, 'distance': dist_info, 'ttc': ttc, 'risk_level': risk_level}
                    distances.append(obj_d)
                    if risk_level in ('DANGER', 'CRITICAL'):
                        results['warnings'].append(self._create_warning(obj_d))
                results['objects_with_distance'] = distances
            except Exception as e:
                logger.warning(f"[INFER] distance: {e}")
                results['objects_with_distance'] = []

            # 5. Lane departure warning (LDW)
            offset_level = results.get('offset_level', 'SAFE')
            if offset_level == 'CRITICAL':
                results['warnings'].append({
                    'type': 'lane_departure',
                    'message': 'LECH LAN! Xe dang ra khoi lan duong',
                    'severity': 'critical',
                })
            elif offset_level == 'WARNING':
                results['warnings'].append({
                    'type': 'lane_departure',
                    'message': 'Chu y: Xe dang lech lan duong',
                    'severity': 'high',
                })

            results['driver_state']  = 'n/a'
            results['traffic_signs'] = []

        elif video_type == 'in_cabin':
            driver_result: Dict = {}
            try:
                if self._stream_driver and torch.cuda.is_available():
                    with torch.cuda.stream(self._stream_driver):
                        driver_result = pipeline['driver'].process_frame(frame)
                else:
                    driver_result = pipeline['driver'].process_frame(frame)
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
            except Exception as e:
                logger.warning(f"[INFER] driver: {e}")

            results['driver_state']          = driver_result.get('state', 'unknown')
            results['driver_confidence']     = driver_result.get('confidence', 0.0)
            results['driver_warnings']       = driver_result.get('warnings', [])
            results['warnings'].extend(results['driver_warnings'])
            results['objects_with_distance'] = []
            results['traffic_signs']         = []

        else:
            results['objects_with_distance'] = []
            results['traffic_signs']         = []

        # Events summary
        results['events'] = [
            {'type': w.get('type', 'warning'), 'level': w.get('severity', 'medium'),
             'time': frame_idx / 30.0, 'frame': frame_idx,
             'data': {'message': w.get('message', '')}}
            for w in results['warnings']
        ]
        if frame_idx % 60 == 0:
            obj_count = len(results.get('objects_with_distance', []))
            has_lane  = results.get('has_lane', False)
            logger.info(f"[FRAME {frame_idx}] objects={obj_count} lane={'YES' if has_lane else 'NO'} warnings={len(results['warnings'])}")
        return results
    
    def _draw_overlay(self, frame: np.ndarray, results: Dict) -> np.ndarray:
        """
        Ve overlay ADAS — giao dien tieng Viet.

        Hien thi:
        - Lan duong (corridor xanh Tesla-style)
        - Object bounding boxes + ten tieng Viet
        - Khoang cach & TTC cho tung vat the
        - Risk level (mau canh bao)
        - HUD panel thong tin
        - Canh bao va cham / lech lan

        lane_colored = annotated_frame tu LaneDetectorV4 (da ve corridor).
        Dung truc tiep lam base, khong blend lai lan 2.
        """
        lane_colored = results.get('lane_colored')
        h, w, _ = frame.shape

        # === 1. LAN DUONG ===
        # lane_colored IS the original frame with green corridor already drawn by LaneDetectorV4.
        # Use it directly as base overlay; no need for double-blend.
        if lane_colored is not None:
            if lane_colored.shape[:2] != (h, w):
                lane_colored = cv2.resize(lane_colored, (w, h))
            overlay = lane_colored.copy()
        else:
            overlay = frame.copy()

        # === 2. VẼ OBJECTS VỚI KHOẢNG CÁCH ===
        for obj in results.get('objects_with_distance', []):
            bbox = obj.get('bbox')
            if not bbox:
                continue

            x1, y1, x2, y2 = map(int, bbox)

            risk_level = obj.get('risk_level', 'SAFE')
            color = self._get_risk_color(risk_level)
            thickness = 3 if risk_level in ['DANGER', 'CRITICAL'] else 2

            # Bounding box
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, thickness)

            # Tên tiếng Việt + confidence
            class_name_vi = self._translate_class_name(obj.get('class_name', ''))
            confidence = obj.get('confidence', 0)
            distance   = obj.get('distance', 0)
            ttc        = obj.get('ttc', float('inf'))

            main_text = f"{class_name_vi} {confidence:.0%}"
            cv2.putText(overlay, main_text, (x1, y1-35),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            distance_text = f"KC: {distance:.1f}m"
            cv2.putText(overlay, distance_text, (x1, y1-15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            if ttc < 10:
                ttc_text = f"TTC: {ttc:.1f}s"
                cv2.putText(overlay, ttc_text, (x1, y1-5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)

        # === 3. VẼ BIỂN BÁO ===
        for sign in results.get('traffic_signs', []):
            bbox = sign.get('bbox')
            if bbox:
                x1, y1, x2, y2 = map(int, bbox)
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 255), 2)
                sign_name = sign.get('class_name', 'Bien bao')
                cv2.putText(overlay, sign_name, (x1, y1-10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

        # === 4. HUD PANEL (TOP-LEFT) ===
        self._draw_hud_panel(overlay, results, w, h)

        # === 5. WARNINGS (CENTER-TOP) ===
        self._draw_warnings(overlay, results, w)

        return overlay
    
    def _get_risk_color(self, risk_level: str) -> tuple:
        """Trả về màu BGR theo risk level."""
        colors = {
            'SAFE': (0, 255, 0),       # Xanh lá
            'CAUTION': (0, 255, 255),  # Vàng
            'DANGER': (0, 165, 255),   # Cam
            'CRITICAL': (0, 0, 255)    # Đỏ
        }
        return colors.get(risk_level, (255, 255, 255))

    def _translate_class_name(self, class_name: str) -> str:
        """Dịch tên class YOLO sang tiếng Việt (Việt hoá giao diện)."""
        translations = {
            'person': 'Nguoi',
            'car': 'O to',
            'truck': 'Xe tai',
            'bus': 'Xe buyt',
            'motorcycle': 'Xe may',
            'bicycle': 'Xe dap',
            'traffic light': 'Den giao thong',
            'stop sign': 'Bien dung',
            'fire hydrant': 'Tru nuoc',
            'dog': 'Cho',
            'cat': 'Meo',
            'bird': 'Chim',
            'horse': 'Ngua',
            'cow': 'Bo',
            'sheep': 'Cuu',
            'train': 'Tau hoa',
            'airplane': 'May bay',
            'boat': 'Thuyen',
            'bench': 'Ghe dai',
            'backpack': 'Ba lo',
            'umbrella': 'Du/O',
            'suitcase': 'Vali',
        }
        return translations.get(class_name.lower(), class_name)
    
    def _draw_hud_panel(self, overlay: np.ndarray, results: Dict, w: int, h: int):
        """Vẽ HUD panel ADAS (góc trên trái) — giao diện tiếng Việt."""
        objects = results.get('objects_with_distance', [])
        dangerous = [o for o in objects if o.get('risk_level') in ('CRITICAL', 'DANGER', 'CAUTION')]
        closest = None
        if dangerous:
            closest = min(dangerous, key=lambda o: o.get('distance', 9999))
        elif objects:
            closest = min(objects, key=lambda o: o.get('distance', 9999))

        panel_w = 310
        panel_h = 150 if closest else 130
        pad = 10
        x0, y0 = pad, pad

        # Nền bán trong suốt
        sub = overlay[y0: y0 + panel_h, x0: x0 + panel_w]
        black_bg = np.zeros_like(sub)
        cv2.addWeighted(sub, 0.3, black_bg, 0.7, 0, sub)

        # Viền theo mức rủi ro cao nhất
        max_risk = 'SAFE'
        if objects:
            risk_order = {'CRITICAL': 4, 'DANGER': 3, 'CAUTION': 2, 'SAFE': 1}
            max_risk = max(objects, key=lambda o: risk_order.get(o.get('risk_level', 'SAFE'), 1)).get('risk_level', 'SAFE')
        border_color = self._get_risk_color(max_risk)
        cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + panel_h), border_color, 2)

        # Thanh header
        cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + 24), border_color, -1)
        cv2.putText(overlay, "HE THONG ADAS", (x0 + 8, y0 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

        y_pos = y0 + 42
        sp    = 22

        # Số vật thể
        obj_count = len(objects)
        cv2.putText(overlay, f"Vat the: {obj_count}", (x0 + 8, y_pos),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        y_pos += sp

        # Vật thể gần nhất
        if closest:
            name  = self._translate_class_name(closest.get('class_name', ''))
            dist  = closest.get('distance', 0)
            ttc   = closest.get('ttc', float('inf'))
            rlvl  = closest.get('risk_level', 'SAFE')
            rc    = self._get_risk_color(rlvl)
            dist_txt = f"Gan nhat: {name} - {dist:.1f}m"
            cv2.putText(overlay, dist_txt, (x0 + 8, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, rc, 2)
            y_pos += sp
            if ttc < 10:
                ttc_txt = f"TTC: {ttc:.1f}s  [{rlvl}]"
                cv2.putText(overlay, ttc_txt, (x0 + 8, y_pos),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, rc, 2)
                y_pos += sp

        # Trạng thái làn đường
        has_lane   = results.get('has_lane', False)
        lane_txt   = "Lan duong: CO" if has_lane else "Lan duong: KHONG RO"
        lane_color = (0, 220, 0)     if has_lane else (0, 165, 255)
        cv2.putText(overlay, lane_txt, (x0 + 8, y_pos),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, lane_color, 1)
        y_pos += sp

        # Trạng thái tài xế
        driver_state = results.get('driver_state', 'unknown')
        state_vn     = self._translate_driver_state(driver_state)
        d_color      = (0, 255, 0) if driver_state == 'normal' else (0, 0, 255)
        cv2.putText(overlay, f"Tai xe: {state_vn}", (x0 + 8, y_pos),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, d_color, 1)
        y_pos += sp

        # Biển báo giao thông
        sign_count = len(results.get('traffic_signs', []))
        if sign_count:
            cv2.putText(overlay, f"Bien bao: {sign_count}", (x0 + 8, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)

    def _translate_driver_state(self, state: str) -> str:
        """Dịch trạng thái tài xế sang tiếng Việt (không dấu, tương thích cv2.putText)."""
        states = {
            'normal': 'Binh thuong',
            'drowsy': 'Buon ngu',
            'distracted': 'Mat tap trung',
            'looking_away': 'Nhin ra ngoai',
            'unknown': 'Khong ro',
            'n/a': 'N/A'
        }
        return states.get(state, 'Khong ro')
    
    def _draw_warnings(self, overlay: np.ndarray, results: Dict, w: int):
        """Draw prominent warnings at top-centre of frame."""
        warnings = results.get('warnings', [])
        if not warnings:
            return

        severity_order = {'critical': 0, 'high': 1, 'medium': 2}
        warnings = sorted(warnings, key=lambda x: severity_order.get(x.get('severity', 'medium'), 2))

        frame_idx = results.get('frame_idx', 0)
        flash_on = (frame_idx // 8) % 2 == 0

        y_start = 55
        for i, warning in enumerate(warnings[:3]):
            msg      = warning.get('message', '')
            severity = warning.get('severity', 'medium')

            if severity == 'critical':
                color     = (0, 0, 255)
                bg_color  = (0, 0, 120)
                thickness = 3
                scale     = 0.85
                if not flash_on:
                    continue
            elif severity == 'high':
                color     = (0, 100, 255)
                bg_color  = (0, 40, 100)
                thickness = 2
                scale     = 0.75
            else:
                color     = (0, 220, 220)
                bg_color  = (0, 80, 80)
                thickness = 2
                scale     = 0.65

            (tw, th), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
            x_c  = (w - tw) // 2
            y_pos = y_start + i * 44
            pad   = 6

            cv2.rectangle(overlay,
                          (x_c - pad, y_pos - th - pad),
                          (x_c + tw + pad, y_pos + pad),
                          bg_color, -1)
            cv2.rectangle(overlay,
                          (x_c - pad, y_pos - th - pad),
                          (x_c + tw + pad, y_pos + pad),
                          color, thickness)
            cv2.putText(overlay, msg, (x_c, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)
    
    def _assess_risk(self, distance: float, ttc: float, obj_type: str) -> str:
        """Assess collision risk based on distance and TTC."""
        if obj_type in ['motorcycle', 'bicycle']:
            critical_dist = 2.0
            danger_dist   = 5.0
            caution_dist  = 10.0
        else:
            critical_dist = 3.0
            danger_dist   = 7.0
            caution_dist  = 15.0

        if distance <= critical_dist:
            return 'CRITICAL'
        elif distance <= danger_dist:
            return 'DANGER'
        elif distance <= caution_dist:
            return 'CAUTION'

        if ttc <= 1.0:
            return 'CRITICAL'
        elif ttc <= 2.0:
            return 'DANGER'
        elif ttc <= 3.0:
            return 'CAUTION'

        return 'SAFE'
    
    def _create_warning(self, obj_with_distance: Dict) -> Dict:
        """Tạo cảnh báo va chạm tiếng Việt."""
        class_name_vi = self._translate_class_name(obj_with_distance.get('class_name', ''))
        distance      = obj_with_distance.get('distance', 0)
        ttc           = obj_with_distance.get('ttc', float('inf'))
        risk          = obj_with_distance.get('risk_level', 'SAFE')

        if risk == 'CRITICAL':
            message  = f"NGUY HIEM! {class_name_vi} rat gan - {distance:.1f}m"
            severity = 'critical'
        elif risk == 'DANGER':
            message  = f"CANH BAO! {class_name_vi} o {distance:.1f}m"
            severity = 'high'
        else:
            message  = f"Chu y {class_name_vi} o {distance:.1f}m"
            severity = 'medium'

        return {
            'type': 'collision_warning',
            'message': message,
            'severity': severity,
            'object_type': class_name_vi,
            'distance': distance,
            'ttc': ttc
        }
    
    def _handle_voice_warnings(self, results: Dict):
        """Log critical voice warnings (TTS hook placeholder)."""
        if not self.voice_enabled:
            return

        current_time = time.time()
        if current_time - self.last_warning_time < self.warning_cooldown:
            return

        critical_warnings = [
            w for w in results.get('warnings', [])
            if w.get('severity') == 'critical'
        ]

        if critical_warnings:
            message = critical_warnings[0].get('message', '')
            logger.warning(f"[VOICE] {message}")
            self.last_warning_time = current_time
    
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
