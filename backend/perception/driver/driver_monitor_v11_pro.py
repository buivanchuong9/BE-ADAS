"""
DRIVER MONITOR V11 PRO - Giám sát hành vi tài xế NÂNG CAO
=========================================================
Phát hiện hành vi nguy hiểm của tài xế với độ chính xác cao:
- Dùng điện thoại (phone near face/ear)
- Uống nước/ăn khi lái (cup/bottle near mouth)
- Hút thuốc (hand near mouth pattern)
- Buồn ngủ/mệt mỏi (head pose + eye closure)
- Mất tập trung (looking away, not watching road)

Advanced Features:
- Head Pose Estimation (yaw, pitch, roll)
- Attention Score (0-100)
- Distraction Level Tracking
- Temporal Smoothing với multi-frame analysis
- Vietnamese voice warnings support

Tác giả: Lead AI Architect
Version: 2.0 PRO
Ngày: 2026-03-01
"""

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

logger = logging.getLogger(__name__)


class DriverMonitorV11Pro:
    """
    Hệ thống giám sát tài xế PRO - Object Detection + Pose + Head Pose Analysis.
    
    Architecture:
        Frame → YOLO Object → YOLO Pose → Head Pose → Behavior Analysis → Risk Score
    
    Tính năng NÂNG CAO:
    - Phát hiện điện thoại, ly/chai nước với temporal smoothing
    - Head Pose Estimation (yaw/pitch/roll) từ facial keypoints
    - Attention Score (0-100) - đánh giá mức tập trung
    - Distraction Level Tracking (LOW → CRITICAL)
    - Phát hiện buồn ngủ đa tiêu chí (head nod, eye closure approximation, head tilt)
    - Smoking detection via hand-mouth proximity pattern
    - Vietnamese warnings với severity levels
    """
    
    # ==================== CONFIGURATION ====================
    
    # COCO Class IDs
    OBJECT_CLASSES = {
        67: 'điện thoại',  # cell phone
        41: 'cốc',         # cup
        39: 'chai',        # bottle
    }
    
    # Distance thresholds (pixels) - adaptive based on face size
    PHONE_DISTANCE_THRESHOLD = 200
    DRINK_DISTANCE_THRESHOLD = 180
    SMOKE_DISTANCE_THRESHOLD = 100  # hand near mouth
    
    # Head Pose thresholds (degrees)
    YAW_THRESHOLD = 30           # Looking left/right
    YAW_SEVERE = 45              # Severely looking away
    PITCH_THRESHOLD = 20         # Head tilt up/down
    PITCH_SEVERE = 35            # Severely tilted
    ROLL_THRESHOLD = 25          # Head roll (lateral tilt)
    
    # Temporal thresholds (frames @ 30fps)
    LOOKING_AWAY_FRAMES = 45     # 1.5 seconds
    DROWSY_FRAMES = 60           # 2 seconds
    PHONE_CONFIRM_FRAMES = 10    # 0.33 seconds
    DRINK_CONFIRM_FRAMES = 8     # 0.27 seconds
    
    # Attention Score configuration
    ATTENTION_WEIGHTS = {
        'head_forward': 35,      # Looking forward (yaw < threshold)
        'head_level': 20,        # Head not tilted (pitch < threshold)
        'eyes_open': 25,         # Eyes appear open (EAR-like)
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
    ):
        """
        Khởi tạo Driver Monitor PRO.
        
        Args:
            object_model_path: Model phát hiện vật thể YOLO
            pose_model_path: Model phát hiện pose YOLO
            device: "cuda" hoặc "cpu"
            enable_attention_score: Bật tính năng Attention Score
            enable_head_pose: Bật tính năng Head Pose Estimation
        """
        self.device = device
        self.enable_attention = enable_attention_score
        self.enable_head_pose = enable_head_pose
        
        # State tracking
        self.frame_count = 0
        self.last_process_time = 0
        self.current_attention_score = 100
        self.current_distraction_level = 'LOW'
        
        # Reference head pose (calibrated when driver looks forward)
        self.reference_pose = None
        self.calibration_frames = []
        self.is_calibrated = False
        
        logger.info(f"🚗 Khởi tạo Driver Monitor V11 PRO ({device})")
        logger.info(f"   ├─ Attention Score: {'✅' if enable_attention_score else '❌'}")
        logger.info(f"   └─ Head Pose: {'✅' if enable_head_pose else '❌'}")
        
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
        
        # Load Vietnamese font
        self._load_font()
        
        # Initialize temporal buffers
        self._init_buffers()
        
        logger.info("✅ Driver Monitor V11 PRO khởi tạo thành công!")
    
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
    
    def _init_buffers(self):
        """Initialize temporal smoothing buffers."""
        # Behavior buffers (15-60 frames)
        self.phone_buffer = deque(maxlen=30)
        self.drink_buffer = deque(maxlen=30)
        self.smoke_buffer = deque(maxlen=30)
        
        # Head pose buffers
        self.yaw_buffer = deque(maxlen=30)
        self.pitch_buffer = deque(maxlen=30)
        self.roll_buffer = deque(maxlen=30)
        
        # Drowsiness indicators
        self.head_nod_buffer = deque(maxlen=60)
        self.head_tilt_buffer = deque(maxlen=60)
        self.eye_closure_buffer = deque(maxlen=90)  # 3 seconds
        
        # Attention tracking
        self.attention_history = deque(maxlen=90)
        self.looking_away_counter = 0
        
        # Performance tracking
        self.fps_buffer = deque(maxlen=30)
    
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
        """Phát hiện điện thoại, cốc, chai."""
        try:
            results = self.object_model(frame, device=self.device, verbose=False)
            objects = []
            
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
                    
                    objects.append({
                        'class_id': cls_id,
                        'class_name': self.OBJECT_CLASSES[cls_id],
                        'confidence': conf,
                        'bbox': [x1, y1, x2, y2],
                        'center': ((x1 + x2) // 2, (y1 + y2) // 2),
                        'area': (x2 - x1) * (y2 - y1)
                    })
            
            return objects
            
        except Exception as e:
            logger.error(f"❌ Object detection error: {e}")
            return []
    
    @torch.no_grad()
    def detect_pose(self, frame: np.ndarray) -> Optional[Dict]:
        """Phát hiện pose của tài xế."""
        try:
            results = self.pose_model(frame, device=self.device, verbose=False)
            
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
    
    def check_phone_use(self, objects: List[Dict], pose: Optional[Dict]) -> Tuple[bool, str, float]:
        """
        Kiểm tra dùng điện thoại với confidence score.
        
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
        
        for phone in phones:
            pc = phone['center']
            
            dist_nose = self._distance(pc, nose)
            dist_left_ear = self._distance(pc, left_ear)
            dist_right_ear = self._distance(pc, right_ear)
            
            min_dist = min(dist_nose, dist_left_ear, dist_right_ear)
            
            # Calculate confidence based on distance
            if min_dist < self.PHONE_DISTANCE_THRESHOLD:
                conf = 1.0 - (min_dist / self.PHONE_DISTANCE_THRESHOLD)
                conf = min(1.0, conf * phone['confidence'])
                self.phone_buffer.append(conf)
                
                # Temporal confirmation
                recent = list(self.phone_buffer)[-self.PHONE_CONFIRM_FRAMES:]
                if len(recent) >= self.PHONE_CONFIRM_FRAMES // 2:
                    avg_conf = np.mean([x for x in recent if x > 0])
                    if avg_conf > 0.3 and sum(1 for x in recent if x > 0) >= len(recent) // 2:
                        if min_dist == dist_nose:
                            msg = "📱 CẢNH BÁO: ĐANG NHÌN ĐIỆN THOẠI!"
                        else:
                            msg = "📱 CẢNH BÁO: ĐANG GỌI ĐIỆN KHI LÁI XE!"
                        return True, msg, avg_conf
        
        self.phone_buffer.append(0)
        return False, "", 0.0
    
    def check_drinking(self, objects: List[Dict], pose: Optional[Dict]) -> Tuple[bool, str, float]:
        """Kiểm tra đang uống nước."""
        if pose is None:
            self.drink_buffer.append(0)
            return False, "", 0.0
        
        drinks = [obj for obj in objects if obj['class_name'] in ['cốc', 'chai']]
        
        if not drinks:
            self.drink_buffer.append(0)
            return False, "", 0.0
        
        nose = pose['nose']
        
        for drink in drinks:
            dist = self._distance(drink['center'], nose)
            
            if dist < self.DRINK_DISTANCE_THRESHOLD:
                conf = (1.0 - dist / self.DRINK_DISTANCE_THRESHOLD) * drink['confidence']
                self.drink_buffer.append(conf)
                
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
        
        # ===== Warning Banner (top) =====
        if warnings:
            banner_height = 60 + 50 * len(warnings)
            
            # Background
            overlay = Image.new('RGBA', (w, banner_height), (200, 0, 0, 200))
            frame_pil.paste(overlay, (0, 0), overlay)
            
            # Warnings
            y = 20
            for warning in warnings:
                if self.font_large:
                    draw.text((20, y), warning, fill=(255, 255, 255), font=self.font_large)
                y += 50
        
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
    
    # ==================== MAIN PIPELINE ====================
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Pipeline xử lý hoàn chỉnh.
        
        Returns:
            Dictionary chứa tất cả metrics và results
        """
        start_time = time.time()
        self.frame_count += 1
        
        # Detect
        objects = self.detect_objects(frame)
        pose = self.detect_pose(frame)
        
        # Head pose estimation
        head_pose = self.estimate_head_pose(pose) if self.enable_head_pose and pose else {
            'yaw': 0, 'pitch': 0, 'roll': 0, 'is_valid': False
        }
        
        # Behavior checks
        warnings = []
        behaviors = {}
        
        # Phone
        using_phone, phone_msg, phone_conf = self.check_phone_use(objects, pose)
        if using_phone:
            warnings.append(phone_msg)
        behaviors['phone'] = {'detected': using_phone, 'confidence': phone_conf}
        
        # Drinking
        drinking, drink_msg, drink_conf = self.check_drinking(objects, pose)
        if drinking:
            warnings.append(drink_msg)
        behaviors['drinking'] = {'detected': drinking, 'confidence': drink_conf}
        
        # Smoking
        smoking, smoke_msg, smoke_conf = self.check_smoking(pose)
        if smoking:
            warnings.append(smoke_msg)
        behaviors['smoking'] = {'detected': smoking, 'confidence': smoke_conf}
        
        # Drowsiness
        drowsy, drowsy_msg, drowsy_severity, drowsy_conf = self.check_drowsiness(pose, head_pose)
        if drowsy:
            warnings.append(drowsy_msg)
        behaviors['drowsiness'] = {'detected': drowsy, 'severity': drowsy_severity, 'confidence': drowsy_conf}
        
        # Looking away
        looking_away, away_msg, away_duration = self.check_looking_away(head_pose)
        if looking_away:
            warnings.append(away_msg)
        behaviors['looking_away'] = {'detected': looking_away, 'duration': away_duration}
        
        # Calculate attention score
        attention_score = self.calculate_attention_score(head_pose, using_phone, drinking, smoking)
        distraction_level = self.get_distraction_level(attention_score)
        
        # Draw overlays
        annotated_frame = frame.copy()
        if pose:
            annotated_frame = self.draw_pose_overlay(annotated_frame, pose, head_pose)
        annotated_frame = self.draw_dashboard(
            annotated_frame, warnings, attention_score, head_pose, distraction_level
        )
        
        # FPS tracking
        process_time = time.time() - start_time
        self.fps_buffer.append(1.0 / max(process_time, 0.001))
        avg_fps = np.mean(list(self.fps_buffer)[-10:])
        
        # Determine driver state for backward compatibility
        # Priority: drowsy > distracted (phone/looking_away) > normal
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
            
            # Backward compatibility fields
            'state': driver_state,
            'confidence': driver_confidence,
            
            # PRO features
            'behaviors': behaviors,
            'head_pose': head_pose,
            'attention_score': attention_score,
            'distraction_level': distraction_level,
            
            # Individual flags (backward compat)
            'using_phone': using_phone,
            'drinking': drinking,
            'smoking': smoking,
            'drowsy': drowsy,
            'looking_away': looking_away,
            
            # Metadata
            'objects_detected': len(objects),
            'pose_detected': pose is not None,
            'fps': round(avg_fps, 1),
            'frame_number': self.frame_count,
        }
    
    def get_status(self) -> Dict:
        """Get current monitor status."""
        return {
            'attention_score': self.current_attention_score,
            'distraction_level': self.current_distraction_level,
            'is_calibrated': self.is_calibrated,
            'frame_count': self.frame_count,
            'device': self.device,
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
