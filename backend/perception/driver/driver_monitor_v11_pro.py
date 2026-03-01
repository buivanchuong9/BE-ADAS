import cv2
import numpy as np
import torch
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import logging
from collections import deque
import math
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Try to import MediaPipe
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
    logger.info("✅ MediaPipe available for Face Mesh")
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    logger.warning("⚠️ MediaPipe not installed - Face Mesh disabled. Install with: pip install mediapipe")


class DriverMonitorV11Pro:
    """
    Hệ thống giám sát tài xế PRO - Object Detection + Pose + Face Mesh + Head Pose Analysis.
    
    Architecture:
        Frame → YOLO Object → YOLO Pose → MediaPipe Face Mesh → Head Pose → Behavior Analysis → Risk Score
    
    Tính năng NÂNG CAO:
    - MediaPipe Face Mesh (468 landmarks) với EAR & MAR
    - Eye Aspect Ratio (EAR) để phát hiện mắt nhắm
    - Đếm số lần chớp mắt (Blink Counter)
    - PERCLOS (% mắt nhắm) để phát hiện buồn ngủ
    - Seatbelt Detection - Phát hiện dây an toàn
    - Phát hiện điện thoại, ly/chai nước với temporal smoothing
    - Head Pose Estimation (yaw/pitch/roll) từ facial keypoints
    - Attention Score (0-100) - đánh giá mức tập trung
    - Distraction Level Tracking (LOW → CRITICAL)
    - Vietnamese warnings với severity levels
    """
    
    # ==================== CONFIGURATION ====================
    
    # COCO Class IDs
    OBJECT_CLASSES = {
        67: 'điện thoại',  # cell phone
        41: 'cốc',         # cup
        39: 'chai',        # bottle
    }
    
    # Detection confidence thresholds - NHẠY HƠN
    OBJ_CONF_THRESHOLD = 0.25     # Lower = more sensitive (was implicit at model default)
    POSE_CONF_THRESHOLD = 0.3    # Pose keypoint confidence
    
    # Distance thresholds (pixels) - adaptive based on face size
    PHONE_DISTANCE_THRESHOLD = 250   # Increased for better detection
    DRINK_DISTANCE_THRESHOLD = 220   # Increased for better detection
    SMOKE_DISTANCE_THRESHOLD = 120   # hand near mouth
    
    # Head Pose thresholds (degrees)
    YAW_THRESHOLD = 25           # Looking left/right (was 30, now more sensitive)
    YAW_SEVERE = 40              # Severely looking away
    YAW_EXTREME = 60             # Looking at backseat
    PITCH_THRESHOLD = 15         # Head tilt up/down (was 20, now more sensitive)
    PITCH_SEVERE = 30            # Severely tilted
    PITCH_EXTREME = 45           # Looking at floor/ceiling (ngủ gục)
    ROLL_THRESHOLD = 20          # Head roll (lateral tilt)
    
    # ==================== PRIORITY MATRIX ====================
    # P0: Nguy hiểm tức thời - Còi chói tai, ghi đè tất cả
    # P1: Rủi ro cao - Giọng nói gắt
    # P2: Cảnh báo sớm - Ping nhẹ + text
    # P3: Vi phạm thụ động - Icon nhấp nháy
    
    PRIORITY_LEVELS = {
        'P0_CRITICAL': {
            'level': 0,
            'name': 'NGUY HIỂM TỨC THỜI',
            'color': (255, 0, 255),    # Magenta
            'sound': 'alarm_critical', # Bíp bíp liên tục
            'behaviors': ['drowsy_severe', 'pitch_extreme', 'sleeping'],
        },
        'P1_HIGH': {
            'level': 1,
            'name': 'RỦI RO CAO',
            'color': (0, 0, 255),      # Red
            'sound': 'voice_warning',  # "Yêu cầu tập trung lái xe!"
            'behaviors': ['phone', 'yaw_extreme', 'texting'],
        },
        'P2_MEDIUM': {
            'level': 2,
            'name': 'CẢNH BÁO SỚM',
            'color': (0, 165, 255),    # Orange
            'sound': 'ping_soft',      # Ping nhẹ
            'behaviors': ['yawning', 'drinking', 'eating', 'smoking'],
        },
        'P3_LOW': {
            'level': 3,
            'name': 'VI PHẠM THỤ ĐỘNG',
            'color': (0, 255, 255),    # Yellow
            'sound': 'none',           # Chỉ icon nhấp nháy
            'behaviors': ['no_seatbelt'],
        },
    }
    
    # ==================== TIME BUFFER CONFIGURATION ====================
    # Sliding Window để chống báo động giả
    # FPS = 30, mỗi buffer chứa N frames
    
    TIME_BUFFER_CONFIG = {
        # Ngủ gục - CỰC KỲ NGUY HIỂM, không cần đợi lâu
        'drowsy': {
            'window_size': 30,       # 1 giây @ 30fps
            'trigger_ratio': 0.67,   # 20/30 frames (67%) mắt nhắm = ngủ gục
            'cooldown_frames': 90,   # 3 giây cooldown
        },
        # Điện thoại - Ưu tiên cao
        'phone': {
            'window_size': 45,       # 1.5 giây
            'trigger_ratio': 0.75,   # 34/45 frames = đang dùng điện thoại
            'cooldown_frames': 60,
        },
        # Uống nước - Có thể bỏ qua nếu ngắn
        'drinking': {
            'window_size': 30,       # 1 giây
            'trigger_ratio': 0.67,   # 20/30 frames
            'cooldown_frames': 45,
        },
        # Hút thuốc - Cần xác nhận vì dễ nhầm
        'smoking': {
            'window_size': 60,       # 2 giây
            'trigger_ratio': 0.6,    # 36/60 frames
            'cooldown_frames': 90,
        },
        # Nhìn sang - Cho phép liếc gương chiếu hậu
        'looking_away': {
            'window_size': 45,       # 1.5 giây
            'trigger_ratio': 0.8,    # 36/45 frames = không phải liếc gương
            'cooldown_frames': 30,
        },
        # Ngáp - Báo hiệu mệt mỏi
        'yawning': {
            'window_size': 45,       # 1.5 giây
            'trigger_ratio': 0.5,    # 22/45 frames
            'cooldown_frames': 120,  # 4 giây (không cần cảnh báo liên tục)
        },
        # Dây an toàn - Chờ xe khởi hành
        'seatbelt': {
            'window_size': 90,       # 3 giây
            'trigger_ratio': 0.9,    # 81/90 frames không có dây
            'cooldown_frames': 300,  # 10 giây
        },
        # Chớp mắt (để phân biệt với ngủ gục)
        'blink': {
            'window_size': 10,       # 0.33 giây - chớp mắt bình thường
            'trigger_ratio': 0.3,    # 3/10 frames
            'cooldown_frames': 5,
        },
    }
    
    # ===== SEATBELT DETECTION Configuration =====
    # COCO Pose keypoints for seatbelt region
    # 5: left_shoulder, 6: right_shoulder, 11: left_hip, 12: right_hip
    SEATBELT_MIN_EDGE_RATIO = 0.15   # Min ratio of diagonal edges to detect seatbelt
    SEATBELT_CANNY_LOW = 50          # Canny edge detection thresholds
    SEATBELT_CANNY_HIGH = 150
    SEATBELT_HOUGH_THRESHOLD = 30    # Hough line detection threshold
    SEATBELT_CONFIRM_FRAMES = 30     # 1 second to confirm no seatbelt
    
    # ===== EYE ASPECT RATIO (EAR) Configuration =====
    # MediaPipe Face Mesh eye landmark indices
    # Left eye: 6 points for EAR calculation
    LEFT_EYE_IDX = [362, 385, 387, 263, 373, 380]
    # Right eye: 6 points for EAR calculation  
    RIGHT_EYE_IDX = [33, 160, 158, 133, 153, 144]
    
    # Mouth landmarks for MAR (Mouth Aspect Ratio)
    MOUTH_IDX = [61, 291, 0, 17, 269, 405]
    
    # EAR thresholds - REALISTIC DETECTION
    EAR_THRESHOLD = 0.21         # Below this = eyes closed
    EAR_DROWSY_THRESHOLD = 0.20  # Below this for extended time = drowsy/lờ đờ
    EAR_CONSEC_FRAMES = 3        # Consecutive frames for normal blink
    EAR_DROWSY_TIME = 2.0        # Seconds with EAR < 0.20 = lờ đờ
    
    # BLINK DURATION thresholds (realistic)
    # Normal blink: 100-400ms
    # Long blink: 400-800ms (suspicious)
    # Microsleep: > 800ms (dangerous!)
    BLINK_NORMAL_MAX_MS = 400    # Normal blink up to 400ms
    BLINK_LONG_MS = 800          # Long blink = drowsy indicator
    MICROSLEEP_MS = 800          # > 800ms = microsleep warning!
    MICROSLEEP_DANGER_MS = 1500  # > 1.5s = critical danger
    
    # PERCLOS threshold (% of time eyes closed in 1 minute)
    PERCLOS_THRESHOLD = 0.15     # 15% = drowsy
    PERCLOS_DANGER = 0.25        # 25% = severe drowsiness
    
    # MAR thresholds for yawning - MORE REALISTIC
    MAR_THRESHOLD = 0.55         # Above this = mouth wide open (yawn candidate)
    MAR_YAWN_CONFIRM = 0.65      # Above this for extended time = confirmed yawn
    YAWN_FRAMES = 20             # ~0.67s at 30fps to confirm yawn
    YAWN_DURATION_MS = 2000      # Typical yawn lasts 2-4 seconds
    
    # STROKE DETECTION - Facial Asymmetry
    # If one side of face drops significantly vs other = possible stroke
    STROKE_EAR_ASYMMETRY = 0.15  # |left_ear - right_ear| > 0.15 = asymmetry
    STROKE_MOUTH_DROOP = 0.2    # One side of mouth significantly lower
    STROKE_CONFIRM_FRAMES = 60  # 2 seconds to confirm (not just expression)
    
    # Temporal thresholds (frames @ 30fps)
    LOOKING_AWAY_FRAMES = 45     # 1.5 seconds
    DROWSY_FRAMES = 60           # 2 seconds
    PHONE_CONFIRM_FRAMES = 10    # 0.33 seconds
    DRINK_CONFIRM_FRAMES = 8     # 0.27 seconds
    
    # Attention Score configuration
    ATTENTION_WEIGHTS = {
        'head_forward': 30,      # Looking forward (yaw < threshold)
        'head_level': 15,        # Head not tilted (pitch < threshold)
        'eyes_open': 35,         # Eyes open (EAR > threshold)
        'no_objects': 20,        # Not using phone/drinking
    }
    
    # Distraction levels with score ranges
    DISTRACTION_LEVELS = {
        'LOW': (80, 100),
        'MEDIUM': (60, 79),
        'HIGH': (40, 59),
        'CRITICAL': (0, 39),
    }
    
    # Warning colors (BGR)
    COLORS = {
        'SAFE': (0, 255, 0),       # Green
        'WARNING': (0, 165, 255),  # Orange
        'DANGER': (0, 0, 255),     # Red
        'CRITICAL': (255, 0, 255), # Magenta
    }
    
    # ==================== INITIALIZATION ====================
    
    def __init__(
        self,
        object_model_path: str = "backend/models/yolo11x.pt",
        pose_model_path: str = "backend/models/yolo11x-pose.pt",
        device: str = "cuda",
        enable_attention_score: bool = True,
        enable_head_pose: bool = True,
        enable_face_mesh: bool = True,
    ):
        """
        Khởi tạo Driver Monitor PRO.
        
        Args:
            object_model_path: Model phát hiện vật thể YOLO
            pose_model_path: Model phát hiện pose YOLO
            device: "cuda" hoặc "cpu"
            enable_attention_score: Bật tính năng Attention Score
            enable_head_pose: Bật tính năng Head Pose Estimation
            enable_face_mesh: Bật MediaPipe Face Mesh (EAR, Blink detection)
        """
        self.device = device
        self.enable_attention = enable_attention_score
        self.enable_head_pose = enable_head_pose
        self.enable_face_mesh = enable_face_mesh and MEDIAPIPE_AVAILABLE
        
        # State tracking
        self.frame_count = 0
        self.last_process_time = 0
        self.current_attention_score = 100
        self.current_distraction_level = 'LOW'
        
        # EAR and Blink tracking
        self.current_ear = 0.3
        self.blink_counter = 0
        self.total_blinks = 0
        self.eyes_closed_frames = 0
        self.eyes_closed_start_time = None
        self.perclos_buffer = deque(maxlen=1800)  # 60 seconds @ 30fps
        self.yawn_counter = 0
        self.current_mar = 0.0
        
        # ===== NEW: Advanced Drowsiness Detection =====
        # Microsleep tracking (blink duration > 800ms)
        self.blink_start_time = None  # When current blink started
        self.last_blink_duration_ms = 0  # Duration of last completed blink
        self.microsleep_detected = False
        self.microsleep_count = 0
        self.long_blink_count = 0  # Blinks > 400ms but < 800ms
        
        # Drowsy eyes tracking (EAR < 0.2 continuously)
        self.drowsy_eyes_start_time = None  # When EAR dropped below threshold
        self.drowsy_eyes_detected = False  # Mắt lờ đờ
        self.drowsy_eyes_duration = 0.0
        
        # Yawn tracking (improved)
        self.yawn_start_time = None
        self.yawns_in_last_5min = deque(maxlen=10)  # Track yawn timestamps
        self.current_yawn_duration = 0.0
        
        # Stroke detection (facial asymmetry)
        self.ear_asymmetry_frames = 0
        self.mouth_asymmetry_frames = 0
        self.stroke_warning_active = False
        
        # Seatbelt tracking - REALISTIC: Start with unknown state
        self.seatbelt_detected = False  # Don't assume - wait for actual detection
        self.seatbelt_status = 'unknown'  # 'wearing', 'not_wearing', 'checking', 'unknown'
        self.seatbelt_warning_sent = False
        self.no_seatbelt_frames = 0
        
        # Reference head pose (calibrated when driver looks forward)
        self.reference_pose = None
        self.calibration_frames = []
        self.is_calibrated = False
        
        logger.info(f"🚗 Khởi tạo Driver Monitor V11 PRO ({device})")
        logger.info(f"   ├─ Attention Score: {'✅' if enable_attention_score else '❌'}")
        logger.info(f"   ├─ Head Pose: {'✅' if enable_head_pose else '❌'}")
        logger.info(f"   └─ Face Mesh (EAR/Blink): {'✅' if self.enable_face_mesh else '❌'}")
        
        # Check CUDA
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("⚠️ CUDA không khả dụng, chuyển sang CPU")
            self.device = "cpu"
        
        # GPU Optimization
        if self.device == "cuda":
            torch.set_float32_matmul_precision('high')
            torch.backends.cudnn.benchmark = True
            logger.info("🚀 GPU Optimization: Enabled")
        
        # Load models
        self._load_models(object_model_path, pose_model_path)
        
        # Initialize MediaPipe Face Mesh
        self._init_face_mesh()
        
        # Load Vietnamese font
        self._load_font()
        
        # Initialize temporal buffers
        self._init_buffers()
        
        # ===== PERFORMANCE: Thread pool for parallel YOLO inference =====
        self._infer_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='drv_yolo')
        
        # ===== PERFORMANCE: Inference stride — skip YOLO every N frames =====
        self.INFER_STRIDE = 2  # Run YOLO every 2 frames (2x speed boost)
        self._cached_objects = []
        self._cached_pose = None
        
        # ===== PERFORMANCE: Overlay skip — full PIL render every N frames =====
        self.OVERLAY_STRIDE = 3  # Full dashboard render every 3 frames
        self._cached_dashboard_frame = None
        self._cached_overlay_results = None
        
        # ===== PERFORMANCE: FP16 inference for YOLO models =====
        self.use_fp16 = self.device == 'cuda' and torch.cuda.is_available()
        if self.use_fp16:
            logger.info("🚀 FP16 enabled (half=True in predict calls)")
        
        # ===== PERFORMANCE: Downscale for face mesh (CPU bound) =====
        self.FACE_MESH_SCALE = 0.5  # Process face mesh at half resolution
        
        logger.info("✅ Driver Monitor V11 PRO khởi tạo thành công!")
        logger.info(f"   ├─ Inference Stride: {self.INFER_STRIDE}x")
        logger.info(f"   ├─ Overlay Stride: {self.OVERLAY_STRIDE}x")
        logger.info(f"   └─ Parallel YOLO: ✅ (2 threads)")
    
    def _load_models(self, object_path: str, pose_path: str):
        """Load YOLO models."""
        try:
            from ultralytics import YOLO
            
            # Object detection
            if not Path(object_path).exists():
                raise FileNotFoundError(f"❌ Không tìm thấy: {object_path}")
            
            self.object_model = YOLO(object_path)
            self.object_model.overrides['conf'] = 0.4
            self.object_model.overrides['verbose'] = False
            logger.info(f"📦 Object model: {object_path}")
            
            # Pose estimation
            if not Path(pose_path).exists():
                raise FileNotFoundError(f"❌ Không tìm thấy: {pose_path}")
            
            self.pose_model = YOLO(pose_path)
            self.pose_model.overrides['conf'] = 0.5
            self.pose_model.overrides['verbose'] = False
            logger.info(f"📦 Pose model: {pose_path}")
            
        except ImportError:
            raise ImportError("❌ Chưa cài ultralytics: pip install ultralytics")
    
    def _load_font(self):
        """Load Vietnamese font for overlay."""
        try:
            font_path = "backend/assets/fonts/Roboto-Bold.ttf"
            self.font_large = ImageFont.truetype(font_path, 32)
            self.font_medium = ImageFont.truetype(font_path, 24)
            self.font_small = ImageFont.truetype(font_path, 18)
            logger.info(f"✅ Font tiếng Việt: {font_path}")
        except Exception as e:
            logger.warning(f"⚠️ Không load được font: {e}")
            self.font_large = None
            self.font_medium = None
            self.font_small = None

    def _put_text_pil(self, frame: np.ndarray, text: str, position: tuple,
                      color: tuple = (255, 255, 255), font=None) -> np.ndarray:
        """Draw Vietnamese/Unicode text on frame using PIL.
        
        cv2.putText cannot render Unicode (Vietnamese shows as ???).
        This method converts to PIL, draws text, converts back.
        
        Args:
            frame: BGR numpy array
            text: Text to draw (supports Vietnamese/Unicode)
            position: (x, y) top-left position
            color: BGR color tuple
            font: PIL ImageFont (default: self.font_medium)
        """
        if font is None:
            font = self.font_medium
        if font is None:
            # Fallback to cv2 if no font loaded
            cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            return frame
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        draw = ImageDraw.Draw(pil_img)
        rgb_color = (color[2], color[1], color[0])
        draw.text(position, text, fill=rgb_color, font=font)
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def _draw_texts_pil_batch(self, frame: np.ndarray, texts: list) -> np.ndarray:
        """Draw multiple Vietnamese texts on frame in ONE PIL conversion (efficient).
        
        Args:
            frame: BGR numpy array
            texts: list of (text, (x, y), bgr_color, font) tuples
        """
        if not texts:
            return frame
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        draw = ImageDraw.Draw(pil_img)
        for text, pos, bgr_color, font in texts:
            if font is None:
                font = self.font_medium
            if font is None:
                continue
            rgb_color = (bgr_color[2], bgr_color[1], bgr_color[0])
            draw.text(pos, text, fill=rgb_color, font=font)
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    
    def _init_face_mesh(self):
        """Initialize MediaPipe Face Mesh for EAR detection."""
        self.face_mesh = None
        self.mp_face_mesh = None
        self.mp_drawing = None
        self.mp_drawing_styles = None
        
        if not self.enable_face_mesh:
            logger.info("⏭️ Face Mesh disabled")
            return
        
        if not MEDIAPIPE_AVAILABLE:
            logger.warning("⚠️ MediaPipe not available - Face Mesh disabled")
            self.enable_face_mesh = False
            return
        
        try:
            self.mp_face_mesh = mp.solutions.face_mesh
            self.mp_drawing = mp.solutions.drawing_utils
            self.mp_drawing_styles = mp.solutions.drawing_styles
            
            # Initialize Face Mesh — try with refinement first, fallback without
            try:
                self.face_mesh = self.mp_face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,  # Bật iris landmarks
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5
                )
                logger.info("✅ MediaPipe Face Mesh initialized (478 landmarks, refined)")
            except Exception as e_refined:
                logger.warning(f"⚠️ Face Mesh refined failed ({e_refined}), trying without refinement...")
                try:
                    self.face_mesh = self.mp_face_mesh.FaceMesh(
                        max_num_faces=1,
                        refine_landmarks=False,  # Fallback: no iris
                        min_detection_confidence=0.5,
                        min_tracking_confidence=0.5
                    )
                    logger.info("✅ MediaPipe Face Mesh initialized (468 landmarks, basic)")
                except Exception as e_basic:
                    logger.error(f"❌ Face Mesh basic mode also failed: {e_basic}")
                    raise e_basic
        except Exception as e:
            logger.error(f"❌ Failed to init Face Mesh: {e}")
            # Check if it's a protobuf error
            if "protobuf" in str(e).lower() or "parse" in str(e).lower():
                logger.error("💡 Hint: Try reinstalling mediapipe and protobuf:")
                logger.error("   pip uninstall mediapipe protobuf -y")
                logger.error("   pip install mediapipe==0.10.30 'protobuf>=3.20.0,<4.0.0'")
            self.enable_face_mesh = False
    
    def _init_buffers(self):
        """Initialize temporal smoothing buffers with proper sliding windows."""
        # ===== BEHAVIOR BUFFERS - Sized by TIME_BUFFER_CONFIG =====
        cfg = self.TIME_BUFFER_CONFIG
        
        # Phone detection buffer
        self.phone_buffer = deque(maxlen=cfg['phone']['window_size'])
        self.phone_cooldown = 0
        
        # Drinking detection buffer
        self.drink_buffer = deque(maxlen=cfg['drinking']['window_size'])
        self.drink_cooldown = 0
        
        # Smoking detection buffer
        self.smoke_buffer = deque(maxlen=cfg['smoking']['window_size'])
        self.smoke_cooldown = 0
        
        # Drowsy/eye closure buffer
        self.eye_closure_buffer = deque(maxlen=cfg['drowsy']['window_size'])
        self.drowsy_cooldown = 0
        
        # Looking away buffer
        self.looking_away_buffer = deque(maxlen=cfg['looking_away']['window_size'])
        self.looking_away_cooldown = 0
        
        # Yawning buffer
        self.yawn_buffer = deque(maxlen=cfg['yawning']['window_size'])
        self.yawn_cooldown = 0
        
        # Seatbelt buffer
        self.seatbelt_buffer = deque(maxlen=cfg['seatbelt']['window_size'])
        self.seatbelt_cooldown = 0
        
        # Blink buffer (để phân biệt chớp mắt vs ngủ gục)
        self.blink_buffer = deque(maxlen=cfg['blink']['window_size'])
        
        # ===== HEAD POSE BUFFERS =====
        self.yaw_buffer = deque(maxlen=30)
        self.pitch_buffer = deque(maxlen=30)
        self.roll_buffer = deque(maxlen=30)
        
        # Drowsiness head indicators (for check_drowsiness)
        self.head_nod_buffer = deque(maxlen=60)
        self.head_tilt_buffer = deque(maxlen=60)
        
        # ===== EAR/MAR BUFFERS =====
        self.ear_buffer = deque(maxlen=30)
        self.mar_buffer = deque(maxlen=30)
        
        # ===== ATTENTION & TRACKING =====
        self.attention_history = deque(maxlen=90)
        self.looking_away_counter = 0
        
        # Performance tracking
        self.fps_buffer = deque(maxlen=30)
        
        # ===== PRIORITY & WARNING STATE =====
        self.active_warnings = []          # List of active warnings
        self.warning_history = deque(maxlen=300)  # 10 seconds of warnings
        self.last_warning_priority = 99    # 99 = no warning (lower = higher priority)
        self.last_warning_time = 0
        
        # ===== WARNING STABILIZATION (anti-flicker) =====
        self._stable_warnings = {}         # {key: {'message': str, 'last_seen': float}}
        self.WARNING_PERSIST_TIME = 2.0    # Keep warning displayed for at least 2 seconds
        
        # ===== DETECTION BOUNDING BOXES =====
        self.detection_boxes = {}          # Store bounding boxes for current frame
    
    def _check_buffer_trigger(self, buffer: deque, behavior: str) -> Tuple[bool, float]:
        """
        Check if buffer exceeds trigger threshold (sliding window logic).
        
        Args:
            buffer: The deque buffer to check
            behavior: Behavior type from TIME_BUFFER_CONFIG
            
        Returns:
            (triggered, ratio) - Whether triggered and the actual ratio
        """
        cfg = self.TIME_BUFFER_CONFIG.get(behavior)
        if not cfg:
            return False, 0.0
        
        if len(buffer) < cfg['window_size'] // 2:  # Need at least half window
            return False, 0.0
        
        # Count positive detections
        positive_count = sum(1 for x in buffer if x > 0)
        ratio = positive_count / len(buffer)
        
        triggered = ratio >= cfg['trigger_ratio']
        return triggered, ratio
    
    def _get_warning_priority(self, behavior: str) -> Tuple[int, str, Tuple[int, int, int]]:
        """
        Get priority level for a behavior.
        
        Returns:
            (priority_level, priority_name, color)
        """
        for priority_key, priority_data in self.PRIORITY_LEVELS.items():
            if behavior in priority_data['behaviors']:
                return (
                    priority_data['level'],
                    priority_data['name'],
                    priority_data['color']
                )
        return (99, 'UNKNOWN', (128, 128, 128))
    
    def _should_warn(self, behavior: str, cooldown_attr: str) -> bool:
        """
        Check if we should trigger a warning (considering cooldown).
        
        Args:
            behavior: Behavior type
            cooldown_attr: Attribute name for cooldown counter
        
        Returns:
            True if warning should trigger
        """
        cfg = self.TIME_BUFFER_CONFIG.get(behavior)
        if not cfg:
            return True
        
        cooldown = getattr(self, cooldown_attr, 0)
        if cooldown > 0:
            setattr(self, cooldown_attr, cooldown - 1)
            return False
        
        # Reset cooldown when triggered
        setattr(self, cooldown_attr, cfg['cooldown_frames'])
        return True
    
    # ==================== FACE MESH & EAR ====================
    
    def _calculate_ear(self, eye_landmarks: List[Tuple[float, float]]) -> float:
        """
        Calculate Eye Aspect Ratio (EAR).
        
        EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
        
        Khi mắt mở: EAR ~ 0.25-0.35
        Khi mắt nhắm: EAR < 0.21
        
        Args:
            eye_landmarks: 6 điểm [p1, p2, p3, p4, p5, p6]
                          p1: góc mắt ngoài, p4: góc mắt trong
                          p2, p3: mí trên, p5, p6: mí dưới
        
        Returns:
            EAR value (0.0 - 0.5)
        """
        if len(eye_landmarks) != 6:
            return 0.3
        
        # Khoảng cách dọc
        v1 = self._distance(eye_landmarks[1], eye_landmarks[5])
        v2 = self._distance(eye_landmarks[2], eye_landmarks[4])
        
        # Khoảng cách ngang
        h = self._distance(eye_landmarks[0], eye_landmarks[3])
        
        if h == 0:
            return 0.3
        
        ear = (v1 + v2) / (2.0 * h)
        return ear
    
    def _calculate_mar(self, mouth_landmarks: List[Tuple[float, float]]) -> float:
        """
        Calculate Mouth Aspect Ratio (MAR) for yawn detection.
        
        MAR = vertical_dist / horizontal_dist
        
        Args:
            mouth_landmarks: 6 điểm miệng
        
        Returns:
            MAR value
        """
        if len(mouth_landmarks) < 4:
            return 0.0
        
        # Simplified: top-bottom / left-right
        v = self._distance(mouth_landmarks[2], mouth_landmarks[3])
        h = self._distance(mouth_landmarks[0], mouth_landmarks[1])
        
        if h == 0:
            return 0.0
        
        return v / h
    
    def process_face_mesh(self, frame: np.ndarray) -> Dict:
        """
        Process frame with MediaPipe Face Mesh - ENHANCED VERSION.
        
        NEW Features:
        - Microsleep detection (blink > 800ms)
        - Drowsy eyes detection (EAR < 0.2 continuously for 2s)
        - Improved yawn detection with duration tracking
        - Stroke detection (facial asymmetry)
        
        Returns:
            Dict with all face analysis results
        """
        result = {
            'ear': 0.3,
            'ear_left': 0.3,
            'ear_right': 0.3,
            'mar': 0.0,
            'blink_detected': False,
            'eyes_open': True,
            'yawning': False,
            'face_landmarks': None,
            'face_detected': False,
            # NEW fields
            'microsleep': False,
            'microsleep_duration_ms': 0,
            'long_blink': False,
            'blink_duration_ms': 0,
            'drowsy_eyes': False,  # Mắt lờ đờ
            'drowsy_eyes_duration': 0.0,
            'ear_asymmetry': 0.0,
            'stroke_warning': False,
            'yawn_duration': 0.0,
        }
        
        if not self.enable_face_mesh or self.face_mesh is None:
            return result
        
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb_frame.flags.writeable = False
            
            # Process with Face Mesh
            results = self.face_mesh.process(rgb_frame)
            
            if not results.multi_face_landmarks:
                # No face - reset tracking states
                self._reset_blink_tracking()
                return result
            
            # Get first face
            face_landmarks = results.multi_face_landmarks[0]
            result['face_detected'] = True
            result['face_landmarks'] = face_landmarks
            
            h, w = frame.shape[:2]
            
            # Extract eye landmarks
            def get_landmark_coords(idx):
                lm = face_landmarks.landmark[idx]
                return (lm.x * w, lm.y * h)
            
            # Left eye (from viewer's perspective, right side of image)
            left_eye = [get_landmark_coords(i) for i in self.LEFT_EYE_IDX]
            # Right eye
            right_eye = [get_landmark_coords(i) for i in self.RIGHT_EYE_IDX]
            
            # Calculate EAR for each eye
            ear_left = self._calculate_ear(left_eye)
            ear_right = self._calculate_ear(right_eye)
            ear_avg = (ear_left + ear_right) / 2.0
            
            result['ear_left'] = round(ear_left, 3)
            result['ear_right'] = round(ear_right, 3)
            result['ear'] = round(ear_avg, 3)
            
            # Update EAR buffer
            self.ear_buffer.append(ear_avg)
            self.current_ear = ear_avg
            
            # ===== 1. STROKE DETECTION - Facial Asymmetry =====
            ear_asymmetry = abs(ear_left - ear_right)
            result['ear_asymmetry'] = round(ear_asymmetry, 3)
            
            if ear_asymmetry > self.STROKE_EAR_ASYMMETRY:
                self.ear_asymmetry_frames += 1
                if self.ear_asymmetry_frames >= self.STROKE_CONFIRM_FRAMES:
                    result['stroke_warning'] = True
                    self.stroke_warning_active = True
            else:
                self.ear_asymmetry_frames = max(0, self.ear_asymmetry_frames - 1)
            
            # ===== 2. MICROSLEEP & BLINK DURATION Detection =====
            current_time = time.time()
            eyes_currently_closed = ear_avg < self.EAR_THRESHOLD
            
            if eyes_currently_closed:
                # Eyes just closed - start timing
                if self.blink_start_time is None:
                    self.blink_start_time = current_time
                
                # Calculate current closure duration
                closure_duration_ms = (current_time - self.blink_start_time) * 1000
                result['blink_duration_ms'] = int(closure_duration_ms)
                
                # Check for microsleep (> 800ms)
                if closure_duration_ms >= self.MICROSLEEP_MS:
                    result['microsleep'] = True
                    result['microsleep_duration_ms'] = int(closure_duration_ms)
                    self.microsleep_detected = True
                # Long blink (400-800ms) - warning sign
                elif closure_duration_ms >= self.BLINK_NORMAL_MAX_MS:
                    result['long_blink'] = True
                
                self.blink_counter += 1
            else:
                # Eyes just opened - calculate blink duration
                if self.blink_start_time is not None:
                    blink_duration_ms = (current_time - self.blink_start_time) * 1000
                    self.last_blink_duration_ms = blink_duration_ms
                    
                    # Count blink types
                    if blink_duration_ms >= self.MICROSLEEP_MS:
                        self.microsleep_count += 1
                    elif blink_duration_ms >= self.BLINK_NORMAL_MAX_MS:
                        self.long_blink_count += 1
                    
                    # Normal blink completed
                    if self.blink_counter >= self.EAR_CONSEC_FRAMES:
                        self.total_blinks += 1
                        result['blink_detected'] = True
                
                # Reset blink tracking
                self.blink_start_time = None
                self.blink_counter = 0
                self.microsleep_detected = False
            
            # Check if eyes are open
            result['eyes_open'] = not eyes_currently_closed
            
            # PERCLOS update
            self.perclos_buffer.append(1 if eyes_currently_closed else 0)
            
            # ===== 3. DROWSY EYES Detection (EAR < 0.20 continuously) =====
            # Different from closed eyes - this is "half-closed" drowsy look
            drowsy_ear_threshold = getattr(self, 'EAR_DROWSY_THRESHOLD', 0.20)
            is_drowsy_looking = ear_avg < drowsy_ear_threshold and ear_avg >= (self.EAR_THRESHOLD - 0.05)
            
            # Or just very low EAR for extended time
            if ear_avg < drowsy_ear_threshold:
                if self.drowsy_eyes_start_time is None:
                    self.drowsy_eyes_start_time = current_time
                
                drowsy_duration = current_time - self.drowsy_eyes_start_time
                result['drowsy_eyes_duration'] = round(drowsy_duration, 2)
                self.drowsy_eyes_duration = drowsy_duration
                
                # 2 seconds of low EAR = drowsy eyes / lờ đờ
                if drowsy_duration >= self.EAR_DROWSY_TIME:
                    result['drowsy_eyes'] = True
                    self.drowsy_eyes_detected = True
            else:
                self.drowsy_eyes_start_time = None
                self.drowsy_eyes_detected = False
                self.drowsy_eyes_duration = 0.0
            
            # Track eyes closed duration (original logic)
            if eyes_currently_closed:
                if self.eyes_closed_start_time is None:
                    self.eyes_closed_start_time = current_time
                self.eyes_closed_frames += 1
            else:
                self.eyes_closed_start_time = None
                self.eyes_closed_frames = 0
            
            # ===== 4. IMPROVED YAWN Detection =====
            try:
                mouth = [get_landmark_coords(i) for i in self.MOUTH_IDX]
                mar = self._calculate_mar(mouth)
                result['mar'] = round(mar, 3)
                self.mar_buffer.append(mar)
                self.current_mar = mar
                
                # Yawn detection with duration tracking
                mar_confirm = getattr(self, 'MAR_YAWN_CONFIRM', 0.65)
                
                if mar > self.MAR_THRESHOLD:
                    # Mouth is open wide
                    if self.yawn_start_time is None:
                        self.yawn_start_time = current_time
                    
                    yawn_duration = current_time - self.yawn_start_time
                    result['yawn_duration'] = round(yawn_duration, 2)
                    self.current_yawn_duration = yawn_duration
                    
                    self.yawn_counter += 1
                    
                    # Confirm yawn: mouth very wide OR sustained open mouth
                    if mar > mar_confirm or self.yawn_counter >= self.YAWN_FRAMES:
                        result['yawning'] = True
                        
                        # Track yawns for frequency analysis
                        if self.yawn_counter == self.YAWN_FRAMES:  # Only count once per yawn
                            self.yawns_in_last_5min.append(current_time)
                else:
                    # Mouth closed - reset yawn tracking
                    self.yawn_counter = 0
                    self.yawn_start_time = None
                    self.current_yawn_duration = 0.0
            except Exception as e:
                logger.debug(f"Yawn detection error: {e}")
            
            return result
            
        except Exception as e:
            logger.debug(f"Face mesh error: {e}")
            return result
    
    def _reset_blink_tracking(self):
        """Reset blink tracking when face is lost."""
        self.blink_start_time = None
        self.blink_counter = 0
        self.microsleep_detected = False
    
    def get_perclos(self) -> float:
        """
        Calculate PERCLOS (Percentage of Eye Closure).
        
        Returns:
            % of time eyes were closed (0.0 - 1.0)
        """
        if len(self.perclos_buffer) == 0:
            return 0.0
        return sum(self.perclos_buffer) / len(self.perclos_buffer)
    
    def draw_face_mesh(
        self,
        frame: np.ndarray,
        face_landmarks,
        ear: float,
        eyes_open: bool
    ) -> np.ndarray:
        """
        Vẽ Face Mesh overlay với EAR và trạng thái mắt.
        """
        if face_landmarks is None:
            return frame
        
        frame = frame.copy()
        h, w = frame.shape[:2]
        
        # Vẽ mesh connections (tesselation)
        if self.mp_drawing and self.mp_face_mesh:
            self.mp_drawing.draw_landmarks(
                image=frame,
                landmark_list=face_landmarks,
                connections=self.mp_face_mesh.FACEMESH_TESSELATION,
                landmark_drawing_spec=None,
                connection_drawing_spec=self.mp_drawing_styles.get_default_face_mesh_tesselation_style()
            )
            
            # Vẽ contour mắt
            self.mp_drawing.draw_landmarks(
                image=frame,
                landmark_list=face_landmarks,
                connections=self.mp_face_mesh.FACEMESH_LEFT_EYE,
                landmark_drawing_spec=None,
                connection_drawing_spec=self.mp_drawing.DrawingSpec(
                    color=(0, 255, 0) if eyes_open else (0, 0, 255),
                    thickness=2
                )
            )
            self.mp_drawing.draw_landmarks(
                image=frame,
                landmark_list=face_landmarks,
                connections=self.mp_face_mesh.FACEMESH_RIGHT_EYE,
                landmark_drawing_spec=None,
                connection_drawing_spec=self.mp_drawing.DrawingSpec(
                    color=(0, 255, 0) if eyes_open else (0, 0, 255),
                    thickness=2
                )
            )
        
        # Vẽ text EAR và Blinks (góc trên trái) — PIL for Vietnamese
        eye_status = "MỞ" if eyes_open else "NHẮM"
        eye_color = (0, 255, 0) if eyes_open else (0, 0, 255)
        
        frame = self._draw_texts_pil_batch(frame, [
            (f"MẮT: {eye_status} ({ear:.2f})", (10, 8), eye_color, self.font_medium),
            (f"CHỚP MẮT: {self.total_blinks}", (10, 38), (255, 255, 0), self.font_medium),
        ])
        
        return frame
    
    # ==================== HEAD POSE ESTIMATION ====================
    
    def estimate_head_pose(self, keypoints: Dict) -> Dict:
        """
        Ước lượng Head Pose (yaw, pitch, roll) từ facial keypoints.
        
        COCO Pose Keypoints:
        0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear
        5: left_shoulder, 6: right_shoulder
        
        Approach:
        - YAW: Tỉ lệ khoảng cách nose-ears (nếu nhìn trái, gần tai phải hơn)
        - PITCH: Tỉ lệ nose-eyes vs nose-shoulders
        - ROLL: Góc của đường nối 2 mắt với đường ngang
        
        Returns:
            Dict với yaw, pitch, roll (degrees) và is_valid
        """
        if keypoints is None:
            return {'yaw': 0, 'pitch': 0, 'roll': 0, 'is_valid': False}
        
        try:
            nose = keypoints['nose']
            left_eye = keypoints['left_eye']
            right_eye = keypoints['right_eye']
            left_ear = keypoints['left_ear']
            right_ear = keypoints['right_ear']
            left_shoulder = keypoints['left_shoulder']
            right_shoulder = keypoints['right_shoulder']
            
            # ===== YAW (Left/Right rotation) =====
            # Dựa vào visibility của tai
            # Khi quay trái: right_ear visible, left_ear hidden
            dist_nose_left_ear = self._distance(nose, left_ear)
            dist_nose_right_ear = self._distance(nose, right_ear)
            
            # Tỉ lệ khoảng cách
            if dist_nose_left_ear + dist_nose_right_ear > 0:
                yaw_ratio = (dist_nose_right_ear - dist_nose_left_ear) / (dist_nose_right_ear + dist_nose_left_ear)
                # Map to degrees (-60 to +60)
                yaw = yaw_ratio * 60
            else:
                yaw = 0
            
            # Thêm validation từ vị trí mũi vs trung điểm mắt
            eye_center_x = (left_eye[0] + right_eye[0]) / 2
            nose_offset = nose[0] - eye_center_x
            eye_width = abs(right_eye[0] - left_eye[0])
            if eye_width > 0:
                yaw_from_nose = (nose_offset / eye_width) * 30
                yaw = (yaw + yaw_from_nose) / 2  # Average both estimates
            
            # ===== PITCH (Up/Down tilt) =====
            # Vị trí mũi so với mắt
            eye_center_y = (left_eye[1] + right_eye[1]) / 2
            shoulder_center_y = (left_shoulder[1] + right_shoulder[1]) / 2
            
            # Khoảng cách mũi-mắt bình thường vs thực tế
            nose_eye_dist = nose[1] - eye_center_y
            eye_shoulder_dist = shoulder_center_y - eye_center_y
            
            if eye_shoulder_dist > 0:
                normal_nose_ratio = 0.15  # Tỉ lệ bình thường
                actual_ratio = nose_eye_dist / eye_shoulder_dist
                pitch_deviation = actual_ratio - normal_nose_ratio
                # Map to degrees (-45 to +45)
                pitch = pitch_deviation * 150
                pitch = max(-45, min(45, pitch))
            else:
                pitch = 0
            
            # ===== ROLL (Lateral head tilt) =====
            # Góc của đường nối 2 mắt với đường ngang
            dx = right_eye[0] - left_eye[0]
            dy = right_eye[1] - left_eye[1]
            if dx != 0:
                roll = math.degrees(math.atan2(dy, dx))
            else:
                roll = 0
            
            # Add to buffers for smoothing
            self.yaw_buffer.append(yaw)
            self.pitch_buffer.append(pitch)
            self.roll_buffer.append(roll)
            
            # Smoothed values
            smooth_yaw = np.mean(list(self.yaw_buffer)[-10:]) if len(self.yaw_buffer) >= 5 else yaw
            smooth_pitch = np.mean(list(self.pitch_buffer)[-10:]) if len(self.pitch_buffer) >= 5 else pitch
            smooth_roll = np.mean(list(self.roll_buffer)[-10:]) if len(self.roll_buffer) >= 5 else roll
            
            return {
                'yaw': round(smooth_yaw, 1),
                'pitch': round(smooth_pitch, 1),
                'roll': round(smooth_roll, 1),
                'yaw_raw': round(yaw, 1),
                'pitch_raw': round(pitch, 1),
                'roll_raw': round(roll, 1),
                'is_valid': True
            }
            
        except Exception as e:
            logger.debug(f"Head pose estimation error: {e}")
            return {'yaw': 0, 'pitch': 0, 'roll': 0, 'is_valid': False}
    
    def calibrate_reference_pose(self, keypoints: Dict):
        """
        Calibrate reference pose khi tài xế nhìn thẳng.
        Call này khi bắt đầu video hoặc khi biết chắc tài xế đang nhìn thẳng.
        """
        head_pose = self.estimate_head_pose(keypoints)
        if head_pose['is_valid']:
            self.calibration_frames.append(head_pose)
            if len(self.calibration_frames) >= 30:
                # Average of first 30 frames as reference
                self.reference_pose = {
                    'yaw': np.mean([p['yaw'] for p in self.calibration_frames]),
                    'pitch': np.mean([p['pitch'] for p in self.calibration_frames]),
                    'roll': np.mean([p['roll'] for p in self.calibration_frames]),
                }
                self.is_calibrated = True
                logger.info(f"✅ Head pose calibrated: yaw={self.reference_pose['yaw']:.1f}°, pitch={self.reference_pose['pitch']:.1f}°")
    
    # ==================== ATTENTION SCORE ====================
    
    def calculate_attention_score(
        self,
        head_pose: Dict,
        using_phone: bool,
        drinking: bool,
        smoking: bool
    ) -> int:
        """
        Tính Attention Score (0-100).
        
        Factors:
        - Head looking forward (yaw < threshold): 35 points
        - Head level (pitch < threshold): 20 points
        - Eyes appear open: 25 points
        - Not using phone/drinking/smoking: 20 points
        
        Returns:
            Score 0-100 (100 = fully attentive)
        """
        score = 0
        
        if not self.enable_attention:
            return 100
        
        # 1. Head forward (35 points)
        if head_pose['is_valid']:
            yaw = abs(head_pose['yaw'])
            if yaw < 15:
                score += 35
            elif yaw < self.YAW_THRESHOLD:
                score += int(35 * (1 - (yaw - 15) / (self.YAW_THRESHOLD - 15)))
            # else: 0 points
        else:
            score += 20  # Give some points if we can't estimate
        
        # 2. Head level (20 points)
        if head_pose['is_valid']:
            pitch = abs(head_pose['pitch'])
            if pitch < 10:
                score += 20
            elif pitch < self.PITCH_THRESHOLD:
                score += int(20 * (1 - (pitch - 10) / (self.PITCH_THRESHOLD - 10)))
        else:
            score += 10
        
        # 3. Eyes open approximation (25 points)
        # Dựa vào pitch - nếu cúi đầu quá, có thể đang nhắm mắt
        if head_pose['is_valid']:
            pitch = head_pose['pitch']
            roll = abs(head_pose['roll'])
            
            # Nếu đầu không cúi quá và không nghiêng quá -> eyes likely open
            if pitch > -self.PITCH_THRESHOLD and roll < self.ROLL_THRESHOLD:
                score += 25
            elif pitch > -self.PITCH_SEVERE:
                score += 15
            else:
                score += 5  # Heavily nodding = likely drowsy
        else:
            score += 15
        
        # 4. No distractions (20 points)
        if not using_phone and not drinking and not smoking:
            score += 20
        elif not using_phone:
            score += 10  # Phone is most dangerous
        
        # Clamp to 0-100
        score = max(0, min(100, score))
        
        # Smooth the score
        self.attention_history.append(score)
        if len(self.attention_history) >= 5:
            score = int(np.mean(list(self.attention_history)[-15:]))
        
        self.current_attention_score = score
        return score
    
    def get_distraction_level(self, attention_score: int) -> str:
        """Get distraction level from attention score."""
        for level, (low, high) in self.DISTRACTION_LEVELS.items():
            if low <= attention_score <= high:
                self.current_distraction_level = level
                return level
        return 'MEDIUM'
    
    # ==================== BEHAVIOR DETECTION ====================
    
    def _distance(self, p1, p2) -> float:
        """Euclidean distance between two points."""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    @torch.no_grad()
    def detect_objects(self, frame: np.ndarray) -> List[Dict]:
        """
        Phát hiện điện thoại, cốc, chai - NHẠY HƠN.
        
        Returns:
            List of detected objects with bounding boxes
        """
        try:
            # Use lower confidence for more sensitive detection
            results = self.object_model(
                frame, 
                device=self.device, 
                verbose=False,
                half=self.use_fp16,
                conf=self.OBJ_CONF_THRESHOLD  # Dùng threshold thấp hơn
            )
            objects = []
            
            # Clear detection boxes for this frame
            self.detection_boxes = {}
            
            for result in results:
                if result.boxes is None:
                    continue
                
                for box in result.boxes:
                    cls_id = int(box.cls[0].item())
                    
                    if cls_id not in self.OBJECT_CLASSES:
                        continue
                    
                    conf = float(box.conf[0].item())
                    xyxy = box.xyxy[0].cpu().numpy()
                    x1, y1, x2, y2 = map(int, xyxy)
                    
                    obj_data = {
                        'class_id': cls_id,
                        'class_name': self.OBJECT_CLASSES[cls_id],
                        'confidence': conf,
                        'bbox': [x1, y1, x2, y2],
                        'center': ((x1 + x2) // 2, (y1 + y2) // 2),
                        'area': (x2 - x1) * (y2 - y1)
                    }
                    objects.append(obj_data)
                    
                    # Store for visualization
                    class_name = self.OBJECT_CLASSES[cls_id]
                    if class_name not in self.detection_boxes:
                        self.detection_boxes[class_name] = []
                    self.detection_boxes[class_name].append(obj_data)
            
            return objects
            
        except Exception as e:
            logger.error(f"❌ Object detection error: {e}")
            return []
    
    @torch.no_grad()
    def detect_pose(self, frame: np.ndarray) -> Optional[Dict]:
        """Phát hiện pose của tài xế."""
        try:
            results = self.pose_model(frame, device=self.device, verbose=False, half=self.use_fp16)
            
            for result in results:
                if result.keypoints is None:
                    continue
                
                kpts_data = result.keypoints.data
                if kpts_data.shape[0] == 0:
                    continue
                
                # Lấy người đầu tiên (tài xế)
                kpts = kpts_data[0].cpu().numpy()
                
                # Extract keypoints với confidence
                def get_point(idx):
                    return (kpts[idx][0], kpts[idx][1], kpts[idx][2])  # x, y, conf
                
                return {
                    'nose': kpts[0][:2],
                    'left_eye': kpts[1][:2],
                    'right_eye': kpts[2][:2],
                    'left_ear': kpts[3][:2],
                    'right_ear': kpts[4][:2],
                    'left_shoulder': kpts[5][:2],
                    'right_shoulder': kpts[6][:2],
                    'left_elbow': kpts[7][:2],
                    'right_elbow': kpts[8][:2],
                    'left_wrist': kpts[9][:2],
                    'right_wrist': kpts[10][:2],
                    'keypoints': kpts,
                    'keypoints_conf': kpts[:, 2],  # confidence scores
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Pose detection error: {e}")
            return None
    
    def check_phone_use(self, objects: List[Dict], pose: Optional[Dict], frame_shape: Tuple[int, int] = (720, 1280)) -> Tuple[bool, str, float]:
        """
        Kiểm tra dùng điện thoại với confidence score.
        
        Args:
            objects: List of detected objects
            pose: Pose detection result
            frame_shape: (height, width) of frame for adaptive threshold
        
        Returns:
            (is_using, warning_message, confidence)
        """
        if pose is None:
            self.phone_buffer.append(0)
            return False, "", 0.0
        
        phones = [obj for obj in objects if obj['class_name'] == 'điện thoại']
        
        if not phones:
            self.phone_buffer.append(0)
            return False, "", 0.0
        
        # Reference points
        nose = pose['nose']
        left_ear = pose['left_ear']
        right_ear = pose['right_ear']
        left_wrist = pose.get('left_wrist', nose)
        right_wrist = pose.get('right_wrist', nose)
        
        # Adaptive threshold based on frame size (scale from 720p baseline)
        h, w = frame_shape
        scale = max(h, w) / 1280.0
        phone_threshold = self.PHONE_DISTANCE_THRESHOLD * scale  # Scale threshold
        wrist_threshold = phone_threshold * 1.5  # Larger threshold for wrist check
        
        for phone in phones:
            pc = phone['center']
            
            # Check distances to face and hands
            dist_nose = self._distance(pc, nose)
            dist_left_ear = self._distance(pc, left_ear)
            dist_right_ear = self._distance(pc, right_ear)
            dist_left_wrist = self._distance(pc, left_wrist)
            dist_right_wrist = self._distance(pc, right_wrist)
            
            min_face_dist = min(dist_nose, dist_left_ear, dist_right_ear)
            min_wrist_dist = min(dist_left_wrist, dist_right_wrist)
            
            # HIGH CONFIDENCE PHONE: Warn immediately if phone detected clearly
            # In a car cabin, if YOLO sees a phone with high confidence, driver is likely using it
            if phone['confidence'] >= 0.5:
                self.phone_buffer.append(phone['confidence'])
                
                # Phone near face => calling or looking at phone
                if min_face_dist < phone_threshold:
                    if min_face_dist == dist_nose:
                        msg = "📱 CẢNH BÁO: ĐANG NHÌN ĐIỆN THOẠI!"
                    else:
                        msg = "📱 CẢNH BÁO: ĐANG GỌI ĐIỆN KHI LÁI XE!"
                    return True, msg, phone['confidence']
                
                # Phone near hand => holding phone
                if min_wrist_dist < wrist_threshold:
                    msg = "📱 CẢNH BÁO: ĐANG DÙNG ĐIỆN THOẠI KHI LÁI XE!"
                    return True, msg, phone['confidence']
            
            # LOWER CONFIDENCE: Check distance to face
            min_dist = min(min_face_dist, min_wrist_dist / 1.5)
            
            if min_dist < phone_threshold:
                conf = 1.0 - (min_dist / phone_threshold)
                conf = min(1.0, conf * phone['confidence'])
                self.phone_buffer.append(conf)
                
                # Temporal confirmation for lower confidence
                recent = list(self.phone_buffer)[-self.PHONE_CONFIRM_FRAMES:]
                if len(recent) >= self.PHONE_CONFIRM_FRAMES // 2:
                    avg_conf = np.mean([x for x in recent if x > 0])
                    if avg_conf > 0.3 and sum(1 for x in recent if x > 0) >= len(recent) // 2:
                        if min_face_dist < min_wrist_dist:
                            msg = "📱 CẢNH BÁO: ĐANG NHÌN ĐIỆN THOẠI!"
                        else:
                            msg = "📱 CẢNH BÁO: ĐANG DÙNG ĐIỆN THOẠI KHI LÁI XE!"
                        return True, msg, avg_conf
        
        self.phone_buffer.append(0)
        return False, "", 0.0
    
    def check_drinking(self, objects: List[Dict], pose: Optional[Dict], frame_shape: Tuple[int, int] = (720, 1280)) -> Tuple[bool, str, float]:
        """Kiểm tra đang uống nước."""
        if pose is None:
            self.drink_buffer.append(0)
            return False, "", 0.0
        
        drinks = [obj for obj in objects if obj['class_name'] in ['cốc', 'chai']]
        
        if not drinks:
            self.drink_buffer.append(0)
            return False, "", 0.0
        
        nose = pose['nose']
        
        # Adaptive threshold based on frame size
        h, w = frame_shape
        scale = max(h, w) / 1280.0
        drink_threshold = self.DRINK_DISTANCE_THRESHOLD * scale
        
        for drink in drinks:
            dist = self._distance(drink['center'], nose)
            
            if dist < drink_threshold:
                conf = (1.0 - dist / drink_threshold) * drink['confidence']
                self.drink_buffer.append(conf)
                
                # HIGH CONFIDENCE: Warn immediately
                if drink['confidence'] >= 0.5 and dist < drink_threshold * 0.8:
                    return True, "🥤 CẢNH BÁO: ĐANG UỐNG NƯỚC KHI LÁI XE!", conf
                
                # LOWER CONFIDENCE: Require temporal confirmation
                recent = list(self.drink_buffer)[-self.DRINK_CONFIRM_FRAMES:]
                if len(recent) >= self.DRINK_CONFIRM_FRAMES // 2:
                    avg_conf = np.mean([x for x in recent if x > 0])
                    if avg_conf > 0.3:
                        return True, "🥤 CẢNH BÁO: ĐANG UỐNG NƯỚC KHI LÁI XE!", avg_conf
        
        self.drink_buffer.append(0)
        return False, "", 0.0
    
    def check_smoking(self, pose: Optional[Dict]) -> Tuple[bool, str, float]:
        """
        Phát hiện hút thuốc qua pattern tay gần miệng.
        
        Logic: Nếu cổ tay gần mũi/miệng trong thời gian ngắn, lặp lại nhiều lần
        """
        if pose is None:
            self.smoke_buffer.append(0)
            return False, "", 0.0
        
        nose = pose['nose']
        left_wrist = pose.get('left_wrist', nose)
        right_wrist = pose.get('right_wrist', nose)
        
        dist_left = self._distance(left_wrist, nose)
        dist_right = self._distance(right_wrist, nose)
        min_dist = min(dist_left, dist_right)
        
        # Smoking: hand near mouth but not holding phone/drink
        if min_dist < self.SMOKE_DISTANCE_THRESHOLD:
            self.smoke_buffer.append(1.0)
        else:
            self.smoke_buffer.append(0)
        
        # Check pattern: hand near mouth nhiều lần trong 3 giây
        recent = list(self.smoke_buffer)[-30:]
        near_count = sum(1 for x in recent if x > 0)
        
        # Smoking pattern: > 40% frames có tay gần miệng
        if near_count > len(recent) * 0.4 and len(recent) >= 20:
            return True, "🚬 CẢNH BÁO: NGHI NGỜ HÚT THUỐC KHI LÁI XE!", near_count / len(recent)
        
        return False, "", 0.0
    
    def check_seatbelt(self, frame: np.ndarray, pose: Optional[Dict]) -> Tuple[bool, str, float]:
        """
        Phát hiện dây an toàn (Seatbelt Detection).
        
        Approach:
        1. Lấy vùng từ vai xuống hông (torso region)
        2. Phát hiện cạnh bằng Canny
        3. Tìm đường thẳng chéo bằng Hough Transform
        4. Nếu có đường chéo từ vai này sang hông kia → có dây an toàn
        
        Returns:
            (is_wearing_seatbelt, warning_message, confidence)
            - confidence > 0.5: Phát hiện có/không dây an toàn
            - confidence = 0: Không thể xác định (không có pose, không rõ)
        """
        if pose is None:
            # Không có pose → không thể kiểm tra, trả về unknown state
            self.seatbelt_status = 'unknown'
            return False, "", 0.0  # confidence = 0 means unknown
        
        try:
            h, w = frame.shape[:2]
            
            # Lấy keypoints
            left_shoulder = pose.get('left_shoulder')
            right_shoulder = pose.get('right_shoulder')
            
            # Check if we have shoulder keypoints
            if left_shoulder is None or right_shoulder is None:
                self.seatbelt_status = 'unknown'
                return False, "", 0.0  # Cannot determine
            
            # COCO Pose: 11: left_hip, 12: right_hip
            # But our pose dict might have different keys
            keypoints = pose.get('keypoints')
            if keypoints is None or len(keypoints) < 13:
                self.seatbelt_status = 'unknown'
                return False, "", 0.0  # Cannot determine
            
            left_hip = keypoints[11][:2]
            right_hip = keypoints[12][:2]
            
            # Tính bounding box cho vùng ngực (torso)
            x_coords = [left_shoulder[0], right_shoulder[0], left_hip[0], right_hip[0]]
            y_coords = [left_shoulder[1], right_shoulder[1], left_hip[1], right_hip[1]]
            
            x_min = max(0, int(min(x_coords)) - 20)
            x_max = min(w, int(max(x_coords)) + 20)
            y_min = max(0, int(min(y_coords)) - 10)
            y_max = min(h, int(max(y_coords)) + 10)
            
            # Kiểm tra vùng hợp lệ
            if x_max - x_min < 50 or y_max - y_min < 50:
                return True, "", 0.0
            
            # Crop vùng ngực
            torso_roi = frame[y_min:y_max, x_min:x_max]
            
            # Chuyển sang grayscale
            gray = cv2.cvtColor(torso_roi, cv2.COLOR_BGR2GRAY)
            
            # Cải thiện contrast (CLAHE)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            
            # Gaussian blur để giảm noise
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Canny edge detection
            edges = cv2.Canny(gray, self.SEATBELT_CANNY_LOW, self.SEATBELT_CANNY_HIGH)
            
            # Hough Line Transform để tìm đường thẳng
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=self.SEATBELT_HOUGH_THRESHOLD,
                minLineLength=30,
                maxLineGap=10
            )
            
            # Kiểm tra có đường chéo (diagonal line) không
            # Dây an toàn thường tạo góc 20-70 độ với phương ngang
            diagonal_lines = 0
            total_diagonal_length = 0
            
            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    
                    # Tính góc của đường thẳng
                    dx = abs(x2 - x1)
                    dy = abs(y2 - y1)
                    
                    if dx == 0:
                        continue
                    
                    angle = math.degrees(math.atan2(dy, dx))
                    
                    # Dây an toàn: góc 20-70 độ (không quá ngang, không quá dọc)
                    if 20 <= angle <= 70:
                        line_length = math.sqrt(dx**2 + dy**2)
                        if line_length > 30:  # Đường đủ dài
                            diagonal_lines += 1
                            total_diagonal_length += line_length
            
            # Tính confidence dựa trên số lượng và độ dài đường chéo
            roi_diagonal = math.sqrt((x_max - x_min)**2 + (y_max - y_min)**2)
            
            # Normalize by ROI size
            seatbelt_score = total_diagonal_length / max(roi_diagonal, 1)
            
            # Update buffer
            self.seatbelt_buffer.append(seatbelt_score)
            
            # Evaluate seatbelt status với temporal smoothing
            recent = list(self.seatbelt_buffer)[-self.SEATBELT_CONFIRM_FRAMES:]
            avg_score = np.mean(recent) if recent else 0
            
            # Thresholds - REALISTIC detection
            # Need significant diagonal edges to confirm seatbelt presence
            if avg_score >= self.SEATBELT_MIN_EDGE_RATIO:
                # Có dây an toàn - detected with high confidence
                self.seatbelt_detected = True
                self.seatbelt_status = 'wearing'
                self.no_seatbelt_frames = 0
                self.seatbelt_warning_sent = False
                # Confidence > 0.5 indicates reliable detection
                confidence = min(1.0, 0.5 + avg_score * 2)
                return True, "", confidence
            else:
                # Không phát hiện dây an toàn
                self.no_seatbelt_frames += 1
                
                # Chỉ cảnh báo sau khi confirm nhiều frames
                if self.no_seatbelt_frames >= self.SEATBELT_CONFIRM_FRAMES:
                    self.seatbelt_detected = False
                    self.seatbelt_status = 'not_wearing'
                    # High confidence that NO seatbelt
                    confidence = min(1.0, 0.7 + (1.0 - avg_score / self.SEATBELT_MIN_EDGE_RATIO) * 0.3)
                    return False, "🚨 CẢNH BÁO: KHÔNG THẮT DÂY AN TOÀN!", confidence
                
                # Chưa đủ frames để confirm - state is uncertain
                self.seatbelt_status = 'checking'
                return False, "", 0.3  # Low confidence, still checking
                
        except Exception as e:
            logger.debug(f"Seatbelt detection error: {e}")
            self.seatbelt_status = 'unknown'
            return False, "", 0.0  # Unknown state

    def draw_seatbelt_status(
        self,
        frame: np.ndarray,
        pose: Optional[Dict],
        seatbelt_detected: bool,
        confidence: float = 0.0
    ) -> np.ndarray:
        """
        Vẽ bounding box vùng ngực và trạng thái dây an toàn.
        
        REALISTIC - Chỉ vẽ những gì thực sự phát hiện được:
        - Nếu confidence thấp (<0.5): Không vẽ đường dây an toàn giả
        - Nếu không phát hiện được: Hiển thị rõ ràng "KHÔNG PHÁT HIỆN"
        """
        if pose is None:
            return frame
        
        frame = frame.copy()
        h, w = frame.shape[:2]
        
        try:
            left_shoulder = pose.get('left_shoulder')
            right_shoulder = pose.get('right_shoulder')
            keypoints = pose.get('keypoints')
            
            if left_shoulder is None or right_shoulder is None or keypoints is None:
                return frame
            
            if len(keypoints) < 13:
                return frame
            
            left_hip = keypoints[11][:2]
            right_hip = keypoints[12][:2]
            
            # Draw torso bounding box
            x_coords = [left_shoulder[0], right_shoulder[0], left_hip[0], right_hip[0]]
            y_coords = [left_shoulder[1], right_shoulder[1], left_hip[1], right_hip[1]]
            
            x_min = int(min(x_coords)) - 10
            x_max = int(max(x_coords)) + 10
            y_min = int(min(y_coords)) - 5
            y_max = int(max(y_coords)) + 5
            
            # Get actual seatbelt status from instance variable
            seatbelt_status = getattr(self, 'seatbelt_status', 'unknown')
            
            # Color and label based on ACTUAL detection status
            if seatbelt_status == 'wearing' and confidence >= 0.5:
                # Chỉ khi thực sự phát hiện được dây an toàn
                color = (0, 255, 0)  # Green
                label = "DÂY AN TOÀN: ĐÃ THẮT ✓"
                box_style = 'solid'
            elif seatbelt_status == 'not_wearing' and confidence >= 0.5:
                # Xác nhận KHÔNG có dây an toàn
                color = (0, 0, 255)  # Red
                label = "⚠ KHÔNG CÓ DÂY AN TOÀN!"
                box_style = 'alert'
            elif seatbelt_status == 'checking':
                # Đang kiểm tra
                color = (0, 200, 255)  # Yellow-Orange
                label = "DÂY AN TOÀN: ĐANG KIỂM TRA..."
                box_style = 'checking'
            else:
                # Unknown - không thể xác định (video TikTok, không phải cảnh lái xe)
                color = (128, 128, 128)  # Gray
                label = "DÂY AN TOÀN: KHÔNG PHÁT HIỆN"
                box_style = 'unknown'
            
            # Draw bounding box based on style
            if box_style == 'alert':
                # Animated alert border for no seatbelt
                thickness = 3 if (self.frame_count // 5) % 2 == 0 else 2
                cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color, thickness)
            elif box_style == 'checking':
                # Dashed-style for checking
                cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color, 1)
            elif box_style == 'solid':
                cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color, 2)
            else:
                # Unknown - dotted/light border
                cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color, 1)
            
            # Draw label — PIL for Vietnamese Unicode
            label_y = max(5, y_min - 28)
            frame = self._put_text_pil(frame, label, (x_min, label_y), color, self.font_medium)
            
            # REALISTIC: Chỉ vẽ đường dây an toàn khi THỰC SỰ phát hiện với confidence cao
            # KHÔNG vẽ đường giả khi không có dây an toàn!
            if seatbelt_status == 'wearing' and confidence >= 0.6:
                # Draw approximate seatbelt line (shoulder to opposite hip)
                # Chỉ khi confidence >= 0.6 mới vẽ
                cv2.line(frame,
                        (int(left_shoulder[0]), int(left_shoulder[1])),
                        (int(right_hip[0]), int(right_hip[1])),
                        (255, 0, 255), 2)  # Magenta
            
        except Exception as e:
            logger.debug(f"Draw seatbelt error: {e}")
        
        return frame

    def check_drowsiness(self, pose: Optional[Dict], head_pose: Dict) -> Tuple[bool, str, str, float]:
        """
        Phát hiện buồn ngủ đa tiêu chí.
        
        Indicators:
        1. Head nodding (pitch oscillation) - gật gù
        2. Head tilt (roll > threshold) - nghiêng đầu
        3. Looking down too long - cúi đầu
        4. Shoulder slump - vai sụp
        
        Returns:
            (is_drowsy, warning_message, severity, confidence)
        """
        if pose is None:
            return False, "", "NONE", 0.0
        
        indicators = []
        
        # 1. Head nodding detection (pitch changes)
        if head_pose['is_valid']:
            self.head_nod_buffer.append(head_pose['pitch'])
            
            if len(self.head_nod_buffer) >= 30:
                recent_pitch = list(self.head_nod_buffer)[-30:]
                pitch_std = np.std(recent_pitch)
                pitch_mean = np.mean(recent_pitch)
                
                # High variation + downward mean = nodding
                if pitch_std > 8 and pitch_mean < -5:
                    indicators.append(('nodding', 0.8))
        
        # 2. Head tilt (roll)
        if head_pose['is_valid']:
            roll = abs(head_pose['roll'])
            self.head_tilt_buffer.append(roll)
            
            if len(self.head_tilt_buffer) >= 30:
                recent_roll = list(self.head_tilt_buffer)[-30:]
                avg_roll = np.mean(recent_roll)
                
                if avg_roll > self.ROLL_THRESHOLD:
                    indicators.append(('head_tilt', min(1.0, avg_roll / 45)))
        
        # 3. Looking down (pitch severely negative)
        if head_pose['is_valid']:
            pitch = head_pose['pitch']
            if pitch < -self.PITCH_SEVERE:
                indicators.append(('looking_down', 0.7))
        
        # 4. Shoulder slump
        left_shoulder = pose['left_shoulder']
        right_shoulder = pose['right_shoulder']
        dx = right_shoulder[0] - left_shoulder[0]
        dy = right_shoulder[1] - left_shoulder[1]
        shoulder_angle = abs(math.degrees(math.atan2(dy, dx)))
        
        if shoulder_angle > 15:
            indicators.append(('shoulder_slump', min(1.0, shoulder_angle / 30)))
        
        # Evaluate drowsiness
        if not indicators:
            return False, "", "NONE", 0.0
        
        total_conf = sum(conf for _, conf in indicators)
        indicator_names = [name for name, _ in indicators]
        
        if total_conf >= 1.5 or len(indicators) >= 2:
            severity = "HIGH" if total_conf >= 2.0 else "MEDIUM"
            
            if 'nodding' in indicator_names:
                msg = "😴 NGUY HIỂM: TÀI XẾ ĐANG GẬT GÙ!"
            elif 'head_tilt' in indicator_names:
                msg = "😴 CẢNH BÁO: TÀI XẾ CÓ DẤU HIỆU BUỒN NGỦ!"
            else:
                msg = "😴 CẢNH BÁO: DẤU HIỆU MỆT MỎI!"
            
            return True, msg, severity, min(1.0, total_conf / 2)
        
        return False, "", "NONE", 0.0
    
    def check_looking_away(self, head_pose: Dict) -> Tuple[bool, str, float]:
        """
        Phát hiện tài xế nhìn ngang quá lâu.
        
        Returns:
            (is_looking_away, warning_message, duration_seconds)
        """
        if not head_pose['is_valid']:
            return False, "", 0.0
        
        yaw = abs(head_pose['yaw'])
        
        if yaw > self.YAW_THRESHOLD:
            self.looking_away_counter += 1
        else:
            self.looking_away_counter = max(0, self.looking_away_counter - 2)
        
        duration_seconds = self.looking_away_counter / 30  # Assuming 30 fps
        
        if self.looking_away_counter >= self.LOOKING_AWAY_FRAMES:
            direction = "TRÁI" if head_pose['yaw'] < 0 else "PHẢI"
            
            if yaw > self.YAW_SEVERE:
                msg = f"⚠️ NGUY HIỂM: KHÔNG NHÌN ĐƯỜNG - QUAY {direction} QUÁ LÂU!"
            else:
                msg = f"👀 CHÚ Ý: ĐANG NHÌN SANG {direction} QUÁ LÂU!"
            
            return True, msg, duration_seconds
        
        return False, "", duration_seconds
    
    # ==================== VISUALIZATION ====================
    
    def _draw_rounded_rect(self, img: np.ndarray, pt1: Tuple[int, int], pt2: Tuple[int, int], 
                           color: Tuple[int, int, int], radius: int = 15, 
                           thickness: int = -1, alpha: float = 1.0) -> np.ndarray:
        """
        Vẽ hình chữ nhật bo góc với alpha blending.
        
        Args:
            img: Image to draw on
            pt1: Top-left corner (x1, y1)
            pt2: Bottom-right corner (x2, y2)
            color: BGR color
            radius: Corner radius
            thickness: -1 for filled, >0 for outline
            alpha: Transparency (0.0 to 1.0)
        """
        x1, y1 = pt1
        x2, y2 = pt2
        
        # Create overlay for alpha blending
        overlay = img.copy()
        
        if thickness == -1:
            # Filled rounded rectangle
            # Draw the main rectangle body (without corners)
            cv2.rectangle(overlay, (x1 + radius, y1), (x2 - radius, y2), color, -1)
            cv2.rectangle(overlay, (x1, y1 + radius), (x2, y2 - radius), color, -1)
            
            # Draw the four corner circles
            cv2.circle(overlay, (x1 + radius, y1 + radius), radius, color, -1)
            cv2.circle(overlay, (x2 - radius, y1 + radius), radius, color, -1)
            cv2.circle(overlay, (x1 + radius, y2 - radius), radius, color, -1)
            cv2.circle(overlay, (x2 - radius, y2 - radius), radius, color, -1)
        else:
            # Outline only
            cv2.line(overlay, (x1 + radius, y1), (x2 - radius, y1), color, thickness)
            cv2.line(overlay, (x1 + radius, y2), (x2 - radius, y2), color, thickness)
            cv2.line(overlay, (x1, y1 + radius), (x1, y2 - radius), color, thickness)
            cv2.line(overlay, (x2, y1 + radius), (x2, y2 - radius), color, thickness)
            
            cv2.ellipse(overlay, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, thickness)
            cv2.ellipse(overlay, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, thickness)
            cv2.ellipse(overlay, (x1 + radius, y2 - radius), (radius, radius), 90, 0, 90, color, thickness)
            cv2.ellipse(overlay, (x2 - radius, y2 - radius), (radius, radius), 0, 0, 90, color, thickness)
        
        # Apply alpha blending
        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
        return img
    
    def _draw_gradient_rect(self, img: np.ndarray, pt1: Tuple[int, int], pt2: Tuple[int, int],
                            color1: Tuple[int, int, int], color2: Tuple[int, int, int],
                            direction: str = 'vertical', alpha: float = 0.8) -> np.ndarray:
        """
        Vẽ hình chữ nhật với gradient màu.
        """
        x1, y1 = pt1
        x2, y2 = pt2
        h = y2 - y1
        w = x2 - x1
        
        overlay = img.copy()
        
        if direction == 'vertical':
            for i in range(h):
                ratio = i / h
                color = tuple(int(c1 + (c2 - c1) * ratio) for c1, c2 in zip(color1, color2))
                cv2.line(overlay, (x1, y1 + i), (x2, y1 + i), color, 1)
        else:
            for i in range(w):
                ratio = i / w
                color = tuple(int(c1 + (c2 - c1) * ratio) for c1, c2 in zip(color1, color2))
                cv2.line(overlay, (x1 + i, y1), (x1 + i, y2), color, 1)
        
        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
        return img
    
    def _draw_glass_panel(self, img: np.ndarray, pt1: Tuple[int, int], pt2: Tuple[int, int],
                          base_color: Tuple[int, int, int] = (30, 30, 40),
                          alpha: float = 0.75, border_color: Tuple[int, int, int] = (100, 100, 120)) -> np.ndarray:
        """
        Vẽ panel kiểu glass-morphism (hiệu ứng kính mờ).
        """
        x1, y1 = pt1
        x2, y2 = pt2
        
        # Main panel with rounded corners
        img = self._draw_rounded_rect(img, pt1, pt2, base_color, radius=12, alpha=alpha)
        
        # Subtle top highlight (glass reflection effect)
        highlight_color = tuple(min(255, c + 30) for c in base_color)
        img = self._draw_rounded_rect(img, (x1, y1), (x2, y1 + 3), highlight_color, radius=12, alpha=0.3)
        
        # Border
        img = self._draw_rounded_rect(img, pt1, pt2, border_color, radius=12, thickness=1, alpha=0.5)
        
        return img
    
    def _draw_progress_bar(self, img: np.ndarray, x: int, y: int, width: int, height: int,
                           value: float, max_value: float = 100,
                           bg_color: Tuple[int, int, int] = (50, 50, 60),
                           fill_gradient: Tuple[Tuple, Tuple] = None) -> np.ndarray:
        """
        Vẽ progress bar với gradient fill.
        
        Args:
            value: Current value
            max_value: Maximum value
            fill_gradient: ((color1), (color2)) for gradient, or single color
        """
        # Background
        img = self._draw_rounded_rect(img, (x, y), (x + width, y + height), bg_color, radius=height//2, alpha=0.8)
        
        # Calculate fill width
        ratio = min(1.0, value / max_value)
        fill_width = int((width - 4) * ratio)
        
        if fill_width > 0:
            # Determine color based on value
            if fill_gradient is None:
                if ratio >= 0.7:
                    fill_color = (0, 200, 100)  # Green
                elif ratio >= 0.4:
                    fill_color = (0, 180, 255)  # Orange
                else:
                    fill_color = (0, 80, 255)   # Red
            else:
                fill_color = fill_gradient[0]
            
            img = self._draw_rounded_rect(
                img, (x + 2, y + 2), (x + 2 + fill_width, y + height - 2),
                fill_color, radius=max(1, height//2 - 2), alpha=0.9
            )
        
        return img
    
    def draw_dashboard(
        self,
        frame: np.ndarray,
        warnings: List[str],
        attention_score: int,
        head_pose: Dict,
        distraction_level: str
    ) -> np.ndarray:
        """
        Vẽ dashboard với metrics và warnings.
        """
        h, w = frame.shape[:2]
        frame_pil = Image.fromarray(frame)
        draw = ImageDraw.Draw(frame_pil)
        
        # ===== Warning Banner (top) - CLEAN & SIMPLE =====
        if warnings:
            banner_height = 45 + 40 * len(warnings)
            
            # Background — simple dark with slight transparency
            overlay = Image.new('RGBA', (w, banner_height), (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            # Clean dark background
            overlay_draw.rectangle([(0, 0), (w, banner_height)], fill=(20, 20, 30, 220))
            # Thin bottom line for separation
            overlay_draw.rectangle([(0, banner_height - 2), (w, banner_height)], fill=(255, 100, 100, 200))
            frame_pil.paste(overlay, (0, 0), overlay)
            
            # Warnings — clean white text, easy to read
            y = 10
            for warning in warnings:
                if self.font_large:
                    # White text for better readability
                    draw.text((15, y), warning, fill=(255, 255, 255), font=self.font_large)
                y += 40
        
        # ===== Dashboard Panel (bottom-left) =====
        panel_w, panel_h = 350, 180
        panel_x, panel_y = 10, h - panel_h - 10
        
        # Panel background
        panel_overlay = Image.new('RGBA', (panel_w, panel_h), (0, 0, 0, 180))
        frame_pil.paste(panel_overlay, (panel_x, panel_y), panel_overlay)
        
        # Get color based on distraction level
        level_colors = {
            'LOW': (0, 255, 0),
            'MEDIUM': (255, 200, 0),
            'HIGH': (255, 100, 0),
            'CRITICAL': (255, 0, 0)
        }
        color = level_colors.get(distraction_level, (255, 255, 255))
        
        if self.font_medium:
            # Title
            draw.text((panel_x + 10, panel_y + 10), "🚗 DRIVER MONITOR", 
                      fill=(255, 255, 255), font=self.font_medium)
            
            # Attention Score
            score_text = f"Attention: {attention_score}%"
            draw.text((panel_x + 10, panel_y + 45), score_text, fill=color, font=self.font_medium)
            
            # Distraction Level
            level_text = f"Status: {distraction_level}"
            draw.text((panel_x + 10, panel_y + 75), level_text, fill=color, font=self.font_medium)
            
            # Head Pose
            if head_pose['is_valid']:
                pose_text = f"Yaw: {head_pose['yaw']:+.0f}°  Pitch: {head_pose['pitch']:+.0f}°"
                draw.text((panel_x + 10, panel_y + 105), pose_text, 
                          fill=(200, 200, 200), font=self.font_small)
                
                roll_text = f"Roll: {head_pose['roll']:+.0f}°"
                draw.text((panel_x + 10, panel_y + 130), roll_text,
                          fill=(200, 200, 200), font=self.font_small)
        
        # ===== Attention Bar (bottom-right) =====
        bar_w, bar_h = 30, 150
        bar_x = w - bar_w - 20
        bar_y = h - bar_h - 30
        
        # Bar background
        draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], 
                       fill=(50, 50, 50), outline=(100, 100, 100))
        
        # Fill based on score
        fill_h = int(bar_h * attention_score / 100)
        fill_y = bar_y + bar_h - fill_h
        draw.rectangle([bar_x + 2, fill_y, bar_x + bar_w - 2, bar_y + bar_h - 2], 
                       fill=color)
        
        # Label
        if self.font_small:
            draw.text((bar_x - 5, bar_y - 25), f"{attention_score}", 
                      fill=color, font=self.font_medium)
        
        return np.array(frame_pil)
    
    def draw_pose_overlay(self, frame: np.ndarray, pose: Dict, head_pose: Dict) -> np.ndarray:
        """Vẽ pose keypoints và head pose direction."""
        if pose is None:
            return frame
        
        frame = frame.copy()
        
        # Draw facial keypoints
        keypoint_names = ['nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear']
        for name in keypoint_names:
            if name in pose:
                pt = pose[name]
                cv2.circle(frame, (int(pt[0]), int(pt[1])), 4, (0, 255, 255), -1)
        
        # Draw head direction arrow
        if head_pose['is_valid'] and 'nose' in pose:
            nose = pose['nose']
            yaw_rad = math.radians(head_pose['yaw'])
            pitch_rad = math.radians(head_pose['pitch'])
            
            # Arrow endpoint
            arrow_len = 60
            end_x = int(nose[0] + arrow_len * math.sin(yaw_rad))
            end_y = int(nose[1] - arrow_len * math.cos(pitch_rad) * 0.5)
            
            # Color based on yaw
            if abs(head_pose['yaw']) > self.YAW_SEVERE:
                color = (0, 0, 255)  # Red
            elif abs(head_pose['yaw']) > self.YAW_THRESHOLD:
                color = (0, 165, 255)  # Orange
            else:
                color = (0, 255, 0)  # Green
            
            cv2.arrowedLine(frame, (int(nose[0]), int(nose[1])), 
                           (end_x, end_y), color, 3, tipLength=0.3)
        
        return frame
    
    def draw_detection_boxes(
        self, 
        frame: np.ndarray, 
        behaviors: Dict,
        active_warnings: List[Dict]
    ) -> np.ndarray:
        """
        Vẽ bounding boxes sạch sẽ, text tiếng Việt qua PIL.
        """
        frame = frame.copy()
        h, w = frame.shape[:2]
        
        # Clean color palette (BGR)
        COLORS = {
            'phone': (50, 100, 255),      # Orange
            'drink': (50, 200, 255),      # Yellow
            'seatbelt': (200, 200, 50),   # Cyan
            'default': (200, 200, 200),   # Gray
        }
        
        # Collect all text draws for batch PIL rendering at the end
        pending_texts = []
        
        # ===== Draw object bounding boxes =====
        for class_name, detections in self.detection_boxes.items():
            for det in detections:
                x1, y1, x2, y2 = det['bbox']
                conf = det['confidence']
                
                # Determine color and label (proper Vietnamese)
                if class_name == 'điện thoại':
                    color = COLORS['phone']
                    label = f"ĐIỆN THOẠI {conf*100:.0f}%"
                elif class_name in ['cốc', 'chai']:
                    color = COLORS['drink']
                    label = f"ĐỒ UỐNG {conf*100:.0f}%"
                else:
                    color = COLORS['default']
                    label = f"{class_name.upper()} {conf*100:.0f}%"
                
                # Draw clean box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw corner accents
                corner_len = min(20, (x2-x1)//5)
                t = 3  # thickness
                cv2.line(frame, (x1, y1), (x1 + corner_len, y1), color, t)
                cv2.line(frame, (x1, y1), (x1, y1 + corner_len), color, t)
                cv2.line(frame, (x2, y1), (x2 - corner_len, y1), color, t)
                cv2.line(frame, (x2, y1), (x2, y1 + corner_len), color, t)
                cv2.line(frame, (x1, y2), (x1 + corner_len, y2), color, t)
                cv2.line(frame, (x1, y2), (x1, y2 - corner_len), color, t)
                cv2.line(frame, (x2, y2), (x2 - corner_len, y2), color, t)
                cv2.line(frame, (x2, y2), (x2, y2 - corner_len), color, t)
                
                # Draw label background
                label_h = 24
                label_w = len(label) * 11 + 10
                label_y = max(0, y1 - label_h - 2)
                
                # Semi-transparent background for label
                overlay = frame.copy()
                cv2.rectangle(overlay, (x1, label_y), (x1 + label_w, label_y + label_h), color, -1)
                cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
                
                # Queue label text for PIL batch render
                pending_texts.append((label, (x1 + 5, label_y + 2), (255, 255, 255), self.font_small))
        
        # ===== Draw seatbelt box if detected =====
        seatbelt_data = behaviors.get('seatbelt', {})
        if seatbelt_data.get('box'):
            box = seatbelt_data['box']
            is_on = seatbelt_data.get('detected', False)
            color = (100, 255, 100) if is_on else (100, 100, 255)
            label = "DÂY AN TOÀN: OK" if is_on else "DÂY AN TOÀN: CHƯA THẮT!"
            
            cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)
            pending_texts.append((label, (box[0], box[1] - 22), color, self.font_small))
        
        # ===== Draw status indicators (top-right) - ENHANCED =====
        active_behaviors = []
        
        if behaviors.get('phone', {}).get('detected'):
            active_behaviors.append(('ĐANG DÙNG ĐIỆN THOẠI', COLORS['phone']))
        if behaviors.get('drinking', {}).get('detected'):
            active_behaviors.append(('ĐANG UỐNG NƯỚC', COLORS['drink']))
        
        # Enhanced drowsiness indicators
        drowsiness_data = behaviors.get('drowsiness', {})
        if drowsiness_data.get('detected'):
            severity = drowsiness_data.get('severity', 'MEDIUM')
            
            # Show specific type of drowsiness
            if drowsiness_data.get('microsleep'):
                duration_ms = drowsiness_data.get('microsleep_duration_ms', 0)
                active_behaviors.append((f'⚠️ MICROSLEEP {duration_ms}ms', (0, 0, 255)))
            elif drowsiness_data.get('drowsy_eyes'):
                active_behaviors.append(('😴 MẮT LỜ ĐỜ', (0, 80, 255)))
            elif drowsiness_data.get('yawning'):
                active_behaviors.append(('😴 ĐANG NGÁP', (0, 180, 255)))
            elif severity == 'CRITICAL':
                active_behaviors.append(('🚨 NGỦ GẬT NGUY HIỂM', (0, 0, 255)))
            elif severity == 'HIGH':
                active_behaviors.append(('⚠️ RẤT BUỒN NGỦ', (0, 50, 255)))
            else:
                active_behaviors.append(('😴 DẤU HIỆU BUỒN NGỦ', (0, 180, 255)))
        
        # Stroke warning (critical)
        if drowsiness_data.get('stroke_warning'):
            active_behaviors.append(('🚨 BẤT ĐỐI XỨNG MẶT', (255, 0, 255)))
        
        if behaviors.get('looking_away', {}).get('detected'):
            active_behaviors.append(('KHÔNG NHÌN ĐƯỜNG', (0, 150, 255)))
        
        # Draw right-side status badges
        badge_x = w - 260
        badge_y = 15
        badge_h = 32
        badge_spacing = 6
        
        for i, (text, color) in enumerate(active_behaviors):
            y = badge_y + i * (badge_h + badge_spacing)
            badge_w = len(text) * 12 + 20
            
            # Background with alpha
            overlay = frame.copy()
            cv2.rectangle(overlay, (badge_x, y), (badge_x + badge_w, y + badge_h), color, -1)
            cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
            cv2.rectangle(frame, (badge_x, y), (badge_x + badge_w, y + badge_h), (255, 255, 255), 1)
            
            # Queue badge text for PIL batch render
            pending_texts.append((text, (badge_x + 10, y + 5), (255, 255, 255), self.font_small))
        
        # ===== Batch render ALL text with PIL (one conversion round-trip) =====
        frame = self._draw_texts_pil_batch(frame, pending_texts)
        
        return frame
    
    def _stabilize_warnings(self, warnings: List[str]) -> List[str]:
        """Stabilize warnings to prevent rapid flickering between frames.
        
        Keeps a warning displayed for at least WARNING_PERSIST_TIME seconds
        after it was last triggered, so it doesn't flash on/off every frame.
        """
        now = time.time()
        
        # Update timestamps for currently active warnings
        for w in warnings:
            key = self._get_warning_key(w)
            self._stable_warnings[key] = {'message': w, 'last_seen': now}
        
        # Build stable list: include recent warnings even if not in current frame
        stable = []
        expired_keys = []
        for key, data in self._stable_warnings.items():
            if now - data['last_seen'] < self.WARNING_PERSIST_TIME:
                stable.append(data['message'])
            else:
                expired_keys.append(key)
        
        # Clean expired
        for key in expired_keys:
            del self._stable_warnings[key]
        
        return stable
    
    def _get_warning_key(self, warning: str) -> str:
        """Extract a stable key from warning message (ignore variable parts like durations)."""
        w = warning.lower()
        if 'điện thoại' in w or 'gọi điện' in w:
            return 'phone'
        elif 'ngủ gật' in w or 'mắt nhắm' in w or 'perclos' in w or 'buồn ngủ' in w or 'microsleep' in w or 'lờ đờ' in w:
            return 'drowsy'
        elif 'ngáp' in w or 'mệt mỏi' in w:
            return 'yawn'
        elif 'nhìn' in w or 'quay' in w or 'không nhìn đường' in w:
            return 'looking_away'
        elif 'dây an toàn' in w or 'seatbelt' in w:
            return 'seatbelt'
        elif 'uống' in w:
            return 'drinking'
        elif 'thuốc' in w or 'hút' in w:
            return 'smoking'
        elif 'bất đối xứng' in w or 'stroke' in w:
            return 'stroke'
        return warning[:30]  # fallback: first 30 chars as key
    
    def prioritize_warnings(self, warnings: List[str], behaviors: Dict) -> List[Dict]:
        """
        Sắp xếp warnings theo mức độ ưu tiên (Priority Matrix).
        
        Returns:
            List of warnings sorted by priority with metadata
        """
        prioritized = []
        drowsiness_data = behaviors.get('drowsiness', {})
        severity = drowsiness_data.get('severity', 'NONE')
        
        # Check P0 - CRITICAL (microsleep, severe drowsiness, stroke)
        if severity == 'CRITICAL' or drowsiness_data.get('microsleep'):
            prioritized.append({
                'priority': 0,
                'level': 'P0_CRITICAL',
                'message': '🚨 NGUY HIỂM: NGỦ GẬT!',
                'sound': 'alarm_critical',
                'behavior': 'microsleep'
            })
        
        if drowsiness_data.get('stroke_warning'):
            prioritized.append({
                'priority': 0,
                'level': 'P0_CRITICAL',
                'message': '🚨 BẤT ĐỐI XỨNG MẶT - KIỂM TRA SỨC KHỎE!',
                'sound': 'alarm_critical',
                'behavior': 'stroke'
            })
        
        # Check P0/P1 - HIGH severity drowsiness
        if severity == 'HIGH' and not drowsiness_data.get('microsleep'):
            prioritized.append({
                'priority': 0,
                'level': 'P0_CRITICAL',
                'message': '😴 RẤT BUỒN NGỦ - HÃY NGHỈ NGƠI!',
                'sound': 'alarm_critical',
                'behavior': 'drowsy_severe'
            })
        
        # Check P1 - High (phone, extreme yaw)
        if behaviors.get('phone', {}).get('detected'):
            prioritized.append({
                'priority': 1,
                'level': 'P1_HIGH',
                'message': '📱 YÊU CẦU TẬP TRUNG LÁI XE!',
                'sound': 'voice_warning',
                'behavior': 'phone'
            })
        
        if behaviors.get('looking_away', {}).get('duration', 0) > 2.0:
            prioritized.append({
                'priority': 1,
                'level': 'P1_HIGH', 
                'message': '👀 YÊU CẦU NHÌN ĐƯỜNG!',
                'sound': 'voice_warning',
                'behavior': 'yaw_extreme'
            })
        
        # Check P2 - Medium (yawning, drinking)
        if behaviors.get('drowsiness', {}).get('yawning'):
            prioritized.append({
                'priority': 2,
                'level': 'P2_MEDIUM',
                'message': '😴 BẠN CÓ VẺ MỆT, HÃY NGHỈ NGƠI',
                'sound': 'ping_soft',
                'behavior': 'yawning'
            })
        
        if behaviors.get('drinking', {}).get('detected'):
            prioritized.append({
                'priority': 2,
                'level': 'P2_MEDIUM',
                'message': '🥤 HÃY TẬP TRUNG LÁI XE',
                'sound': 'ping_soft',
                'behavior': 'drinking'
            })
        
        if behaviors.get('smoking', {}).get('detected'):
            prioritized.append({
                'priority': 2,
                'level': 'P2_MEDIUM',
                'message': '🚬 KHÔNG NÊN HÚT THUỐC KHI LÁI XE',
                'sound': 'ping_soft',
                'behavior': 'smoking'
            })
        
        # Check P3 - Low (no seatbelt)
        if not behaviors.get('seatbelt', {}).get('detected', True):
            prioritized.append({
                'priority': 3,
                'level': 'P3_LOW',
                'message': '⚠️ VUI LÒNG THẮT DÂY AN TOÀN',
                'sound': 'none',
                'behavior': 'no_seatbelt'
            })
        
        # Sort by priority (lower = more urgent)
        prioritized.sort(key=lambda x: x['priority'])
        
        return prioritized
    
    # ==================== MAIN PIPELINE ====================
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Pipeline xử lý hoàn chỉnh — OPTIMIZED.
        
        Performance optimizations:
        1. Parallel YOLO: Object + Pose chạy đồng thời trên GPU
        2. Inference stride: YOLO chỉ chạy mỗi N frame, reuse kết quả
        3. FP16: Cả 2 model YOLO chạy half-precision
        4. Face mesh downscale: MediaPipe xử lý ở nửa resolution
        5. Overlay stride: Dashboard PIL chỉ render mỗi N frame
        
        Returns:
            Dictionary chứa tất cả metrics và results
        """
        start_time = time.time()
        self.frame_count += 1
        h, w = frame.shape[:2]
        
        # ===== STRIDE CHECK: Run YOLO every N frames =====
        run_yolo = (self.frame_count % self.INFER_STRIDE == 1) or self._cached_pose is None
        
        if run_yolo:
            # ===== 1+2. PARALLEL: Object + Pose Detection (concurrent GPU) =====
            fut_obj = self._infer_pool.submit(self.detect_objects, frame)
            fut_pose = self._infer_pool.submit(self.detect_pose, frame)
            objects = fut_obj.result()
            pose = fut_pose.result()
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            # Cache for stride-skipped frames
            self._cached_objects = objects
            self._cached_pose = pose
        else:
            # Reuse cached YOLO results
            objects = self._cached_objects
            pose = self._cached_pose
        
        # ===== 3. Face Mesh + EAR (MediaPipe, downscaled) =====
        if self.FACE_MESH_SCALE < 1.0 and self.enable_face_mesh:
            small = cv2.resize(frame, (int(w * self.FACE_MESH_SCALE), int(h * self.FACE_MESH_SCALE)))
            face_result = self.process_face_mesh(small)
        else:
            face_result = self.process_face_mesh(frame)
        ear = face_result['ear']
        eyes_open = face_result['eyes_open']
        yawning = face_result['yawning']
        face_landmarks = face_result['face_landmarks']
        
        # ===== 4. Head Pose Estimation =====
        head_pose = self.estimate_head_pose(pose) if self.enable_head_pose and pose else {
            'yaw': 0, 'pitch': 0, 'roll': 0, 'is_valid': False
        }
        
        # ===== 5. Behavior Analysis =====
        warnings = []
        behaviors = {}
        
        # Phone
        using_phone, phone_msg, phone_conf = self.check_phone_use(objects, pose, (h, w))
        if using_phone:
            warnings.append(phone_msg)
        behaviors['phone'] = {'detected': using_phone, 'confidence': phone_conf}
        
        # Drinking
        drinking, drink_msg, drink_conf = self.check_drinking(objects, pose, (h, w))
        if drinking:
            warnings.append(drink_msg)
        behaviors['drinking'] = {'detected': drinking, 'confidence': drink_conf}
        
        # Smoking
        smoking, smoke_msg, smoke_conf = self.check_smoking(pose)
        if smoking:
            warnings.append(smoke_msg)
        behaviors['smoking'] = {'detected': smoking, 'confidence': smoke_conf}
        
        # ===== 6. ENHANCED Drowsiness Detection =====
        # Priority: Microsleep > Drowsy Eyes > Yawning > PERCLOS > Head-based
        drowsy = False
        drowsy_msg = ""
        drowsy_severity = "NONE"
        drowsy_conf = 0.0
        
        # Get new signals from face_result
        microsleep = face_result.get('microsleep', False)
        microsleep_duration = face_result.get('microsleep_duration_ms', 0)
        drowsy_eyes = face_result.get('drowsy_eyes', False)
        drowsy_eyes_duration = face_result.get('drowsy_eyes_duration', 0.0)
        long_blink = face_result.get('long_blink', False)
        stroke_warning = face_result.get('stroke_warning', False)
        yawn_duration = face_result.get('yawn_duration', 0.0)
        
        # ===== P0: MICROSLEEP - Most dangerous! =====
        if microsleep:
            drowsy = True
            if microsleep_duration >= getattr(self, 'MICROSLEEP_DANGER_MS', 1500):
                drowsy_msg = f"🚨 NGUY HIỂM: NGỦ GẬT {microsleep_duration/1000:.1f}s!"
                drowsy_severity = "CRITICAL"
            else:
                drowsy_msg = f"⚠️ MICRO-SLEEP: Mắt nhắm {microsleep_duration}ms!"
                drowsy_severity = "HIGH"
            drowsy_conf = min(1.0, microsleep_duration / 2000)
        
        # ===== P1: DROWSY EYES (Mắt lờ đờ) =====
        elif drowsy_eyes:
            drowsy = True
            drowsy_msg = f"😴 MẮT LỜ ĐỜ: EAR thấp trong {drowsy_eyes_duration:.1f}s"
            drowsy_severity = "HIGH"
            drowsy_conf = min(1.0, drowsy_eyes_duration / 3.0)
        
        # ===== P2: Long blink warning =====
        elif long_blink and not drowsy:
            # Long blinks (400-800ms) are warning signs
            drowsy = True
            drowsy_msg = "⚠️ CHỚP MẮT DÀI - Dấu hiệu mệt mỏi"
            drowsy_severity = "MEDIUM"
            drowsy_conf = 0.6
        
        # ===== P2: YAWNING Detection =====
        if yawning and not drowsy:
            drowsy = True
            if yawn_duration > 2.0:
                drowsy_msg = f"😴 NGÁP DÀI {yawn_duration:.1f}s - Rất mệt mỏi!"
                drowsy_severity = "HIGH"
                drowsy_conf = 0.85
            else:
                drowsy_msg = "😴 PHÁT HIỆN NGÁP - Dấu hiệu mệt mỏi"
                drowsy_severity = "MEDIUM"
                drowsy_conf = 0.7
        
        # ===== P3: PERCLOS Check =====
        perclos = self.get_perclos()
        perclos_danger = getattr(self, 'PERCLOS_DANGER', 0.25)
        
        if not drowsy:
            if perclos > perclos_danger:
                drowsy = True
                drowsy_msg = f"🚨 PERCLOS CAO: {perclos*100:.0f}% - Rất buồn ngủ!"
                drowsy_severity = "HIGH"
                drowsy_conf = min(1.0, perclos * 2)
            elif perclos > self.PERCLOS_THRESHOLD:
                drowsy = True
                drowsy_msg = f"😴 PERCLOS: {perclos*100:.0f}% - Dấu hiệu buồn ngủ"
                drowsy_severity = "MEDIUM"
                drowsy_conf = perclos
        
        # ===== P3: Eye closure duration (fallback) =====
        if not drowsy and not eyes_open and self.eyes_closed_start_time:
            eyes_closed_duration = time.time() - self.eyes_closed_start_time
            if eyes_closed_duration >= self.EAR_DROWSY_TIME:
                drowsy = True
                drowsy_msg = f"😴 MẮT NHẮM QUÁ LÂU ({eyes_closed_duration:.1f}s)!"
                drowsy_severity = "HIGH"
                drowsy_conf = min(1.0, eyes_closed_duration / 3.0)
        
        # ===== P4: Head-based drowsiness (fallback) =====
        if not drowsy:
            head_drowsy, head_drowsy_msg, head_severity, head_conf = self.check_drowsiness(pose, head_pose)
            if head_drowsy:
                drowsy = True
                drowsy_msg = head_drowsy_msg
                drowsy_severity = head_severity
                drowsy_conf = head_conf
        
        # ===== STROKE Warning (separate from drowsiness) =====
        if stroke_warning:
            warnings.append("🚨 CẢNH BÁO: Bất đối xứng khuôn mặt - Kiểm tra sức khỏe!")
        
        if drowsy:
            warnings.append(drowsy_msg)
        behaviors['drowsiness'] = {
            'detected': drowsy,
            'severity': drowsy_severity,
            'confidence': drowsy_conf,
            'ear': ear,
            'eyes_open': eyes_open,
            'perclos': perclos,
            'yawning': yawning,
            'blinks': self.total_blinks,
            # NEW: Enhanced drowsiness signals
            'microsleep': microsleep,
            'microsleep_duration_ms': microsleep_duration,
            'drowsy_eyes': drowsy_eyes,
            'drowsy_eyes_duration': drowsy_eyes_duration,
            'long_blink': long_blink,
            'stroke_warning': stroke_warning,
            'yawn_duration': yawn_duration,
            'microsleep_count': getattr(self, 'microsleep_count', 0),
            'long_blink_count': getattr(self, 'long_blink_count', 0),
        }
        
        # Looking away
        looking_away, away_msg, away_duration = self.check_looking_away(head_pose)
        if looking_away:
            warnings.append(away_msg)
        behaviors['looking_away'] = {'detected': looking_away, 'duration': away_duration}
        
        # ===== 6b. Seatbelt Detection =====
        seatbelt_on, seatbelt_msg, seatbelt_conf = self.check_seatbelt(frame, pose)
        if not seatbelt_on and seatbelt_msg:
            warnings.append(seatbelt_msg)
        
        # Get actual seatbelt status for behaviors dict
        seatbelt_status = getattr(self, 'seatbelt_status', 'unknown')
        behaviors['seatbelt'] = {
            'detected': seatbelt_on,
            'wearing': seatbelt_on and seatbelt_conf >= 0.5,  # Only if confident
            'status': seatbelt_status,  # 'wearing', 'not_wearing', 'checking', 'unknown'
            'confidence': seatbelt_conf,
            'warning_active': not seatbelt_on and seatbelt_conf >= 0.5
        }
        
        # ===== 7. Attention Score =====
        attention_score = self.calculate_attention_score_v2(
            head_pose, using_phone, drinking, smoking, eyes_open, ear
        )
        distraction_level = self.get_distraction_level(attention_score)
        
        # ===== 7.5 Stabilize warnings (anti-flicker) =====
        # Keep warnings displayed for at least WARNING_PERSIST_TIME seconds
        # so they don't flash on/off rapidly between frames
        warnings = self._stabilize_warnings(warnings)
        
        # ===== 8. Priority-based Warnings =====
        prioritized_warnings = self.prioritize_warnings(warnings, behaviors)
        
        # Get highest priority warning
        highest_priority = None
        if prioritized_warnings:
            highest_priority = prioritized_warnings[0]
            self.last_warning_priority = highest_priority['priority']
        else:
            self.last_warning_priority = 99
        
        # ===== 9. Draw Overlays (with stride caching) =====
        annotated_frame = frame.copy()
        
        do_full_overlay = (
            (self.frame_count % self.OVERLAY_STRIDE == 1)
            or self._cached_dashboard_frame is None
        )
        
        # Draw Face Mesh (lightweight — just lines on cv2)
        if face_result['face_detected'] and self.enable_face_mesh:
            annotated_frame = self.draw_face_mesh(
                annotated_frame, face_landmarks, ear, eyes_open
            )
        
        # Draw Detection Bounding Boxes (cv2 — fast)
        annotated_frame = self.draw_detection_boxes(
            annotated_frame, behaviors, prioritized_warnings
        )
        
        if do_full_overlay:
            # FULL RENDER: Seatbelt + Pose + Dashboard (heavy PIL ops)
            if pose:
                annotated_frame = self.draw_seatbelt_status(annotated_frame, pose, seatbelt_on, seatbelt_conf)
            if pose:
                annotated_frame = self.draw_pose_overlay(annotated_frame, pose, head_pose)
            annotated_frame = self.draw_dashboard_v2(
                annotated_frame, warnings, attention_score, head_pose,
                distraction_level, ear, eyes_open, self.total_blinks, perclos,
                seatbelt_on, seatbelt_conf
            )
            # Cache the overlay portion for reuse
            self._cached_overlay_results = {
                'warnings': warnings,
                'attention_score': attention_score,
                'head_pose': head_pose,
                'distraction_level': distraction_level,
                'ear': ear,
                'eyes_open': eyes_open,
                'seatbelt_on': seatbelt_on,
                'seatbelt_conf': seatbelt_conf,
            }
        else:
            # FAST PATH: Reuse cached dashboard — only draw lightweight cv2 overlays
            cr = self._cached_overlay_results
            if cr and pose:
                annotated_frame = self.draw_seatbelt_status(annotated_frame, pose, cr.get('seatbelt_on', False), cr.get('seatbelt_conf', 0.0))
                annotated_frame = self.draw_pose_overlay(annotated_frame, pose, cr.get('head_pose', {}))
            annotated_frame = self.draw_dashboard_v2(
                annotated_frame, 
                cr.get('warnings', []) if cr else warnings,
                cr.get('attention_score', 100) if cr else attention_score,
                cr.get('head_pose', head_pose) if cr else head_pose,
                cr.get('distraction_level', 'LOW') if cr else distraction_level,
                cr.get('ear', 0.3) if cr else ear,
                cr.get('eyes_open', True) if cr else eyes_open,
                self.total_blinks,
                perclos,
                cr.get('seatbelt_on', False) if cr else seatbelt_on,
                cr.get('seatbelt_conf', 0.0) if cr else seatbelt_conf
            )
        
        # ===== 10. FPS & State =====
        process_time = time.time() - start_time
        self.fps_buffer.append(1.0 / max(process_time, 0.001))
        avg_fps = np.mean(list(self.fps_buffer)[-10:])
        
        # Determine driver state for backward compatibility
        if drowsy:
            driver_state = 'drowsy'
            driver_confidence = drowsy_conf
        elif using_phone:
            driver_state = 'distracted'
            driver_confidence = phone_conf
        elif looking_away:
            driver_state = 'looking_away'
            driver_confidence = min(1.0, away_duration / 3.0)
        elif drinking or smoking:
            driver_state = 'distracted'
            driver_confidence = max(drink_conf, smoke_conf)
        else:
            driver_state = 'normal'
            driver_confidence = attention_score / 100.0
        
        return {
            # Core results
            'annotated_frame': annotated_frame,
            'warnings': warnings,
            'is_safe': len(warnings) == 0,
            
            # Priority Matrix results
            'prioritized_warnings': prioritized_warnings,
            'highest_priority': highest_priority,
            'warning_sound': highest_priority['sound'] if highest_priority else 'none',
            
            # Backward compatibility fields
            'state': driver_state,
            'confidence': driver_confidence,
            
            # PRO features
            'behaviors': behaviors,
            'head_pose': head_pose,
            'attention_score': attention_score,
            'distraction_level': distraction_level,
            
            # Face Mesh / EAR data
            'ear': ear,
            'eyes_open': eyes_open,
            'blinks': self.total_blinks,
            'perclos': round(perclos, 3),
            'yawning': yawning,
            
            # Seatbelt
            'seatbelt': seatbelt_on,
            
            # Individual flags (backward compat)
            'using_phone': using_phone,
            'drinking': drinking,
            'smoking': smoking,
            'drowsy': drowsy,
            'looking_away': looking_away,
            
            # Detected objects with bounding boxes
            'detected_objects': objects,
            'detection_boxes': self.detection_boxes,
            
            # Metadata
            'objects_detected': len(objects),
            'pose_detected': pose is not None,
            'face_detected': face_result['face_detected'],
            'fps': round(avg_fps, 1),
            'frame_number': self.frame_count,
        }
    
    def calculate_attention_score_v2(
        self,
        head_pose: Dict,
        using_phone: bool,
        drinking: bool,
        smoking: bool,
        eyes_open: bool,
        ear: float
    ) -> int:
        """
        Tính Attention Score V2 với EAR.
        """
        score = 0
        
        if not self.enable_attention:
            return 100
        
        # 1. Head forward (30 points)
        if head_pose['is_valid']:
            yaw = abs(head_pose['yaw'])
            if yaw < 15:
                score += 30
            elif yaw < self.YAW_THRESHOLD:
                score += int(30 * (1 - (yaw - 15) / (self.YAW_THRESHOLD - 15)))
        else:
            score += 15
        
        # 2. Head level (15 points)
        if head_pose['is_valid']:
            pitch = abs(head_pose['pitch'])
            if pitch < 10:
                score += 15
            elif pitch < self.PITCH_THRESHOLD:
                score += int(15 * (1 - (pitch - 10) / (self.PITCH_THRESHOLD - 10)))
        else:
            score += 7
        
        # 3. Eyes open - EAR based (35 points)
        if eyes_open:
            # Scale by how open the eyes are
            if ear >= 0.25:
                score += 35
            elif ear >= self.EAR_THRESHOLD:
                score += int(35 * (ear - self.EAR_THRESHOLD) / (0.25 - self.EAR_THRESHOLD))
        else:
            score += 5  # Eyes closed = very low attention
        
        # 4. No distractions (20 points)
        if not using_phone and not drinking and not smoking:
            score += 20
        elif not using_phone:
            score += 10
        
        # Clamp and smooth
        score = max(0, min(100, score))
        self.attention_history.append(score)
        if len(self.attention_history) >= 5:
            score = int(np.mean(list(self.attention_history)[-15:]))
        
        self.current_attention_score = score
        return score
    
    def draw_dashboard_v2(
        self,
        frame: np.ndarray,
        warnings: List[str],
        attention_score: int,
        head_pose: Dict,
        distraction_level: str,
        ear: float,
        eyes_open: bool,
        blinks: int,
        perclos: float,
        seatbelt_on: bool = False,
        seatbelt_conf: float = 0.0
    ) -> np.ndarray:
        """
        Vẽ dashboard V2 PRO - Layout rõ ràng, đầy đủ thông số.
        """
        h, w = frame.shape[:2]
        frame = frame.copy()
        
        # Modern color scheme
        DASHBOARD_COLORS = {
            'LOW': ((80, 200, 120), (120, 255, 150)),       # Green
            'MEDIUM': ((0, 180, 255), (50, 220, 255)),      # Yellow-Orange  
            'HIGH': ((0, 100, 255), (50, 150, 255)),        # Orange
            'CRITICAL': ((0, 0, 200), (50, 50, 255)),       # Deep Red (BGR)
        }
        
        colors = DASHBOARD_COLORS.get(distraction_level, DASHBOARD_COLORS['LOW'])
        main_color = colors[0]
        glow_color = colors[1]
        
        # ===== Warning Banner (top) =====
        if warnings:
            banner_height = 50 + 45 * len(warnings)
            frame = self._draw_gradient_rect(
                frame, (0, 0), (w, banner_height),
                (10, 10, 30), (20, 15, 50), 'vertical', alpha=0.92
            )
            cv2.line(frame, (0, banner_height), (w, banner_height), (30, 30, 220), 2)
        
        # ===== Main Dashboard Panel (bottom-left) - LARGER =====
        panel_w, panel_h = 320, 220
        panel_x, panel_y = 10, h - panel_h - 10
        
        # Glass panel background
        frame = self._draw_glass_panel(
            frame,
            (panel_x, panel_y),
            (panel_x + panel_w, panel_y + panel_h),
            base_color=(20, 20, 30),
            alpha=0.88,
            border_color=(60, 60, 80)
        )
        
        # Header bar
        frame = self._draw_rounded_rect(
            frame,
            (panel_x + 8, panel_y + 8),
            (panel_x + panel_w - 8, panel_y + 38),
            main_color, radius=6, alpha=0.8
        )
        
        # ===== Gauge (inline với header) =====
        gauge_cx = panel_x + panel_w - 50
        gauge_cy = panel_y + 23
        gauge_r = 18
        
        # Simple gauge arc
        cv2.ellipse(frame, (gauge_cx, gauge_cy), (gauge_r, gauge_r), 0, 0, 360, (50, 50, 60), 2)
        arc_end = int(attention_score * 3.6)
        cv2.ellipse(frame, (gauge_cx, gauge_cy), (gauge_r, gauge_r), -90, 0, arc_end, glow_color, 3)
        
        # ===== Convert to PIL for text =====
        frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(frame_pil)
        
        # Warning text
        if warnings:
            y = 15
            for warning in warnings:
                if self.font_large:
                    draw.text((25, y), warning, fill=(255, 255, 255), font=self.font_large)
                y += 45
        
        # Dashboard title + score
        if self.font_medium:
            draw.text((panel_x + 15, panel_y + 12), "GIÁM SÁT TÀI XẾ PRO",
                     fill=(255, 255, 255), font=self.font_medium)
        
        # Score number in gauge
        if self.font_small:
            score_str = str(attention_score)
            draw.text((gauge_cx - 8, gauge_cy - 8), score_str,
                     fill=(255, 255, 255), font=self.font_small)
        
        # === Metrics Layout (2 columns) ===
        left_x = panel_x + 15
        right_x = panel_x + 170
        row_h = 28
        start_y = panel_y + 48
        
        # Row 1: Status + Level
        status_vn = {'LOW': 'AN TOÀN', 'MEDIUM': 'CHÚ Ý', 'HIGH': 'RỦI RO', 'CRITICAL': 'NGUY HIỂM'}
        if self.font_medium:
            draw.text((left_x, start_y), "Trạng thái:", fill=(180, 180, 180), font=self.font_small)
            draw.text((left_x + 75, start_y), status_vn.get(distraction_level, distraction_level),
                     fill=glow_color[::-1], font=self.font_medium)
        
        # Row 2: Eye status
        row2_y = start_y + row_h
        eye_status = "MẮT MỞ" if eyes_open else "MẮT NHẮM"
        eye_color = (150, 255, 150) if eyes_open else (255, 100, 100)
        if self.font_small:
            draw.text((left_x, row2_y), "Mắt:", fill=(180, 180, 180), font=self.font_small)
            draw.text((left_x + 40, row2_y), eye_status, fill=eye_color, font=self.font_small)
            draw.text((right_x, row2_y), f"EAR: {ear:.2f}", fill=(200, 200, 200), font=self.font_small)
        
        # Row 3: Blinks + PERCLOS
        row3_y = start_y + row_h * 2
        perclos_color = (150, 255, 150) if perclos < 0.15 else (255, 150, 100)
        if self.font_small:
            draw.text((left_x, row3_y), f"Chớp mắt: {blinks}", fill=(200, 200, 200), font=self.font_small)
            draw.text((right_x, row3_y), f"PERCLOS: {perclos*100:.1f}%", fill=perclos_color, font=self.font_small)
        
        # Row 4: Seatbelt - REALISTIC display based on confidence
        row4_y = start_y + row_h * 3
        
        # Get actual seatbelt status from instance
        seatbelt_status = getattr(self, 'seatbelt_status', 'unknown')
        
        # Determine display text and color based on ACTUAL detection
        if seatbelt_status == 'wearing' and seatbelt_conf >= 0.5:
            # Confirmed detection of seatbelt
            seatbelt_text = "ĐÃ THẮT"
            seatbelt_color = (150, 255, 150)  # Green
            indicator = "✓"
        elif seatbelt_status == 'not_wearing' and seatbelt_conf >= 0.5:
            # Confirmed NO seatbelt
            seatbelt_text = "KHÔNG CÓ!"
            seatbelt_color = (255, 100, 100)  # Red
            indicator = "✗"
        elif seatbelt_status == 'checking':
            # Still checking
            seatbelt_text = "ĐANG KIỂM TRA..."
            seatbelt_color = (255, 200, 100)  # Yellow
            indicator = "○"
        else:
            # Unknown / Not in driving scenario (e.g., TikTok video)
            seatbelt_text = "KHÔNG PHÁT HIỆN"
            seatbelt_color = (150, 150, 150)  # Gray
            indicator = "?"
        if self.font_small:
            draw.text((left_x, row4_y), f"Dây an toàn: {indicator} {seatbelt_text}",
                     fill=seatbelt_color, font=self.font_small)
        
        # Row 5: Head pose
        row5_y = start_y + row_h * 4
        if head_pose['is_valid'] and self.font_small:
            yaw_dir = "←" if head_pose['yaw'] < -15 else ("→" if head_pose['yaw'] > 15 else "↑")
            draw.text((left_x, row5_y), f"Đầu: {yaw_dir} Y={head_pose['yaw']:+.0f} P={head_pose['pitch']:+.0f}",
                     fill=(150, 150, 170), font=self.font_small)
        
        # Row 6: Attention score bar
        row6_y = start_y + row_h * 5
        if self.font_small:
            draw.text((left_x, row6_y), f"Tập trung: {attention_score}%",
                     fill=glow_color[::-1], font=self.font_small)
        
        # ===== Vertical Attention Bar (right side) =====
        frame = cv2.cvtColor(np.array(frame_pil), cv2.COLOR_RGB2BGR)
        
        bar_w, bar_h = 20, 120
        bar_x = w - bar_w - 20
        bar_y = h - bar_h - 25
        
        # Bar background
        frame = self._draw_rounded_rect(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h),
                                        (35, 35, 45), radius=10, alpha=0.85)
        
        # Filled portion
        fill_h = int((bar_h - 6) * attention_score / 100)
        fill_y = bar_y + bar_h - fill_h - 3
        
        if fill_h > 0:
            frame = self._draw_rounded_rect(
                frame, (bar_x + 3, fill_y), (bar_x + bar_w - 3, bar_y + bar_h - 3),
                main_color, radius=7, alpha=0.95
            )
        
        # Score label
        frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(frame_pil)
        if self.font_medium:
            draw.text((bar_x - 5, bar_y - 30), f"{attention_score}%", fill=glow_color[::-1], font=self.font_medium)
        
        return cv2.cvtColor(np.array(frame_pil), cv2.COLOR_RGB2BGR)
    
    def get_status(self) -> Dict:
        """Get current monitor status."""
        return {
            'attention_score': self.current_attention_score,
            'distraction_level': self.current_distraction_level,
            'ear': self.current_ear,
            'blinks': self.total_blinks,
            'perclos': self.get_perclos(),
            'is_calibrated': self.is_calibrated,
            'frame_count': self.frame_count,
            'device': self.device,
            'face_mesh_enabled': self.enable_face_mesh,
        }


# Backward compatibility alias
DriverMonitorV11 = DriverMonitorV11Pro


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("DRIVER MONITOR V11 PRO - Test")
    print("=" * 60)
    
    try:
        monitor = DriverMonitorV11Pro(device="cuda")
        print("✅ Driver Monitor PRO khởi tạo thành công!")
        print(f"   Status: {monitor.get_status()}")
    except Exception as e:
        print(f"❌ Lỗi: {e}")
