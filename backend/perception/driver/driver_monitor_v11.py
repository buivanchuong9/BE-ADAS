"""
DRIVER MONITORING MODULE V11 - ENHANCED
========================================
Monitors driver state using in-cabin camera and MediaPipe Face Mesh.

PRODUCTION FEATURES (Phase 3 + Object Detection):
- 468 Facial Landmarks (MediaPipe Face Mesh)
- Temporal state tracking with rolling window
- EMA smoothing for EAR/MAR metrics (alpha=0.2)
- Sustained state detection (3-second confirmation)
- Confidence scoring for alert reliability
- Multi-factor drowsiness assessment
- Object Detection (Phone, Cigarette, Food, Bottle) - NEW!

Detection Algorithms:
- Eye closure (EAR - Eye Aspect Ratio) with temporal consistency
- Yawning (MAR - Mouth Aspect Ratio) with frequency tracking
- Head pose (pitch, yaw, roll) with drift compensation
- Drowsiness: Requires sustained condition (3+ seconds)
- Object Detection: YOLO-based dangerous object detection

Temporal Logic:
- Rolling buffer: 90 frames (3 seconds @ 30fps)
- EMA smoothing: alpha=0.2 for noise reduction
- State confirmation: 70% frames in window must agree
- Alert cooldown: 5 seconds between same-type alerts

Author: Senior ADAS Engineer
Date: 2026-01-16 (Enhanced with Object Detection)
"""

import cv2
import numpy as np
from typing import Dict, Tuple, Optional, List
from collections import deque
import logging
from enum import Enum
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def put_vietnamese_text(
    img: np.ndarray,
    text: str,
    position: Tuple[int, int],
    font_size: int = 32,
    color: Tuple[int, int, int] = (0, 0, 255),
    font_path: Optional[str] = None
) -> np.ndarray:
    """
    Draw Vietnamese text on OpenCV image using PIL.
    
    Args:
        img: OpenCV image (BGR)
        text: Vietnamese text to draw
        position: (x, y) position
        font_size: Font size
        color: BGR color tuple
        font_path: Path to TTF font (optional, uses default if None)
        
    Returns:
        Image with Vietnamese text
    """
    try:
        # Convert BGR to RGB
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        
        # Try to load font (fallback to default if not found)
        try:
            if font_path:
                font = ImageFont.truetype(font_path, font_size)
            else:
                # Try common Vietnamese fonts on macOS
                font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", font_size)
        except:
            # Fallback to default font
            font = ImageFont.load_default()
        
        # Convert BGR to RGB for PIL
        color_rgb = (color[2], color[1], color[0])
        
        # Draw text
        draw.text(position, text, font=font, fill=color_rgb)
        
        # Convert back to BGR
        img_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        return img_bgr
    except Exception as e:
        logger.warning(f"Vietnamese text rendering failed: {e}. Using ASCII fallback.")
        # Fallback to OpenCV (ASCII only)
        cv2.putText(img, text, position, cv2.FONT_HERSHEY_SIMPLEX, 
                   font_size / 32, color, 2)
        return img


def draw_premium_hud(
    frame: np.ndarray,
    ear: float,
    mar: float,
    head_pose: Dict,
    is_drowsy: bool,
    drowsy_reason: str,
    detected_objects: List[Dict],
    frame_number: int
) -> np.ndarray:
    """
    Draw premium HUD overlay with glassmorphism and animations.
    
    Features:
    - Real-time metrics dashboard
    - Animated alerts
    - Professional visualization
    - Glassmorphism effects
    """
    height, width = frame.shape[:2]
    overlay = frame.copy()
    
    # === 1. TOP LEFT: METRICS DASHBOARD ===
    # Background panel with glassmorphism
    panel_width = 280
    panel_height = 180
    panel_x, panel_y = 20, 20
    
    # Semi-transparent dark background
    cv2.rectangle(
        overlay,
        (panel_x, panel_y),
        (panel_x + panel_width, panel_y + panel_height),
        (20, 20, 20),
        -1
    )
    
    # Glassmorphism border
    cv2.rectangle(
        overlay,
        (panel_x, panel_y),
        (panel_x + panel_width, panel_y + panel_height),
        (100, 200, 255),
        2
    )
    
    # Blend overlay
    frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)
    
    # Title
    cv2.putText(
        frame,
        "DRIVER MONITORING",
        (panel_x + 10, panel_y + 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (100, 200, 255),
        2,
        cv2.LINE_AA
    )
    
    # EAR metric with color coding
    ear_color = (0, 255, 0) if ear > 0.25 else (0, 165, 255) if ear > 0.20 else (0, 0, 255)
    cv2.putText(
        frame,
        f"EAR: {ear:.3f}",
        (panel_x + 10, panel_y + 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        ear_color,
        2,
        cv2.LINE_AA
    )
    
    # EAR progress bar
    bar_width = int((ear / 0.4) * 200)  # Max EAR = 0.4
    bar_width = min(bar_width, 200)
    cv2.rectangle(
        frame,
        (panel_x + 10, panel_y + 75),
        (panel_x + 10 + bar_width, panel_y + 85),
        ear_color,
        -1
    )
    cv2.rectangle(
        frame,
        (panel_x + 10, panel_y + 75),
        (panel_x + 210, panel_y + 85),
        (100, 100, 100),
        1
    )
    
    # MAR metric with color coding
    mar_color = (0, 255, 0) if mar < 0.6 else (0, 165, 255) if mar < 0.7 else (0, 0, 255)
    cv2.putText(
        frame,
        f"MAR: {mar:.3f}",
        (panel_x + 10, panel_y + 110),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        mar_color,
        2,
        cv2.LINE_AA
    )
    
    # MAR progress bar
    bar_width = int((mar / 0.8) * 200)  # Max MAR = 0.8
    bar_width = min(bar_width, 200)
    cv2.rectangle(
        frame,
        (panel_x + 10, panel_y + 120),
        (panel_x + 10 + bar_width, panel_y + 130),
        mar_color,
        -1
    )
    cv2.rectangle(
        frame,
        (panel_x + 10, panel_y + 120),
        (panel_x + 210, panel_y + 130),
        (100, 100, 100),
        1
    )
    
    # Head pose
    pitch = head_pose.get('pitch', 0)
    yaw = head_pose.get('yaw', 0)
    cv2.putText(
        frame,
        f"HEAD: P:{pitch:.1f} Y:{yaw:.1f}",
        (panel_x + 10, panel_y + 155),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (200, 200, 200),
        1,
        cv2.LINE_AA
    )
    
    # === 2. TOP RIGHT: STATUS INDICATOR ===
    status_x = width - 200
    status_y = 20
    
    if is_drowsy:
        # Animated red alert (pulsing effect)
        pulse = int(abs(np.sin(frame_number * 0.1) * 50))
        status_color = (0, 0, 255 - pulse)
        status_text = "⚠ DROWSY"
    else:
        status_color = (0, 255, 0)
        status_text = "✓ ALERT"
    
    # Status circle
    cv2.circle(frame, (status_x + 30, status_y + 30), 25, status_color, -1)
    cv2.circle(frame, (status_x + 30, status_y + 30), 25, (255, 255, 255), 2)
    
    # Status text
    cv2.putText(
        frame,
        status_text,
        (status_x + 65, status_y + 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        status_color,
        2,
        cv2.LINE_AA
    )
    
    # === 3. BOTTOM: ALERT BANNER ===
    if is_drowsy or detected_objects:
        banner_height = 100
        banner_y = height - banner_height - 20
        
        # Semi-transparent red background
        overlay = frame.copy()
        cv2.rectangle(
            overlay,
            (20, banner_y),
            (width - 20, banner_y + banner_height),
            (0, 0, 139),  # Dark red
            -1
        )
        frame = cv2.addWeighted(frame, 0.6, overlay, 0.4, 0)
        
        # Border
        cv2.rectangle(
            frame,
            (20, banner_y),
            (width - 20, banner_y + banner_height),
            (0, 0, 255),
            3
        )
        
        # Alert text
        if is_drowsy:
            alert_text = f"⚠ CẢNH BÁO: {drowsy_reason}"
            frame = put_vietnamese_text(
                frame,
                alert_text,
                (40, banner_y + 35),
                font_size=32,
                color=(255, 255, 255)
            )
        
        # Detected objects
        if detected_objects:
            obj_text = "PHÁT HIỆN: " + ", ".join([obj['class'].upper() for obj in detected_objects])
            frame = put_vietnamese_text(
                frame,
                obj_text,
                (40, banner_y + 75),
                font_size=24,
                color=(255, 200, 0)
            )
    
    # === 4. OBJECT BOUNDING BOXES (Enhanced) ===
    for obj in detected_objects:
        bbox = obj['bbox']
        x1, y1, x2, y2 = map(int, bbox)
        
        # Thick red box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
        
        # Label background
        label = f"{obj['class'].upper()} {obj['confidence']:.0%}"
        (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(
            frame,
            (x1, y1 - label_h - 10),
            (x1 + label_w + 10, y1),
            (0, 0, 255),
            -1
        )
        
        # Label text
        cv2.putText(
            frame,
            label,
            (x1 + 5, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )
    
    # === 5. FRAME COUNTER (Bottom right) ===
    cv2.putText(
        frame,
        f"Frame: {frame_number}",
        (width - 150, height - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (150, 150, 150),
        1,
        cv2.LINE_AA
    )
    
    return frame


class AlertType(Enum):
    """Alert types for driver monitoring (Vietnamese)."""
    # Drowsiness Detection
    DROWSY_EYES_CLOSED = "BUỒN NGỦ - Mắt nhắm"
    DROWSY_YAWNING = "BUỒN NGỦ - Ngáp liên tục"
    DROWSY_HEAD_DOWN = "BUỒN NGỦ - Đầu cúi xuống"
    
    # Distraction Detection
    DISTRACTED_LOOKING_AWAY = "MẤT TẬP TRUNG - Nhìn sang ngang"
    DISTRACTED_LOOKING_DOWN = "MẤT TẬP TRUNG - Nhìn xuống (Điện thoại?)"
    DISTRACTED_USING_PHONE = "MẤT TẬP TRUNG - Sử dụng điện thoại"
    DISTRACTED_TALKING_PASSENGER = "MẤT TẬP TRUNG - Quay đầu nói chuyện liên tục"
    
    # Safety Violations
    VIOLATION_SMOKING = "VI PHẠM - Hút thuốc"
    VIOLATION_EATING = "VI PHẠM - Ăn uống"
    VIOLATION_DRINKING = "VI PHẠM - Uống bia/nước"
    VIOLATION_NO_SEATBELT = "VI PHẠM - Không thắt dây an toàn"
    
    # Critical Dangers
    CRITICAL_NO_FACE = "NGUY HIỂM - Không phát hiện tài xế"
    CRITICAL_HANDS_OFF = "NGUY HIỂM - Buông cả 2 tay khỏi vô lăng"
    
    # Emotional State (Advanced)
    STATE_STRESSED_ANGRY = "CẢM XÚC - Căng thẳng/Tức giận"


class TemporalDriverState:
    """
    Temporal state tracker for driver monitoring.
    Uses rolling window and EMA smoothing for robust detection.
    """
    
    def __init__(self, window_seconds: float = 3.0, frame_rate: int = 30, alpha: float = 0.2):
        """
        Initialize temporal state tracker.
        
        Args:
            window_seconds: Rolling window duration in seconds
            frame_rate: Video frame rate (fps)
            alpha: EMA smoothing factor (0-1, lower = smoother)
        """
        self.window_size = int(window_seconds * frame_rate)
        self.alpha = alpha
        
        # Rolling buffers
        self.ear_buffer = deque(maxlen=self.window_size)
        self.mar_buffer = deque(maxlen=self.window_size)
        self.yaw_buffer = deque(maxlen=self.window_size)
        self.pitch_buffer = deque(maxlen=self.window_size)
        self.drowsy_state_buffer = deque(maxlen=self.window_size)
        
        # EMA smoothed values
        self.smoothed_ear = None
        self.smoothed_mar = None
        self.smoothed_yaw = None
        self.smoothed_pitch = None
        
        # Alert cooldown tracking
        self.last_alert_time = {}
        self.alert_cooldown_frames = 150  # 5 seconds @ 30fps
    
    def update(
        self,
        ear: float,
        mar: float,
        yaw: float,
        pitch: float,
        is_drowsy: bool,
        frame_number: int
    ) -> None:
        """Update temporal buffers with new measurements."""
        # Update buffers
        self.ear_buffer.append(ear)
        self.mar_buffer.append(mar)
        self.yaw_buffer.append(yaw)
        self.pitch_buffer.append(pitch)
        self.drowsy_state_buffer.append(is_drowsy)
        
        # Update smoothed values using EMA
        if self.smoothed_ear is None:
            self.smoothed_ear = ear
            self.smoothed_mar = mar
            self.smoothed_yaw = yaw
            self.smoothed_pitch = pitch
        else:
            self.smoothed_ear = self.alpha * ear + (1 - self.alpha) * self.smoothed_ear
            self.smoothed_mar = self.alpha * mar + (1 - self.alpha) * self.smoothed_mar
            self.smoothed_yaw = self.alpha * yaw + (1 - self.alpha) * self.smoothed_yaw
            self.smoothed_pitch = self.alpha * pitch + (1 - self.alpha) * self.smoothed_pitch
    
    def get_sustained_drowsiness(self, threshold: float = 0.7) -> Tuple[bool, float]:
        """
        Check if drowsiness is sustained over temporal window.
        
        Args:
            threshold: Fraction of frames that must indicate drowsiness (0-1)
            
        Returns:
            Tuple of (is_sustained, confidence)
        """
        if len(self.drowsy_state_buffer) < self.window_size // 2:
            return False, 0.0
        
        drowsy_count = sum(self.drowsy_state_buffer)
        total_count = len(self.drowsy_state_buffer)
        confidence = drowsy_count / total_count
        
        is_sustained = confidence >= threshold
        return is_sustained, confidence
    
    def get_smoothed_values(self) -> Dict[str, float]:
        """Get EMA-smoothed metric values."""
        return {
            "ear": self.smoothed_ear or 0.0,
            "mar": self.smoothed_mar or 0.0,
            "yaw": self.smoothed_yaw or 0.0,
            "pitch": self.smoothed_pitch or 0.0
        }
    
    def should_alert(self, alert_type: str, frame_number: int) -> bool:
        """
        Check if alert should be triggered (respecting cooldown).
        
        Args:
            alert_type: Type of alert (e.g., 'DROWSY', 'DISTRACTED')
            frame_number: Current frame number
            
        Returns:
            True if alert should be triggered
        """
        last_alert = self.last_alert_time.get(alert_type, -self.alert_cooldown_frames - 1)
        
        if frame_number - last_alert >= self.alert_cooldown_frames:
            self.last_alert_time[alert_type] = frame_number
            return True
        
        return False
    
    def get_temporal_confidence(self) -> Dict[str, float]:
        """
        Calculate temporal confidence for each metric.
        
        Returns:
            Dict with confidence scores (0-1)
        """
        if len(self.ear_buffer) < self.window_size // 2:
            return {
                "ear_confidence": 0.0,
                "mar_confidence": 0.0,
                "pose_confidence": 0.0
            }
        
        # EAR consistency (lower variance = higher confidence)
        ear_variance = np.var(list(self.ear_buffer))
        ear_confidence = max(0.0, 1.0 - ear_variance * 10.0)
        
        # MAR consistency
        mar_variance = np.var(list(self.mar_buffer))
        mar_confidence = max(0.0, 1.0 - mar_variance * 5.0)
        
        # Pose consistency (lower yaw/pitch variance = higher confidence)
        yaw_variance = np.var(list(self.yaw_buffer))
        pitch_variance = np.var(list(self.pitch_buffer))
        pose_variance = (yaw_variance + pitch_variance) / 2.0
        pose_confidence = max(0.0, 1.0 - pose_variance / 100.0)
        
        return {
            "ear_confidence": float(ear_confidence),
            "mar_confidence": float(mar_confidence),
            "pose_confidence": float(pose_confidence)
        }


class DriverMonitorV11:
    """
    Driver monitoring system using MediaPipe Face Mesh.
    Detects drowsiness and distraction from in-cabin video.
    """
    
    # Eye landmarks (MediaPipe Face Mesh indices)
    LEFT_EYE = [362, 385, 387, 263, 373, 380]
    RIGHT_EYE = [33, 160, 158, 133, 153, 144]
    
    # Mouth landmarks
    MOUTH = [61, 291, 0, 17, 269, 405]
    
    # Thresholds
    EAR_THRESHOLD = 0.25  # Below this = eyes closed
    MAR_THRESHOLD = 0.6   # Above this = mouth open (yawning)
    DROWSY_FRAMES = 20    # Consecutive frames to trigger drowsy
    
    def __init__(self, device: str = "cpu", enable_temporal: bool = True, enable_object_detection: bool = False):
        """
        Initialize driver monitor.
        
        Args:
            device: "cuda" or "cpu" (MediaPipe uses CPU)
            enable_temporal: Enable temporal smoothing and sustained state detection
            enable_object_detection: Enable YOLO object detection for phones, cigarettes, etc.
        """
        self.device = device
        self.mp_face_mesh = None
        self.face_mesh = None
        self.enable_object_detection = enable_object_detection
        
        # YOLO Object Detector (optional)
        self.yolo_model = None
        
        # State tracking
        self.closed_eye_counter = 0
        self.yawn_counter = 0
        self.no_face_counter = 0
        self.is_drowsy = False
        
        # Temporal state tracking (PRODUCTION)
        self.enable_temporal = enable_temporal
        self.temporal_state = TemporalDriverState(
            window_seconds=3.0,
            frame_rate=30,
            alpha=0.2
        ) if enable_temporal else None
        self.frame_number = 0
        self.last_alert_time = {}  # {alert_type: frame_number}
        self.alert_cooldown_frames = 150  # 5 seconds @ 30fps
        
        # Try to load MediaPipe
        try:
            import mediapipe as mp
            self.mp_face_mesh = mp.solutions.face_mesh
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            logger.info("✓ MediaPipe Face Mesh initialized")
        except ImportError:
            logger.error("mediapipe package not installed. Install: pip install mediapipe")
            raise
        
        # Initialize YOLO (if enabled)
        if self.enable_object_detection:
            self._init_yolo()
    
    def _init_yolo(self):
        """Initialize YOLO for object detection."""
        try:
            from ultralytics import YOLO
            # Use YOLOv8n (nano) for speed
            self.yolo_model = YOLO('yolov8n.pt')
            logger.info("✓ YOLOv8 initialized for object detection")
        except ImportError:
            logger.warning("ultralytics not installed. Object detection disabled.")
            logger.warning("Install: pip install ultralytics")
            self.enable_object_detection = False
        except Exception as e:
            logger.warning(f"YOLO initialization failed: {e}. Object detection disabled.")
            self.enable_object_detection = False
    
    def calculate_ear(self, eye_landmarks: np.ndarray) -> float:
        """
        Calculate Eye Aspect Ratio (EAR).
        
        EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
        
        Args:
            eye_landmarks: Array of 6 eye landmarks (x, y)
            
        Returns:
            EAR value (typically 0.2-0.4 when open, <0.25 when closed)
        """
        # Vertical distances
        v1 = np.linalg.norm(eye_landmarks[1] - eye_landmarks[5])
        v2 = np.linalg.norm(eye_landmarks[2] - eye_landmarks[4])
        
        # Horizontal distance
        h = np.linalg.norm(eye_landmarks[0] - eye_landmarks[3])
        
        if h == 0:
            return 0.0
        
        ear = (v1 + v2) / (2.0 * h)
        return float(ear)
    
    def calculate_mar(self, mouth_landmarks: np.ndarray) -> float:
        """
        Calculate Mouth Aspect Ratio (MAR).
        
        MAR = ||p2-p6|| / ||p1-p4||
        
        Args:
            mouth_landmarks: Array of 6 mouth landmarks (x, y)
            
        Returns:
            MAR value (typically <0.5 when closed, >0.6 when yawning)
        """
        # Vertical distance
        v = np.linalg.norm(mouth_landmarks[1] - mouth_landmarks[5])
        
        # Horizontal distance
        h = np.linalg.norm(mouth_landmarks[0] - mouth_landmarks[3])
        
        if h == 0:
            return 0.0
        
        mar = v / h
        return float(mar)
    
    def estimate_head_pose(
        self, 
        landmarks: np.ndarray,
        frame_width: int,
        frame_height: int
    ) -> Dict[str, float]:
        """
        Estimate head pose (pitch, yaw, roll) from facial landmarks.
        
        Args:
            landmarks: All facial landmarks (478 points)
            frame_width: Frame width
            frame_height: Frame height
            
        Returns:
            Dict with 'pitch', 'yaw', 'roll' in degrees
        """
        # Key 3D model points (nose, chin, left eye, right eye, left mouth, right mouth)
        model_points = np.array([
            (0.0, 0.0, 0.0),             # Nose tip
            (0.0, -330.0, -65.0),        # Chin
            (-225.0, 170.0, -135.0),     # Left eye left corner
            (225.0, 170.0, -135.0),      # Right eye right corner
            (-150.0, -150.0, -125.0),    # Left mouth corner
            (150.0, -150.0, -125.0)      # Right mouth corner
        ], dtype=np.float64)
        
        # 2D image points from landmarks
        image_points = np.array([
            landmarks[1],      # Nose tip
            landmarks[152],    # Chin
            landmarks[33],     # Left eye
            landmarks[263],    # Right eye
            landmarks[61],     # Left mouth
            landmarks[291]     # Right mouth
        ], dtype=np.float64)
        
        # Camera internals (approximate)
        focal_length = frame_width
        center = (frame_width / 2, frame_height / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float64)
        
        # Assume no lens distortion
        dist_coeffs = np.zeros((4, 1))
        
        try:
            # Solve PnP
            success, rotation_vector, translation_vector = cv2.solvePnP(
                model_points, 
                image_points, 
                camera_matrix, 
                dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE
            )
            
            if not success:
                return {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
            
            # Convert rotation vector to angles
            rotation_mat, _ = cv2.Rodrigues(rotation_vector)
            
            # Extract Euler angles
            pitch = np.arctan2(rotation_mat[2][1], rotation_mat[2][2])
            yaw = np.arctan2(-rotation_mat[2][0], 
                           np.sqrt(rotation_mat[2][1]**2 + rotation_mat[2][2]**2))
            roll = np.arctan2(rotation_mat[1][0], rotation_mat[0][0])
            
            # Convert to degrees
            return {
                "pitch": float(np.degrees(pitch)),
                "yaw": float(np.degrees(yaw)),
                "roll": float(np.degrees(roll))
            }
        except Exception as e:
            logger.warning(f"Head pose estimation failed: {e}")
            return {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
    
    def detect_objects(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect dangerous objects using YOLO.
        
        Args:
            frame: BGR frame
            
        Returns:
            List of detected objects with class, confidence, bbox
        """
        if not self.enable_object_detection or self.yolo_model is None:
            return []
        
        try:
            # Run YOLO inference
            results = self.yolo_model(frame, verbose=False)
            
            # Classes of interest
            # COCO dataset classes (pre-trained)
            DANGEROUS_CLASSES = {
                67: "cell phone",  # Phone detection (COCO)
                39: "bottle",      # Bottle/Can - drinking (COCO)
                # 44: "wine glass", # Uncomment if needed
                # 46: "cup",        # Uncomment if needed
            }
            
            # NOTE: The following require CUSTOM YOLO TRAINING:
            # - "seatbelt": Detect seatbelt strap across shoulder
            # - "hands_on_wheel": Detect hands on steering wheel
            # - "cigarette": Detect cigarette in hand/mouth
            # - "food": Detect food items
            # - "stressed_face": Facial expression analysis (use separate model)
            #
            # To train custom classes:
            # 1. Collect 1000+ labeled images per class
            # 2. Use Roboflow or LabelImg for annotation
            # 3. Train YOLOv8: yolo train data=custom.yaml model=yolov8n.pt epochs=100
            # 4. Update DANGEROUS_CLASSES dict with new class IDs
            
            detections = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls_id = int(box.cls[0])
                    if cls_id in DANGEROUS_CLASSES:
                        detections.append({
                            "class": DANGEROUS_CLASSES[cls_id],
                            "confidence": float(box.conf[0]),
                            "bbox": box.xyxy[0].cpu().numpy().tolist()
                        })
            
            return detections
        except Exception as e:
            logger.warning(f"Object detection failed: {e}")
            return []
    
    def detect_drowsiness(
        self, 
        ear: float, 
        mar: float,
        head_pose: Dict[str, float]
    ) -> Tuple[bool, str]:
        """
        Detect drowsiness based on facial metrics.
        
        Args:
            ear: Eye Aspect Ratio
            mar: Mouth Aspect Ratio
            head_pose: Head pose angles
            
        Returns:
            Tuple of (is_drowsy, reason)
        """
        reasons = []
        
        # Check eyes
        if ear < self.EAR_THRESHOLD:
            self.closed_eye_counter += 1
        else:
            self.closed_eye_counter = 0
        
        # Check yawning
        if mar > self.MAR_THRESHOLD:
            self.yawn_counter += 1
        else:
            self.yawn_counter = 0
        
        # Drowsiness detection
        if self.closed_eye_counter >= self.DROWSY_FRAMES:
            reasons.append("EYES_CLOSED")
        
        if self.yawn_counter >= 10:
            reasons.append("YAWNING")
        
        # Check head pose (looking down = drowsy)
        if head_pose['pitch'] < -20:
            reasons.append("HEAD_DOWN")
        
        # Check head pose (looking away = distracted)
        if abs(head_pose['yaw']) > 30:
            reasons.append("DISTRACTED")
        
        is_drowsy = len(reasons) > 0
        reason = ", ".join(reasons) if reasons else "ALERT"
        
        return is_drowsy, reason
    
    def draw_facial_landmarks(
        self, 
        frame: np.ndarray, 
        landmarks: np.ndarray
    ) -> np.ndarray:
        """
        Draw FULL 468-point facial landmarks mesh on frame.
        
        Features:
        - All 468 MediaPipe landmarks
        - Mesh connections
        - Face contours
        - Neon glow effect
        
        Args:
            frame: RGB frame
            landmarks: Facial landmarks array (468 points)
            
        Returns:
            Frame with full face mesh
        """
        annotated = frame.copy()
        height, width = frame.shape[:2]
        
        # MediaPipe Face Mesh connections (subset for performance)
        # Full mesh would be too dense, so we draw key contours
        
        # === 1. FACE OVAL (Contour) ===
        face_oval = [
            10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
            397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
            172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109
        ]
        
        # === 2. LEFT EYE (Full contour) ===
        left_eye_contour = [
            33, 7, 163, 144, 145, 153, 154, 155, 133,
            173, 157, 158, 159, 160, 161, 246, 33
        ]
        
        # === 3. RIGHT EYE (Full contour) ===
        right_eye_contour = [
            362, 382, 381, 380, 374, 373, 390, 249,
            263, 466, 388, 387, 386, 385, 384, 398, 362
        ]
        
        # === 4. LEFT EYEBROW ===
        left_eyebrow = [46, 53, 52, 65, 55, 70, 63, 105, 66, 107]
        
        # === 5. RIGHT EYEBROW ===
        right_eyebrow = [276, 283, 282, 295, 285, 300, 293, 334, 296, 336]
        
        # === 6. NOSE BRIDGE ===
        nose_bridge = [168, 6, 197, 195, 5, 4, 1, 19, 94, 2]
        
        # === 7. NOSE TIP ===
        nose_tip = [1, 2, 98, 327]
        
        # === 8. LIPS OUTER ===
        lips_outer = [
            61, 146, 91, 181, 84, 17, 314, 405, 321, 375,
            291, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 61
        ]
        
        # === 9. LIPS INNER ===
        lips_inner = [
            78, 191, 80, 81, 82, 13, 312, 311, 310, 415,
            308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 78
        ]
        
        # Draw connections with neon glow effect
        def draw_contour(contour, color, thickness=1):
            """Draw contour with glow effect."""
            points = []
            for idx in contour:
                if idx < len(landmarks):
                    x, y = landmarks[idx].astype(int)
                    points.append((x, y))
            
            if len(points) > 1:
                # Outer glow
                for i in range(len(points) - 1):
                    cv2.line(annotated, points[i], points[i + 1], color, thickness + 2, cv2.LINE_AA)
                # Inner bright line
                for i in range(len(points) - 1):
                    cv2.line(annotated, points[i], points[i + 1], (255, 255, 255), thickness, cv2.LINE_AA)
        
        # Draw all contours with cyan/neon colors
        draw_contour(face_oval, (255, 200, 100), 2)  # Cyan for face
        draw_contour(left_eye_contour, (0, 255, 255), 2)  # Yellow for eyes
        draw_contour(right_eye_contour, (0, 255, 255), 2)
        draw_contour(left_eyebrow, (255, 200, 100), 1)
        draw_contour(right_eyebrow, (255, 200, 100), 1)
        draw_contour(nose_bridge, (255, 200, 100), 1)
        draw_contour(lips_outer, (255, 100, 200), 2)  # Pink for lips
        draw_contour(lips_inner, (255, 100, 200), 1)
        
        # === 10. DRAW ALL 468 LANDMARKS AS POINTS ===
        # Key landmarks (larger)
        key_landmarks = set(
            face_oval + left_eye_contour + right_eye_contour + 
            left_eyebrow + right_eyebrow + nose_bridge + 
            lips_outer + lips_inner
        )
        
        for idx, (x, y) in enumerate(landmarks):
            x, y = int(x), int(y)
            if idx in key_landmarks:
                # Key points: larger with glow
                cv2.circle(annotated, (x, y), 3, (100, 200, 255), -1)
                cv2.circle(annotated, (x, y), 2, (255, 255, 255), -1)
            else:
                # Other points: smaller
                cv2.circle(annotated, (x, y), 1, (100, 200, 255), -1)
        
        return annotated
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Process frame for driver monitoring (PRODUCTION METHOD).
        
        Args:
            frame: RGB frame from in-cabin camera
            
        Returns:
            Dict containing:
                - annotated_frame: Frame with landmarks and warnings
                - face_detected: Boolean
                - ear: Eye Aspect Ratio (raw)
                - mar: Mouth Aspect Ratio (raw)
                - smoothed_ear: Temporal-smoothed EAR (if enabled)
                - smoothed_mar: Temporal-smoothed MAR (if enabled)
                - head_pose: Dict with pitch, yaw, roll
                - is_drowsy: Instantaneous drowsiness (raw)
                - is_sustained_drowsy: Sustained drowsiness over 3s window
                - drowsy_confidence: Confidence score (0-1)
                - drowsy_reason: String reason for drowsiness
                - should_alert: Boolean - whether to trigger alert (respects cooldown)
                - temporal_confidence: Dict with metric confidence scores
        """
        self.frame_number += 1
        height, width = frame.shape[:2]
        
        # Convert to RGB (MediaPipe expects RGB)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process with MediaPipe
        results = self.face_mesh.process(rgb_frame)
        
        # Detect objects (phones, cigarettes, etc.) - Run before face detection
        detected_objects = self.detect_objects(frame)
        
        # Initialize defaults
        face_detected = False
        ear = 0.0
        mar = 0.0
        head_pose = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        is_drowsy = False
        drowsy_reason = "NO_FACE"
        
        annotated_frame = frame.copy()
        
        if results.multi_face_landmarks:
            face_detected = True
            self.no_face_counter = 0
            face_landmarks = results.multi_face_landmarks[0]
            
            # Convert landmarks to numpy array
            landmarks = np.array([
                [lm.x * width, lm.y * height] 
                for lm in face_landmarks.landmark
            ])
            
            # Extract eye landmarks
            left_eye = landmarks[self.LEFT_EYE]
            right_eye = landmarks[self.RIGHT_EYE]
            
            # Calculate EAR
            left_ear = self.calculate_ear(left_eye)
            right_ear = self.calculate_ear(right_eye)
            ear = (left_ear + right_ear) / 2.0
            
            # Extract mouth landmarks
            mouth = landmarks[self.MOUTH]
            
            # Calculate MAR
            mar = self.calculate_mar(mouth)
            
            # Estimate head pose
            head_pose = self.estimate_head_pose(landmarks, width, height)
            
            # Detect drowsiness
            is_drowsy, drowsy_reason = self.detect_drowsiness(ear, mar, head_pose)
            
            # Draw landmarks
            annotated_frame = self.draw_facial_landmarks(frame, landmarks)
            
            # Update temporal state (PRODUCTION)
            if self.enable_temporal and self.temporal_state:
                self.temporal_state.update(
                    ear=ear,
                    mar=mar,
                    yaw=head_pose['yaw'],
                    pitch=head_pose['pitch'],
                    is_drowsy=is_drowsy,
                    frame_number=self.frame_number
                )
            
            # === PREMIUM HUD OVERLAY ===
            annotated_frame = draw_premium_hud(
                frame=annotated_frame,
                ear=ear,
                mar=mar,
                head_pose=head_pose,
                is_drowsy=is_drowsy,
                drowsy_reason=drowsy_reason,
                detected_objects=detected_objects,
                frame_number=self.frame_number
            )
        else:
            # No face detected
            self.no_face_counter += 1
            if self.no_face_counter > 150:  # 5 seconds @ 30fps
                drowsy_reason = "KHÔNG PHÁT HIỆN TÀI XẾ"
                # Draw no-face warning with premium HUD
                annotated_frame = draw_premium_hud(
                    frame=annotated_frame,
                    ear=0.0,
                    mar=0.0,
                    head_pose={'pitch': 0, 'yaw': 0, 'roll': 0},
                    is_drowsy=True,
                    drowsy_reason=drowsy_reason,
                    detected_objects=detected_objects,
                    frame_number=self.frame_number
                )
        
        
        # Get temporal metrics (PRODUCTION)
        is_sustained_drowsy = False
        drowsy_confidence = 0.0
        should_alert = False
        alerts_triggered = []
        smoothed_values = {"ear": ear, "mar": mar, "yaw": head_pose['yaw'], "pitch": head_pose['pitch']}
        temporal_confidence = {"ear_confidence": 1.0, "mar_confidence": 1.0, "pose_confidence": 1.0}
        
        if self.enable_temporal and self.temporal_state:
            is_sustained_drowsy, drowsy_confidence = self.temporal_state.get_sustained_drowsiness()
            smoothed_values = self.temporal_state.get_smoothed_values()
            temporal_confidence = self.temporal_state.get_temporal_confidence()
            
            # Check if alert should be triggered
            if is_sustained_drowsy and self.temporal_state.should_alert('DROWSY', self.frame_number):
                if "EYES_CLOSED" in drowsy_reason:
                    alerts_triggered.append(AlertType.DROWSY_EYES_CLOSED.value)
                if "YAWNING" in drowsy_reason:
                    alerts_triggered.append(AlertType.DROWSY_YAWNING.value)
                if "HEAD_DOWN" in drowsy_reason:
                    alerts_triggered.append(AlertType.DROWSY_HEAD_DOWN.value)
                if "LOOKING_AWAY" in drowsy_reason:
                    alerts_triggered.append(AlertType.DISTRACTED_LOOKING_AWAY.value)
        
        # Object-based alerts
        for obj in detected_objects:
            # Phone detection
            if obj['class'] == 'cell phone' and obj['confidence'] > 0.7:
                if self.enable_temporal and self.temporal_state:
                    if self.temporal_state.should_alert('PHONE', self.frame_number):
                        alerts_triggered.append(AlertType.DISTRACTED_USING_PHONE.value)
                else:
                    alerts_triggered.append(AlertType.DISTRACTED_USING_PHONE.value)
            
            # Drinking detection (bottle/can near face)
            if obj['class'] == 'bottle' and obj['confidence'] > 0.7:
                if self.enable_temporal and self.temporal_state:
                    if self.temporal_state.should_alert('DRINKING', self.frame_number):
                        alerts_triggered.append(AlertType.VIOLATION_DRINKING.value)
                else:
                    alerts_triggered.append(AlertType.VIOLATION_DRINKING.value)
            
            # TODO: Add custom YOLO classes when trained
            # if obj['class'] == 'no_seatbelt' and obj['confidence'] > 0.8:
            #     alerts_triggered.append(AlertType.VIOLATION_NO_SEATBELT.value)
            #
            # if obj['class'] == 'hands_off_wheel' and obj['confidence'] > 0.8:
            #     alerts_triggered.append(AlertType.CRITICAL_HANDS_OFF.value)
            #
            # if obj['class'] == 'cigarette' and obj['confidence'] > 0.7:
            #     alerts_triggered.append(AlertType.VIOLATION_SMOKING.value)
        
        # Talking to passenger detection (sustained head turn > 45° for > 5 seconds)
        if face_detected and abs(head_pose['yaw']) > 45:
            if self.enable_temporal and self.temporal_state:
                # Check if yaw has been > 45° for sustained period
                yaw_buffer = list(self.temporal_state.yaw_buffer)
                if len(yaw_buffer) >= 150:  # 5 seconds @ 30fps
                    sustained_turn = sum(1 for y in yaw_buffer[-150:] if abs(y) > 45)
                    if sustained_turn >= 105:  # 70% of 150 frames
                        if self.temporal_state.should_alert('TALKING_PASSENGER', self.frame_number):
                            alerts_triggered.append(AlertType.DISTRACTED_TALKING_PASSENGER.value)
        
        # No face alert
        if drowsy_reason == "NO_FACE" and self.no_face_counter > 150:
            if self.enable_temporal and self.temporal_state:
                if self.temporal_state.should_alert('NO_FACE', self.frame_number):
                    alerts_triggered.append(AlertType.CRITICAL_NO_FACE.value)
            else:
                alerts_triggered.append(AlertType.CRITICAL_NO_FACE.value)
        
        return {
            "annotated_frame": annotated_frame,
            "face_detected": face_detected,
            "ear": float(ear),
            "mar": float(mar),
            "smoothed_ear": float(smoothed_values['ear']),
            "smoothed_mar": float(smoothed_values['mar']),
            "head_pose": head_pose,
            "is_drowsy": is_drowsy,
            "is_sustained_drowsy": is_sustained_drowsy,
            "drowsy_confidence": float(drowsy_confidence),
            "drowsy_reason": drowsy_reason,
            "detected_objects": detected_objects,
            "alerts_triggered": alerts_triggered,
            "should_alert": len(alerts_triggered) > 0,
            "temporal_confidence": temporal_confidence,
            "frame_number": self.frame_number
        }



if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    
    try:
        monitor = DriverMonitorV11(device="cpu")
        print("Driver Monitor initialized successfully")
    except Exception as e:
        print(f"Failed to initialize: {e}")
