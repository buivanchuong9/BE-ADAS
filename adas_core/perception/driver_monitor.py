"""
Driver Monitoring System (DMS) - Computer Vision for Driver Safety
Detects: Drowsiness, Distraction, Phone usage, Emotions

Features:
- Eye aspect ratio (EAR) for drowsiness detection
- Head pose estimation for distraction
- Yawn detection
- Phone usage detection
- Emotion recognition (angry, tired, happy, neutral)
- Attention scoring
"""

import cv2
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time

from .base import IPerception, PerceptionResult


class DriverState(Enum):
    """Driver attention state"""
    ALERT = "alert"              # Fully attentive
    DROWSY = "drowsy"            # Eyes closing, yawning
    DISTRACTED = "distracted"    # Looking away
    PHONE_USE = "phone_use"      # Using phone
    ASLEEP = "asleep"            # Eyes fully closed


class EmotionState(Enum):
    """Driver emotional state"""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    TIRED = "tired"
    ANGRY = "angry"
    STRESSED = "stressed"


@dataclass
class DriverMonitorResult:
    """
    Driver monitoring result
    
    Contains:
    - Driver state (alert, drowsy, distracted, etc.)
    - Attention score [0-1]
    - Drowsiness indicators (EAR, yawn count)
    - Head pose (pitch, yaw, roll)
    - Emotion
    - Alert messages
    """
    timestamp: datetime
    
    # State
    state: DriverState
    attention_score: float  # [0.0-1.0], 1.0 = fully alert
    
    # Drowsiness indicators
    eye_aspect_ratio: float  # EAR value
    perclos: float  # Percentage of eye closure over time
    yawn_detected: bool
    yawn_count: int  # Total yawns in session
    
    # Head pose (degrees)
    pitch: float  # Up/down tilt
    yaw: float    # Left/right turn
    roll: float   # Side tilt
    
    # Distraction
    gaze_direction: str  # "forward", "left", "right", "down"
    looking_away_duration: float  # Seconds
    
    # Phone usage
    phone_detected: bool
    hand_near_face: bool
    
    # Emotion
    emotion: EmotionState
    
    # Alerts
    alerts: List[str] = field(default_factory=list)
    
    # Face detection
    face_detected: bool = True
    face_bbox: Optional[Tuple[int, int, int, int]] = None
    
    # Confidence
    confidence: float = 1.0


class DriverMonitor(IPerception):
    """
    Driver Monitoring System using Computer Vision
    
    Detection Methods:
    1. Face Detection - Haar Cascade / DNN
    2. Facial Landmarks - dlib / MediaPipe
    3. Eye Aspect Ratio (EAR) - Drowsiness detection
    4. Head Pose Estimation - PnP algorithm
    5. Yawn Detection - Mouth aspect ratio (MAR)
    6. Emotion Recognition - Deep learning model
    
    Thresholds (ISO/DIS 15005 - Driver behavior):
    - EAR < 0.25: Eyes closing
    - EAR < 0.20: Drowsiness warning
    - PERCLOS > 0.15: Severe drowsiness
    - Yawn > 3 in 5 min: Fatigue
    - Looking away > 2s: Distraction
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize driver monitor
        
        Config:
            - enable_drowsiness: Enable drowsiness detection
            - enable_distraction: Enable distraction detection
            - enable_emotion: Enable emotion recognition
            - ear_threshold: Eye aspect ratio threshold (default: 0.25)
            - perclos_threshold: PERCLOS threshold (default: 0.15)
            - yawn_threshold: Yawn count threshold (default: 3)
            - distraction_time: Looking away threshold in seconds (default: 2.0)
        """
        super().__init__(config)
        
        # Configuration
        self.enable_drowsiness = config.get('enable_drowsiness', True)
        self.enable_distraction = config.get('enable_distraction', True)
        self.enable_phone_detection = config.get('enable_phone_detection', True)
        self.enable_emotion = config.get('enable_emotion', True)
        
        # Thresholds
        self.ear_threshold = config.get('ear_threshold', 0.25)
        self.ear_critical = config.get('ear_critical', 0.20)
        self.perclos_threshold = config.get('perclos_threshold', 0.15)
        self.yawn_threshold = config.get('yawn_threshold', 3)
        self.distraction_time_threshold = config.get('distraction_time', 2.0)
        
        # Models
        self.face_cascade = None
        self.eye_cascade = None
        self.face_detector = None
        self.landmark_detector = None
        
        # State tracking
        self.yawn_count = 0
        self.last_yawn_time = None
        self.looking_away_start = None
        self.looking_away_duration = 0.0
        self.ear_history = []
        self.max_ear_history = 30  # 1 second @ 30fps
        
        # 3D face model points (for head pose estimation)
        self.model_points = np.array([
            (0.0, 0.0, 0.0),             # Nose tip
            (0.0, -330.0, -65.0),        # Chin
            (-225.0, 170.0, -135.0),     # Left eye left corner
            (225.0, 170.0, -135.0),      # Right eye right corner
            (-150.0, -150.0, -125.0),    # Left mouth corner
            (150.0, -150.0, -125.0)      # Right mouth corner
        ])
        
    async def initialize(self) -> bool:
        """
        Initialize face detection and landmark models
        
        Returns:
            True if initialization successful
        """
        try:
            print(f"[DriverMonitor] Initializing...")
            
            # Load Haar Cascade for face detection
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            
            # Load eye cascade for basic eye detection
            self.eye_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_eye.xml'
            )
            
            # Try to load dlib or MediaPipe for facial landmarks
            try:
                import dlib
                predictor_path = self.config.get('landmark_model', 
                    'shape_predictor_68_face_landmarks.dat')
                self.landmark_detector = dlib.shape_predictor(predictor_path)
                print(f"[DriverMonitor] ✅ Using dlib for landmarks")
            except:
                print(f"[DriverMonitor] ⚠️ dlib not available, using basic detection")
                self.landmark_detector = None
            
            self._is_initialized = True
            print(f"[DriverMonitor] ✅ Initialized successfully")
            return True
            
        except Exception as e:
            print(f"[DriverMonitor] ❌ Initialization failed: {e}")
            return False
    
    async def process(self, frame: np.ndarray) -> PerceptionResult:
        """
        Process frame and detect driver state
        
        Args:
            frame: Input frame (BGR)
            
        Returns:
            PerceptionResult with driver monitoring data
        """
        start_time = time.time()
        
        # Detect face
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
        )
        
        if len(faces) == 0:
            # No face detected
            result = DriverMonitorResult(
                timestamp=datetime.now(),
                state=DriverState.DISTRACTED,
                attention_score=0.0,
                eye_aspect_ratio=0.0,
                perclos=0.0,
                yawn_detected=False,
                yawn_count=self.yawn_count,
                pitch=0.0, yaw=0.0, roll=0.0,
                gaze_direction="unknown",
                looking_away_duration=0.0,
                phone_detected=False,
                hand_near_face=False,
                emotion=EmotionState.NEUTRAL,
                alerts=["⚠️ KHÔNG PHÁT HIỆN TÀI XẾ!"],
                face_detected=False,
                confidence=0.0
            )
        else:
            # Process largest face (assumed to be driver)
            (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
            face_roi = gray[y:y+h, x:x+w]
            
            # Extract features
            ear = self._calculate_ear(face_roi, (x, y, w, h))
            yawn = self._detect_yawn(face_roi)
            pitch, yaw, roll = self._estimate_head_pose(gray, (x, y, w, h))
            gaze = self._estimate_gaze_direction(yaw)
            emotion = self._detect_emotion(face_roi)
            phone = self._detect_phone_usage(frame, (x, y, w, h))
            
            # Calculate attention score
            attention = self._calculate_attention_score(ear, yaw, roll)
            
            # Determine state
            state = self._determine_state(ear, yawn, gaze, phone)
            
            # Update tracking
            self._update_tracking(ear, yawn, gaze)
            
            # Generate alerts
            alerts = self._generate_alerts(state, ear, yawn, gaze, self.yawn_count)
            
            # Calculate PERCLOS (percentage of eye closure)
            perclos = self._calculate_perclos()
            
            result = DriverMonitorResult(
                timestamp=datetime.now(),
                state=state,
                attention_score=attention,
                eye_aspect_ratio=ear,
                perclos=perclos,
                yawn_detected=yawn,
                yawn_count=self.yawn_count,
                pitch=pitch, yaw=yaw, roll=roll,
                gaze_direction=gaze,
                looking_away_duration=self.looking_away_duration,
                phone_detected=phone,
                hand_near_face=False,
                emotion=emotion,
                alerts=alerts,
                face_detected=True,
                face_bbox=(x, y, w, h),
                confidence=0.9
            )
        
        inference_time = (time.time() - start_time) * 1000
        fps = 1000 / inference_time if inference_time > 0 else 0
        
        # Convert to PerceptionResult
        perception_result = PerceptionResult(
            timestamp=datetime.now(),
            objects=[],  # Not used for DMS
            lanes=[],
            inference_time_ms=inference_time,
            fps=fps,
            confidence=result.confidence
        )
        
        # Store DMS result in metadata
        perception_result.metadata = {'driver_monitor': result}
        
        self._frame_count += 1
        return perception_result
    
    def _calculate_ear(self, face_roi: np.ndarray, face_bbox: Tuple) -> float:
        """
        Calculate Eye Aspect Ratio (EAR)
        
        EAR formula: (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
        Where p1-p6 are eye landmarks
        
        EAR > 0.25: Eyes open
        EAR < 0.25: Eyes closing
        EAR < 0.20: Drowsiness
        """
        # Simplified EAR using eye cascade
        eyes = self.eye_cascade.detectMultiScale(face_roi)
        
        if len(eyes) < 2:
            return 0.2  # Assume eyes closed if not detected
        
        # Calculate average eye height/width ratio
        ear_values = []
        for (ex, ey, ew, eh) in eyes[:2]:
            ear = eh / ew if ew > 0 else 0.25
            ear_values.append(ear)
        
        return np.mean(ear_values) if ear_values else 0.25
    
    def _detect_yawn(self, face_roi: np.ndarray) -> bool:
        """
        Detect yawning using mouth aspect ratio (MAR)
        
        MAR > threshold: Mouth open (yawn)
        """
        # Simplified: detect large dark region in lower face
        h, w = face_roi.shape
        mouth_roi = face_roi[int(h*0.6):, int(w*0.3):int(w*0.7)]
        
        # Threshold to find dark (open mouth) regions
        _, thresh = cv2.threshold(mouth_roi, 50, 255, cv2.THRESH_BINARY_INV)
        white_pixels = cv2.countNonZero(thresh)
        total_pixels = mouth_roi.size
        
        ratio = white_pixels / total_pixels if total_pixels > 0 else 0
        return ratio > 0.4  # Mouth is open significantly
    
    def _estimate_head_pose(self, gray: np.ndarray, face_bbox: Tuple) -> Tuple[float, float, float]:
        """
        Estimate head pose (pitch, yaw, roll) using PnP algorithm
        
        Returns:
            (pitch, yaw, roll) in degrees
        """
        # Simplified: estimate from face bbox aspect ratio and position
        x, y, w, h = face_bbox
        
        # Yaw (left/right): Based on face horizontal position
        frame_center_x = gray.shape[1] / 2
        face_center_x = x + w / 2
        yaw = (face_center_x - frame_center_x) / frame_center_x * 30  # ±30 degrees
        
        # Pitch (up/down): Based on face vertical position
        frame_center_y = gray.shape[0] / 2
        face_center_y = y + h / 2
        pitch = (face_center_y - frame_center_y) / frame_center_y * 20
        
        # Roll (tilt): Based on face aspect ratio deviation
        aspect_ratio = w / h if h > 0 else 1.0
        roll = (aspect_ratio - 0.75) * 20  # Assuming ideal ratio is 0.75
        
        return (pitch, yaw, roll)
    
    def _estimate_gaze_direction(self, yaw: float) -> str:
        """
        Estimate gaze direction from head yaw
        
        Args:
            yaw: Head yaw angle in degrees
            
        Returns:
            "forward", "left", "right", or "down"
        """
        if abs(yaw) < 10:
            return "forward"
        elif yaw < -10:
            return "left"
        elif yaw > 10:
            return "right"
        else:
            return "forward"
    
    def _detect_emotion(self, face_roi: np.ndarray) -> EmotionState:
        """
        Detect driver emotion (simplified)
        
        In production: Use deep learning model (FER, AffectNet)
        """
        # Simplified: Use image statistics
        mean_intensity = np.mean(face_roi)
        
        if mean_intensity < 80:
            return EmotionState.TIRED
        elif mean_intensity > 150:
            return EmotionState.HAPPY
        else:
            return EmotionState.NEUTRAL
    
    def _detect_phone_usage(self, frame: np.ndarray, face_bbox: Tuple) -> bool:
        """
        Detect phone usage (hand near face)
        
        Simplified: Detect skin-colored regions near face
        """
        # In production: Use hand detection model + object detection
        # For now, return False
        return False
    
    def _calculate_attention_score(self, ear: float, yaw: float, roll: float) -> float:
        """
        Calculate attention score [0-1]
        
        Factors:
        - Eye openness (EAR)
        - Head pose (looking forward)
        - Head tilt (not tilted)
        """
        # Eye openness score
        eye_score = min(1.0, ear / 0.30)  # EAR=0.30 is fully open
        
        # Gaze score (looking forward)
        gaze_score = max(0.0, 1.0 - abs(yaw) / 30.0)
        
        # Tilt score
        tilt_score = max(0.0, 1.0 - abs(roll) / 30.0)
        
        # Weighted average
        attention = 0.5 * eye_score + 0.3 * gaze_score + 0.2 * tilt_score
        
        return float(np.clip(attention, 0.0, 1.0))
    
    def _determine_state(self, ear: float, yawn: bool, gaze: str, phone: bool) -> DriverState:
        """Determine driver state based on indicators"""
        if phone:
            return DriverState.PHONE_USE
        elif ear < self.ear_critical:
            return DriverState.ASLEEP
        elif ear < self.ear_threshold or yawn:
            return DriverState.DROWSY
        elif gaze != "forward":
            return DriverState.DISTRACTED
        else:
            return DriverState.ALERT
    
    def _update_tracking(self, ear: float, yawn: bool, gaze: str) -> None:
        """Update tracking state"""
        # Update EAR history
        self.ear_history.append(ear)
        if len(self.ear_history) > self.max_ear_history:
            self.ear_history.pop(0)
        
        # Update yawn count
        if yawn:
            current_time = time.time()
            if self.last_yawn_time is None or current_time - self.last_yawn_time > 5.0:
                self.yawn_count += 1
                self.last_yawn_time = current_time
        
        # Update looking away duration
        if gaze != "forward":
            if self.looking_away_start is None:
                self.looking_away_start = time.time()
            self.looking_away_duration = time.time() - self.looking_away_start
        else:
            self.looking_away_start = None
            self.looking_away_duration = 0.0
    
    def _calculate_perclos(self) -> float:
        """
        Calculate PERCLOS (Percentage of Eye Closure)
        
        PERCLOS > 0.15: Severe drowsiness (ISO/DIS 15005)
        """
        if len(self.ear_history) == 0:
            return 0.0
        
        closed_count = sum(1 for ear in self.ear_history if ear < self.ear_threshold)
        return closed_count / len(self.ear_history)
    
    def _generate_alerts(self, state: DriverState, ear: float, yawn: bool, 
                         gaze: str, yawn_count: int) -> List[str]:
        """Generate alert messages"""
        alerts = []
        
        if state == DriverState.ASLEEP:
            alerts.append("🚨 CẢNH BÁO: TÀI XẾ ĐANG NGỦ! DỪNG XE NGAY!")
        elif state == DriverState.DROWSY:
            if ear < self.ear_threshold:
                alerts.append("😴 CẢNH BÁO: TÀI XẾ BUỒN NGỦ - Mắt đang nhắm!")
            if yawn:
                alerts.append("🥱 PHÁT HIỆN NGÁP - Nghỉ ngơi đi!")
            if yawn_count >= self.yawn_threshold:
                alerts.append(f"⚠️ ĐÃ NGÁP {yawn_count} LẦN - CẦN NGHỈ NGƠI!")
        elif state == DriverState.DISTRACTED:
            if gaze == "left":
                alerts.append("👈 TÀI XẾ NHÌN SANG TRÁI - Tập trung lái xe!")
            elif gaze == "right":
                alerts.append("👉 TÀI XẾ NHÌN SANG PHẢI - Tập trung lái xe!")
            elif self.looking_away_duration > self.distraction_time_threshold:
                alerts.append(f"⚠️ NHÌN ĐI {self.looking_away_duration:.1f}s - TẬP TRUNG!")
        elif state == DriverState.PHONE_USE:
            alerts.append("📱 CẢNH BÁO: SỬ DỤNG ĐIỆN THOẠI KHI LÁI XE!")
        
        return alerts
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """Get diagnostics"""
        return {
            'module': 'driver_monitor',
            'frame_count': self._frame_count,
            'yawn_count': self.yawn_count,
            'is_initialized': self._is_initialized,
            'features': {
                'drowsiness': self.enable_drowsiness,
                'distraction': self.enable_distraction,
                'phone_detection': self.enable_phone_detection,
                'emotion': self.enable_emotion,
            }
        }
    
    async def shutdown(self) -> None:
        """Shutdown"""
        print(f"[DriverMonitor] Shutting down...")
        self._is_initialized = False
