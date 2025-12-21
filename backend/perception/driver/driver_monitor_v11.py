"""
DRIVER MONITORING MODULE
========================
Monitors driver state using in-cabin camera and MediaPipe Face Mesh.

Detects:
- Eye closure (EAR - Eye Aspect Ratio)
- Yawning (MAR - Mouth Aspect Ratio)
- Head pose (pitch, yaw, roll)
- Drowsiness detection

Features:
- Real-time facial landmark detection
- Rule-based drowsiness classification
- Visual alerts for dangerous states

Author: Senior ADAS Engineer
Date: 2025-12-21
"""

import cv2
import numpy as np
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


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
    
    def __init__(self, device: str = "cpu"):
        """
        Initialize driver monitor.
        
        Args:
            device: "cuda" or "cpu" (MediaPipe uses CPU)
        """
        self.device = device
        self.mp_face_mesh = None
        self.face_mesh = None
        
        # State tracking
        self.closed_eye_counter = 0
        self.yawn_counter = 0
        self.is_drowsy = False
        
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
            logger.info("MediaPipe Face Mesh initialized")
        except ImportError:
            logger.error("mediapipe package not installed. Install: pip install mediapipe")
            raise
    
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
        Draw facial landmarks on frame.
        
        Args:
            frame: RGB frame
            landmarks: Facial landmarks array
            
        Returns:
            Frame with landmarks
        """
        annotated = frame.copy()
        
        # Draw eye landmarks
        for idx in self.LEFT_EYE + self.RIGHT_EYE:
            if idx < len(landmarks):
                x, y = landmarks[idx].astype(int)
                cv2.circle(annotated, (x, y), 2, (0, 255, 0), -1)
        
        # Draw mouth landmarks
        for idx in self.MOUTH:
            if idx < len(landmarks):
                x, y = landmarks[idx].astype(int)
                cv2.circle(annotated, (x, y), 2, (255, 0, 0), -1)
        
        return annotated
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Process frame for driver monitoring.
        
        Args:
            frame: RGB frame from in-cabin camera
            
        Returns:
            Dict containing:
                - annotated_frame: Frame with landmarks and warnings
                - face_detected: Boolean
                - ear: Eye Aspect Ratio
                - mar: Mouth Aspect Ratio
                - head_pose: Dict with pitch, yaw, roll
                - is_drowsy: Boolean drowsiness flag
                - drowsy_reason: String reason for drowsiness
        """
        height, width = frame.shape[:2]
        
        # Convert to RGB (MediaPipe expects RGB)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process with MediaPipe
        results = self.face_mesh.process(rgb_frame)
        
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
            
            # Draw metrics
            cv2.putText(
                annotated_frame,
                f"EAR: {ear:.2f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )
            
            cv2.putText(
                annotated_frame,
                f"MAR: {mar:.2f}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )
            
            # Draw warning if drowsy
            if is_drowsy:
                warning_text = f"WARNING: DRIVER DROWSY! ({drowsy_reason})"
                cv2.putText(
                    annotated_frame,
                    warning_text,
                    (50, height - 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 0, 255),
                    3
                )
        
        return {
            "annotated_frame": annotated_frame,
            "face_detected": face_detected,
            "ear": float(ear),
            "mar": float(mar),
            "head_pose": head_pose,
            "is_drowsy": is_drowsy,
            "drowsy_reason": drowsy_reason
        }


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    
    try:
        monitor = DriverMonitorV11(device="cpu")
        print("Driver Monitor initialized successfully")
    except Exception as e:
        print(f"Failed to initialize: {e}")
