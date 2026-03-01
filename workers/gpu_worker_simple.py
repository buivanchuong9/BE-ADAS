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
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

# Load .env explicitly
load_dotenv(PROJECT_ROOT / ".env")

# Import FFmpeg utilities (SAFE)
from backend.core.ffmpeg_utils import FFmpegEncoder, get_video_info, FFMPEG

# Import FCW TTC-based warning system
from backend.perception.risk.fcw_ttc import (
    compute_fcw, FCWResult, FCW_SAFE, FCW_WARNING, FCW_COLLISION_RISK,
    FCW_STATE_VI, get_fcw_color_rgba
)

# Import CUDA preprocessing for zero-copy GpuMat reuse
from backend.perception.cuda_preprocess import CUDAPreprocessor, get_preprocessor

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


    # Model configurations per profile
    # Mỗi profile chứa đầy đủ các model cho tất cả pipeline:
    #   - obj_model:  Object detection (dashcam)
    #   - pose_model: Pose estimation (in_cabin driver monitor)
    #   - seg_model:  Segmentation (lane detection V11, optional)
    #   - ufld_model: Ultra Fast Lane Detection model (dashcam lane)
    MODEL_PROFILES = {
        'cloud': {
            'obj_model':  'backend/models/yolo11x.pt',
            'pose_model': 'backend/models/yolo11x-pose.pt',
            'seg_model':  'backend/models/yolo11x-seg.pt',
            'ufld_model': 'backend/models/ufld_tusimple.pth',
            'imgsz': 416,
            'conf': 0.5,
            'half': True,  # FP16 inference for speed
            'description': 'YOLOv11x + UFLD — high accuracy (server GPU)',
        },
        'fast': {
            # Fast profile: Smaller model + FP16 for ~2x speed when TensorRT unavailable
            'obj_model':  'backend/models/yolo11m.pt',  # Medium model (faster)
            'pose_model': 'backend/models/yolo11m-pose.pt',
            'seg_model':  'backend/models/yolo11m-seg.pt',
            'ufld_model': 'backend/models/ufld_tusimple.pth',
            'imgsz': 384,  # Smaller input
            'conf': 0.45,
            'half': True,  # FP16 inference
            'description': 'YOLOv11m + UFLD — balanced speed/accuracy',
        },
        'edge': {
            'obj_model':  'backend/models/yolov8n.pt',
            'pose_model': 'backend/models/yolov8n-pose.pt',
            'seg_model':  'backend/models/yolov8n-seg.pt',
            'ufld_model': 'backend/models/ufld_tusimple.pth',
            'imgsz': 320,
            'conf': 0.45,
            'half': True,
            'description': 'YOLOv8n + UFLD — real-time (edge deployment)',
        },
    }

    def __init__(
        self,
        worker_id: str,
        database_url: str,
        device: str = "cuda",
        model_profile: str = "cloud",
        enable_tensorrt: bool = True,
    ):
        self.worker_id = worker_id
        self.database_url = database_url
        self.device = device
        self.model_profile = model_profile
        self.enable_tensorrt = enable_tensorrt

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

        # GPU overlay blending is REQUIRED (no CPU fallback)
        self._cuda_overlay: bool = True

        # CUDA Preprocessor for zero-copy GpuMat reuse
        self._cuda_preprocessor: Optional[CUDAPreprocessor] = None

        # GPU FPS measurement
        self._gpu_frame_times: list = []
        self._gpu_fps: float = 0.0

        # TensorRT optimizer (lazy-init)
        self._trt_optimizer = None

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

        # PIL fonts for Vietnamese text rendering (có dấu)
        self._font_path = Path(__file__).parent.parent / "backend" / "assets" / "fonts" / "Roboto-Bold.ttf"
        self._pil_font_cache: Dict[int, ImageFont.FreeTypeFont] = {}

        prof = self.MODEL_PROFILES.get(model_profile, self.MODEL_PROFILES['cloud'])
        logger.info(
            f"[WORKER] {worker_id} initialized: device={device}, "
            f"profile={model_profile} ({prof['description']}), "
            f"tensorrt={'ON' if enable_tensorrt else 'OFF'}"
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
            from backend.perception.lane.lane_detector_ufld     import UFLDLaneDetector

            # --- Model profile selection ---
            prof = self.MODEL_PROFILES.get(self.model_profile, self.MODEL_PROFILES['cloud'])
            model_path = prof['obj_model']
            imgsz      = prof['imgsz']
            conf       = prof['conf']

            # --- TensorRT optimization (auto-export & cache) ---
            trt_model_path = model_path  # default: PyTorch .pt
            if self.enable_tensorrt and self.device == 'cuda':
                try:
                    from backend.perception.engine.tensorrt_optimizer import TensorRTOptimizer
                    if self._trt_optimizer is None:
                        self._trt_optimizer = TensorRTOptimizer()
                    engine_path = self._trt_optimizer.get_engine_path(model_path, imgsz)
                    if engine_path.exists():
                        trt_model_path = str(engine_path)
                        logger.info(f"[TRT] Using cached TensorRT engine: {engine_path.name}")
                    else:
                        exported = self._trt_optimizer.export_to_tensorrt(
                            model_path, imgsz=imgsz, half=True,
                        )
                        if exported:
                            trt_model_path = str(exported)
                            logger.info(f"[TRT] ✅ Auto-exported TensorRT engine")
                        else:
                            logger.info("[TRT] Export skipped — using PyTorch")
                except Exception as e:
                    logger.warning(f"[TRT] TensorRT init failed ({e}), using PyTorch")

            logger.info(
                f"[GPU] Loading pipeline 'dashcam': "
                f"model={Path(trt_model_path).name}, imgsz={imgsz}, "
                f"conf={conf}, profile={self.model_profile}"
            )
            
            # Initialize CUDA preprocessor for zero-copy GpuMat reuse
            if self.device == 'cuda' and self._cuda_preprocessor is None:
                self._cuda_preprocessor = CUDAPreprocessor(
                    enable_cuda=True,
                    use_streams=True,
                    device=self.device,
                )
                logger.info("[GPU] CUDA Preprocessor initialized (zero-copy GpuMat pool)")
            
            pipeline['object']   = ObjectDetectorV11(
                model_path=trt_model_path,
                device=self.device,
                conf_threshold=conf,
                imgsz=imgsz,
                half=prof.get('half', True),  # FP16 for ~2x speedup when TensorRT unavailable
            )
            # Lane detection: UFLD v2 (Ultra Fast Lane Detection)
            ufld_path = prof.get('ufld_model')
            if ufld_path and Path(ufld_path).exists():
                logger.info(f"[GPU] Lane detection: UFLD ({Path(ufld_path).name})")
            else:
                logger.info("[GPU] Lane detection: UFLD (untrained — no model file, will use random weights)")
                ufld_path = None
            pipeline['lane']     = UFLDLaneDetector(
                model_path=ufld_path,
                device=self.device,
                cuda_preprocessor=self._cuda_preprocessor,  # Zero-copy preprocessing
            )
            pipeline['distance'] = DistanceEstimator(focal_length=700.0, camera_height=1.2)
            
            # Store preprocessor in pipeline for frame processing
            pipeline['cuda_preprocessor'] = self._cuda_preprocessor

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

            # Enforce cv2.cuda.addWeighted — REQUIRED for GPU overlay
            _t = cv2.cuda_GpuMat()
            _t.upload(dummy)
            _t2 = cv2.cuda_GpuMat()
            _t2.upload(dummy)
            cv2.cuda.addWeighted(_t, 0.5, _t2, 0.5, 0)
            self._cuda_overlay = True
            cuda_count = cv2.cuda.getCudaEnabledDeviceCount()
            logger.info(
                f"[GPU] GPU overlay ENABLED — cv2.cuda.addWeighted verified — "
                f"CUDA devices={cuda_count}"
            )

            logger.info("[GPU] ✅ dashcam pipeline ready (YOLO + UFLD lane + GPU overlay)")

        elif video_type == 'in_cabin':
            from backend.perception.driver.driver_monitor_v11 import DriverMonitorV11

            # --- Model profile selection (in_cabin) ---
            prof = self.MODEL_PROFILES.get(self.model_profile, self.MODEL_PROFILES['cloud'])
            obj_model_path  = prof['obj_model']
            pose_model_path = prof['pose_model']

            logger.info(
                f"[GPU] Loading pipeline 'in_cabin': DriverMonitor "
                f"(obj={Path(obj_model_path).name}, pose={Path(pose_model_path).name}, "
                f"profile={self.model_profile})"
            )
            pipeline['driver'] = DriverMonitorV11(
                object_model_path=obj_model_path,
                pose_model_path=pose_model_path,
                device=self.device,
            )

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
                            f"speed={fps_proc:.1f}fps  "
                            f"gpu_overlay={self._gpu_fps:.1f}fps  "
                            f"ETA={remaining:.0f}s"
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

            # 4. Distance + FCW (Forward Collision Warning) based on TTC
            # Assume ego vehicle speed = 50 km/h for demo
            EGO_SPEED_KMH = 50.0
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
                    
                    # FCW using TTC-based risk assessment
                    fcw_result = self._assess_risk(dist_info, EGO_SPEED_KMH)
                    
                    obj_d = {
                        **obj,
                        'distance': dist_info,
                        'ttc': fcw_result.ttc,
                        'fcw_state': fcw_result.state,
                        'fcw_state_vi': fcw_result.state_vi,
                        'fcw_reason': fcw_result.reason,
                        'risk_level': fcw_result.state,  # For compatibility
                    }
                    distances.append(obj_d)
                    
                    # Trigger warning for WARNING or COLLISION RISK
                    if fcw_result.state in (FCW_WARNING, FCW_COLLISION_RISK):
                        results['warnings'].append(self._create_warning(obj_d))
                        
                results['objects_with_distance'] = distances
                results['ego_speed_kmh'] = EGO_SPEED_KMH  # For overlay display
            except Exception as e:
                logger.warning(f"[INFER] distance/fcw: {e}")
                results['objects_with_distance'] = []

            # 5. Lane departure warning (LDW) — Cảnh báo lệch làn
            offset_level = results.get('offset_level', 'SAFE')
            if offset_level == 'CRITICAL':
                results['warnings'].append({
                    'type': 'lane_departure',
                    'message': '⚠ LỆCH LÀN! Xe đang ra khỏi làn đường',
                    'severity': 'critical',
                })
            elif offset_level == 'WARNING':
                results['warnings'].append({
                    'type': 'lane_departure',
                    'message': 'Chú ý: Xe đang lệch làn đường',
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
    
    # ===================================================================
    # PIL FONT HELPER
    # ===================================================================

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Lấy PIL font (cached) để render tiếng Việt có dấu."""
        if size in self._pil_font_cache:
            return self._pil_font_cache[size]
        try:
            if self._font_path.exists():
                font = ImageFont.truetype(str(self._font_path), size)
            else:
                font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
        self._pil_font_cache[size] = font
        return font

    # ===================================================================
    # VIETNAMESE TRANSLATIONS — CÓ DẤU, CHUYÊN NGHIỆP
    # ===================================================================

    def _translate_class_name(self, class_name: str) -> str:
        """Dịch tên class YOLO sang tiếng Việt (có dấu, chuyên nghiệp)."""
        translations = {
            'person': 'Người đi bộ',
            'car': 'Ô tô',
            'truck': 'Xe tải',
            'bus': 'Xe buýt',
            'motorcycle': 'Xe máy',
            'bicycle': 'Xe đạp',
            'traffic light': 'Đèn giao thông',
            'stop sign': 'Biển dừng',
            'fire hydrant': 'Trụ cứu hoả',
            'dog': 'Chó',
            'cat': 'Mèo',
            'bird': 'Chim',
            'horse': 'Ngựa',
            'cow': 'Bò',
            'sheep': 'Cừu',
            'train': 'Tàu hoả',
            'airplane': 'Máy bay',
            'boat': 'Thuyền',
            'bench': 'Ghế dài',
            'backpack': 'Ba lô',
            'umbrella': 'Ô/Dù',
            'suitcase': 'Va li',
        }
        return translations.get(class_name.lower(), class_name.title())

    def _translate_driver_state(self, state: str) -> str:
        """Dịch trạng thái tài xế sang tiếng Việt (có dấu)."""
        states = {
            'normal': 'Bình thường',
            'drowsy': 'Buồn ngủ',
            'distracted': 'Mất tập trung',
            'looking_away': 'Nhìn ra ngoài',
            'unknown': 'Không xác định',
            'n/a': 'N/A',
        }
        return states.get(state, 'Không xác định')

    def _translate_risk_level(self, risk_level: str) -> str:
        """Dịch mức rủi ro (FCW state) sang tiếng Việt."""
        levels = {
            'SAFE': 'AN TOÀN',
            'WARNING': 'CẢNH BÁO',
            'COLLISION RISK': 'NGUY HIỂM',
            'CAUTION': 'CHÚ Ý',
            'DANGER': 'NGUY HIỂM',
            'CRITICAL': 'RẤT NGUY HIỂM',
        }
        return levels.get(risk_level, risk_level)

    # ===================================================================
    # COLOUR HELPERS
    # ===================================================================

    def _get_risk_color(self, risk_level: str) -> tuple:
        """Trả về màu BGR theo risk level (cho cv2)."""
        colors = {
            'SAFE': (0, 255, 0),
            'CAUTION': (0, 255, 255),
            'DANGER': (0, 165, 255),
            'CRITICAL': (0, 0, 255),
        }
        return colors.get(risk_level, (255, 255, 255))

    def _get_risk_color_rgba(self, risk_level: str) -> tuple:
        """Trả về màu RGBA theo FCW state (cho PIL)."""
        colors = {
            # New FCW states
            'SAFE':           (80, 255, 80, 230),    # Green
            'WARNING':        (255, 165, 0, 240),    # Orange  
            'COLLISION RISK': (255, 40, 40, 245),   # Red
            # Legacy states (for compatibility)
            'CAUTION':  (255, 220, 0, 235),
            'DANGER':   (255, 140, 0, 240),
            'CRITICAL': (255, 40, 40, 245),
        }
        return colors.get(risk_level, (200, 200, 200, 200))

    # ===================================================================
    # OVERLAY CHÍNH — PIL-BASED, TIẾNG VIỆT CÓ DẤU
    # Đề tài: "Phát triển ứng dụng cảnh báo thông minh cho ô tô"
    # ===================================================================

    def _draw_overlay(self, frame: np.ndarray, results: Dict) -> np.ndarray:
        """
        Vẽ overlay ADAS chuyên nghiệp — tiếng Việt có dấu (PIL rendering).

        Đề tài #138: "Phát triển ứng dụng cảnh báo thông minh cho ô tô
        chạy trên điện thoại Android"

        Sử dụng Pillow để render Unicode tiếng Việt chính xác.

        Hiển thị:
        - Làn đường (corridor xanh Tesla-style từ LaneDetectorV4)
        - Object bounding boxes + tên tiếng Việt có dấu
        - Khoảng cách & TTC cho từng vật thể
        - HUD panel thông tin chuyên nghiệp
        - Cảnh báo va chạm / lệch làn (PIL rendering)
        """
        lane_colored = results.get('lane_colored')
        h, w, _ = frame.shape

        # === 1. LÀN ĐƯỜNG (corridor xanh — GPU blending) ===
        if lane_colored is not None:
            if lane_colored.shape[:2] != (h, w):
                lane_colored = cv2.resize(lane_colored, (w, h))
            # GPU-accelerated alpha blend: lane corridor onto base frame
            if self._cuda_overlay:
                gpu_base = cv2.cuda_GpuMat()
                gpu_base.upload(frame)
                gpu_lane = cv2.cuda_GpuMat()
                gpu_lane.upload(lane_colored)
                gpu_blend = cv2.cuda.addWeighted(gpu_base, 0.4, gpu_lane, 0.6, 0)
                overlay = gpu_blend.download()
            else:
                overlay = cv2.addWeighted(frame, 0.4, lane_colored, 0.6, 0)
        else:
            overlay = frame.copy()

        # === 2. BOUNDING BOXES (cv2 — nhanh, không cần Unicode) ===
        for obj in results.get('objects_with_distance', []):
            bbox = obj.get('bbox')
            if not bbox:
                continue
            x1, y1, x2, y2 = map(int, bbox)
            risk_level = obj.get('risk_level', 'SAFE')
            color = self._get_risk_color(risk_level)
            thickness = 3 if risk_level in ['DANGER', 'CRITICAL'] else 2
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, thickness)

        # Biển báo (cv2 rectangle)
        for sign in results.get('traffic_signs', []):
            bbox = sign.get('bbox')
            if bbox:
                x1, y1, x2, y2 = map(int, bbox)
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 255), 2)

        # === 3. CHUYỂN SANG PIL ĐỂ VẼ VĂN BẢN TIẾNG VIỆT ===
        pil_base = Image.fromarray(
            cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)
        ).convert('RGBA')
        ui_layer = Image.new('RGBA', pil_base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(ui_layer, 'RGBA')

        # 3a. Object labels (tên tiếng Việt + khoảng cách + TTC)
        self._draw_object_labels_pil(draw, results)

        # 3b. Biển báo labels (tiếng Việt)
        for sign in results.get('traffic_signs', []):
            bbox = sign.get('bbox')
            if bbox:
                sx, sy = int(bbox[0]), int(bbox[1])
                sign_vn = self._translate_class_name(sign.get('class_name', ''))
                font_s = self._get_font(18)
                draw.text((sx + 1, sy - 21), sign_vn, font=font_s, fill=(0, 0, 0, 160))
                draw.text((sx, sy - 22), sign_vn, font=font_s, fill=(0, 255, 255, 240))

        # 3c. HUD Panel chuyên nghiệp (góc trên trái)
        self._draw_hud_panel_pil(draw, results, w, h)

        # 3d. Cảnh báo va chạm / lệch làn (top-center)
        self._draw_warnings_pil(draw, results, w)

        # === 4. COMPOSITE & TRẢ VỀ BGR (GPU resize if needed) ===
        result = Image.alpha_composite(pil_base, ui_layer)
        final = cv2.cvtColor(np.array(result.convert('RGB')), cv2.COLOR_RGB2BGR)

        # GPU FPS tracking
        self._gpu_frame_times.append(time.time())
        if len(self._gpu_frame_times) > 60:
            self._gpu_frame_times = self._gpu_frame_times[-60:]
        if len(self._gpu_frame_times) >= 2:
            dt = self._gpu_frame_times[-1] - self._gpu_frame_times[0]
            self._gpu_fps = (len(self._gpu_frame_times) - 1) / max(dt, 0.001)

        return final

    # ===================================================================
    # OBJECT LABELS (PIL)
    # ===================================================================

    def _draw_object_labels_pil(self, draw: ImageDraw.ImageDraw, results: Dict):
        """Vẽ nhãn vật thể tiếng Việt — tên, khoảng cách, TTC, FCW state."""
        font_main = self._get_font(20)
        font_sub  = self._get_font(16)

        for obj in results.get('objects_with_distance', []):
            bbox = obj.get('bbox')
            if not bbox:
                continue
            x1, y1 = int(bbox[0]), int(bbox[1])

            fcw_state = obj.get('fcw_state', obj.get('risk_level', 'SAFE'))
            color_rgba = self._get_risk_color_rgba(fcw_state)

            class_vn   = self._translate_class_name(obj.get('class_name', ''))
            confidence = obj.get('confidence', 0)
            distance   = obj.get('distance', 0)
            ttc        = obj.get('ttc', float('inf'))
            fcw_state_vi = obj.get('fcw_state_vi', self._translate_risk_level(fcw_state))

            # Main: "Ô tô 87%"
            main_text = f"{class_vn} {confidence:.0%}"
            # Sub:  "KC: 5.2m │ TTC: 1.4s │ CẢNH BÁO"
            if ttc < 100:
                sub_text = f"KC: {distance:.1f}m │ TTC: {ttc:.1f}s │ {fcw_state_vi}"
            else:
                sub_text = f"KC: {distance:.1f}m │ {fcw_state_vi}"

            # Measure for chip background
            mb = draw.textbbox((0, 0), main_text, font=font_main)
            sb = draw.textbbox((0, 0), sub_text,  font=font_sub)
            mw, mh = mb[2] - mb[0], mb[3] - mb[1]
            sw, sh = sb[2] - sb[0], sb[3] - sb[1]

            chip_w = max(mw, sw) + 14
            chip_h = mh + sh + 12
            cx, cy = x1, max(0, y1 - chip_h - 4)

            # Semi-transparent chip background
            is_warning = fcw_state in ('WARNING', 'COLLISION RISK', 'DANGER', 'CRITICAL')
            bg_alpha = 185 if is_warning else 150
            draw.rectangle([cx, cy, cx + chip_w, cy + chip_h],
                           fill=(10, 10, 10, bg_alpha))
            # Coloured left accent bar
            draw.rectangle([cx, cy, cx + 3, cy + chip_h], fill=color_rgba)

            # Text
            draw.text((cx + 8, cy + 3), main_text,
                      font=font_main, fill=(255, 255, 255, 245))
            draw.text((cx + 8, cy + 3 + mh + 2), sub_text,
                      font=font_sub, fill=color_rgba)

    # ===================================================================
    # HUD PANEL — "HỆ THỐNG CẢNH BÁO THÔNG MINH"
    # ===================================================================

    def _draw_hud_panel_pil(self, draw: ImageDraw.ImageDraw,
                            results: Dict, w: int, h: int):
        """
        HUD Panel chuyên nghiệp (góc trên trái) — tiếng Việt có dấu.
        Đúng đề tài: "Hệ thống cảnh báo thông minh cho ô tô"
        """
        objects   = results.get('objects_with_distance', [])
        # Filter warnings based on FCW state
        dangerous = [o for o in objects
                     if o.get('fcw_state', o.get('risk_level')) in 
                     ('WARNING', 'COLLISION RISK', 'CRITICAL', 'DANGER', 'CAUTION')]
        closest = None
        if dangerous:
            closest = min(dangerous, key=lambda o: o.get('distance', 9999))
        elif objects:
            closest = min(objects, key=lambda o: o.get('distance', 9999))

        font_header = self._get_font(18)
        font_body   = self._get_font(16)

        pad     = 10
        panel_w = 340
        line_h  = 23
        header_h = 30

        # Dynamic panel height
        num_lines = 4   # objects, lane, driver, signs
        if closest:
            num_lines += 1
            if closest.get('ttc', float('inf')) < 10:
                num_lines += 1
        panel_h = header_h + pad + num_lines * line_h + pad

        x0, y0 = pad, pad

        # Max risk → border colour
        max_risk = 'SAFE'
        if objects:
            risk_order = {'CRITICAL': 4, 'DANGER': 3, 'CAUTION': 2, 'SAFE': 1}
            max_risk = max(
                objects,
                key=lambda o: risk_order.get(o.get('risk_level', 'SAFE'), 1)
            ).get('risk_level', 'SAFE')
        border_rgba = self._get_risk_color_rgba(max_risk)

        # ── Panel background (semi-transparent) ──
        draw.rectangle([x0, y0, x0 + panel_w, y0 + panel_h],
                       fill=(10, 10, 15, 195))
        draw.rectangle([x0, y0, x0 + panel_w, y0 + panel_h],
                       outline=border_rgba, width=2)

        # ── Header bar ──
        draw.rectangle([x0, y0, x0 + panel_w, y0 + header_h],
                       fill=border_rgba)
        header_text = "HỆ THỐNG CẢNH BÁO THÔNG MINH"
        hb = draw.textbbox((0, 0), header_text, font=font_header)
        hw = hb[2] - hb[0]
        hx = x0 + (panel_w - hw) // 2
        # Shadow
        draw.text((hx + 1, y0 + 6 + 1), header_text,
                  font=font_header, fill=(0, 0, 0, 180))
        draw.text((hx, y0 + 6), header_text,
                  font=font_header, fill=(255, 255, 255, 255))

        # ── Body ──
        y_pos  = y0 + header_h + pad
        left_x = x0 + 12

        # 1. Vật thể phát hiện
        obj_count = len(objects)
        draw.text((left_x, y_pos),
                  f"Phát hiện vật thể: {obj_count}",
                  font=font_body, fill=(255, 255, 255, 225))
        y_pos += line_h

        # 2. Vật thể gần nhất
        if closest:
            name = self._translate_class_name(closest.get('class_name', ''))
            dist = closest.get('distance', 0)
            ttc  = closest.get('ttc', float('inf'))
            rlvl = closest.get('risk_level', 'SAFE')
            rc   = self._get_risk_color_rgba(rlvl)

            draw.text((left_x, y_pos),
                      f"Gần nhất: {name} — {dist:.1f}m",
                      font=font_body, fill=rc)
            y_pos += line_h

            if ttc < 10:
                risk_vn = self._translate_risk_level(rlvl)
                draw.text((left_x, y_pos),
                          f"TTC: {ttc:.1f}s  [{risk_vn}]",
                          font=font_body, fill=rc)
                y_pos += line_h

        # 3. Làn đường
        has_lane = results.get('has_lane', False)
        if has_lane:
            lane_text  = "Làn đường: Đã phát hiện ✓"
            lane_color = (80, 255, 80, 235)
        else:
            lane_text  = "Làn đường: Không rõ"
            lane_color = (255, 165, 0, 225)
        draw.text((left_x, y_pos), lane_text,
                  font=font_body, fill=lane_color)
        y_pos += line_h

        # 4. Tài xế
        driver_state = results.get('driver_state', 'unknown')
        state_vn = self._translate_driver_state(driver_state)
        if driver_state == 'normal':
            d_color = (80, 255, 80, 235)
        elif driver_state in ('n/a', 'unknown'):
            d_color = (180, 180, 180, 200)
        else:
            d_color = (255, 80, 80, 240)
        draw.text((left_x, y_pos),
                  f"Tài xế: {state_vn}",
                  font=font_body, fill=d_color)
        y_pos += line_h

        # 5. Biển báo
        sign_count = len(results.get('traffic_signs', []))
        if sign_count:
            draw.text((left_x, y_pos),
                      f"Biển báo: {sign_count}",
                      font=font_body, fill=(0, 255, 255, 225))

    # ===================================================================
    # WARNING BANNERS (PIL) — CẢNH BÁO CHUYÊN NGHIỆP
    # ===================================================================

    def _draw_warnings_pil(self, draw: ImageDraw.ImageDraw,
                           results: Dict, w: int):
        """Vẽ cảnh báo chuyên nghiệp (top-center) — tiếng Việt có dấu."""
        warnings = results.get('warnings', [])
        if not warnings:
            return

        severity_order = {'critical': 0, 'high': 1, 'medium': 2}
        warnings = sorted(
            warnings,
            key=lambda x: severity_order.get(x.get('severity', 'medium'), 2)
        )

        frame_idx = results.get('frame_idx', 0)
        flash_on  = (frame_idx // 8) % 2 == 0

        y_start = 55
        drawn   = 0
        for warning in warnings[:3]:
            msg      = warning.get('message', '')
            severity = warning.get('severity', 'medium')

            if severity == 'critical':
                bg_color   = (200, 0, 0, 170)
                border_col = (255, 40, 40, 240)
                text_color = (255, 255, 255, 255)
                font_size  = 28
                if not flash_on:
                    continue
            elif severity == 'high':
                bg_color   = (180, 60, 0, 150)
                border_col = (255, 140, 0, 230)
                text_color = (255, 255, 255, 250)
                font_size  = 24
            else:
                bg_color   = (0, 100, 100, 130)
                border_col = (0, 220, 220, 210)
                text_color = (220, 255, 255, 245)
                font_size  = 22

            font = self._get_font(font_size)
            tb = draw.textbbox((0, 0), msg, font=font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]

            pad_x, pad_y = 24, 10
            y_pos = y_start + drawn * (th + pad_y * 2 + 12)

            bx1 = (w - tw) // 2 - pad_x
            bx2 = (w + tw) // 2 + pad_x
            by1 = y_pos - pad_y
            by2 = y_pos + th + pad_y

            # Semi-transparent background
            draw.rectangle([bx1, by1, bx2, by2], fill=bg_color)
            draw.rectangle([bx1, by1, bx2, by2],
                           outline=border_col, width=2)

            # Shadow + main text
            tx = (w - tw) // 2
            draw.text((tx + 1, y_pos + 1), msg,
                      font=font, fill=(0, 0, 0, 170))
            draw.text((tx, y_pos), msg,
                      font=font, fill=text_color)
            drawn += 1

    # ===================================================================
    # RISK ASSESSMENT
    # ===================================================================

    def _assess_risk(self, distance: float, ego_speed_kmh: float = 50.0) -> FCWResult:
        """
        Đánh giá rủi ro va chạm dựa trên TTC (Time-To-Collision).
        
        FCW (Forward Collision Warning) principle:
        - TTC = distance / relative_speed
        - TTC < 1.0s → COLLISION RISK (NGUY HIỂM)
        - 1.0 ≤ TTC < 2.0s → WARNING (CẢNH BÁO)  
        - TTC ≥ 2.0s → SAFE (AN TOÀN)
        
        Args:
            distance: Khoảng cách đến vật thể (meters)
            ego_speed_kmh: Tốc độ xe đang chạy (km/h), default 50 km/h
            
        Returns:
            FCWResult với TTC, state, và reason
        """
        return compute_fcw(distance, ego_speed_kmh)

    # ===================================================================
    # TẠO CẢNH BÁO VA CHẠM — TIẾNG VIỆT CÓ DẤU
    # ===================================================================

    def _create_warning(self, obj_with_distance: Dict) -> Dict:
        """
        Tạo cảnh báo FCW tiếng Việt chuyên nghiệp (có dấu).
        Bao gồm lý do giải thích TẠI SAO cảnh báo được kích hoạt.
        """
        class_name_vi = self._translate_class_name(
            obj_with_distance.get('class_name', ''))
        distance = obj_with_distance.get('distance', 0)
        ttc      = obj_with_distance.get('ttc', float('inf'))
        fcw_state = obj_with_distance.get('fcw_state', 'SAFE')
        fcw_reason = obj_with_distance.get('fcw_reason', '')

        # Severity mapping based on FCW state
        if fcw_state == FCW_COLLISION_RISK:
            message  = f"⚠ NGUY HIỂM! {class_name_vi} — TTC={ttc:.1f}s"
            severity = 'critical'
        elif fcw_state == FCW_WARNING:
            message  = f"CẢNH BÁO! {class_name_vi} — TTC={ttc:.1f}s"
            severity = 'high'
        else:
            message  = f"Chú ý: {class_name_vi} — KC={distance:.1f}m"
            severity = 'medium'

        return {
            'type': 'fcw_warning',  # Forward Collision Warning
            'message': message,
            'severity': severity,
            'object_type': class_name_vi,
            'distance': distance,
            'ttc': ttc,
            'fcw_state': fcw_state,
            'fcw_state_vi': FCW_STATE_VI.get(fcw_state, fcw_state),
            'reason': fcw_reason,  # Explanation WHY this warning was triggered
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
    parser = argparse.ArgumentParser(
        description='ADAS GPU Worker — Production Video Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Model Profiles:
  cloud   YOLOv11x imgsz=416  — high accuracy, server GPU (A30/A100)
  edge    YOLOv8n  imgsz=320  — real-time, edge devices (Jetson/mobile)

Examples:
  # Default cloud profile with TensorRT
  python3 workers/gpu_worker_simple.py --worker-id w0 --device cuda

  # Edge profile for lightweight inference
  python3 workers/gpu_worker_simple.py --profile edge --device cuda

  # Disable TensorRT (use PyTorch only)
  python3 workers/gpu_worker_simple.py --no-tensorrt

  # Benchmark TensorRT vs PyTorch
  python3 workers/gpu_worker_simple.py --benchmark
        """
    )
    parser.add_argument('--worker-id', default=f"worker_{os.getpid()}")
    parser.add_argument('--device', default='cuda', choices=['cuda', 'cpu'])
    parser.add_argument('--database-url', default=os.getenv('DATABASE_URL'))
    parser.add_argument(
        '--profile', default='cloud', choices=['cloud', 'edge'],
        help='Model profile: cloud (YOLOv11x) or edge (YOLOv8n)'
    )
    parser.add_argument(
        '--no-tensorrt', action='store_true',
        help='Disable TensorRT optimization (use PyTorch only)'
    )
    parser.add_argument(
        '--benchmark', action='store_true',
        help='Run TensorRT benchmark and exit'
    )
    
    args = parser.parse_args()
    
    # Benchmark mode
    if args.benchmark:
        from backend.perception.engine.tensorrt_optimizer import TensorRTOptimizer
        opt = TensorRTOptimizer()
        prof = SimpleGPUWorker.MODEL_PROFILES.get(args.profile, SimpleGPUWorker.MODEL_PROFILES['cloud'])
        logger.info(f"[BENCH] Benchmarking profile '{args.profile}': {prof['description']}")
        opt.benchmark(prof['obj_model'], prof['imgsz'])
        return

    if not args.database_url:
        logger.error("ERROR: DATABASE_URL required. Check your .env file.")
        sys.exit(1)
    
    # Create worker
    worker = SimpleGPUWorker(
        worker_id=args.worker_id,
        database_url=args.database_url,
        device=args.device,
        model_profile=args.profile,
        enable_tensorrt=not args.no_tensorrt,
    )
    
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")


if __name__ == '__main__':
    main()
