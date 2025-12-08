"""
Traffic Sign Recognition (TSR) Module
Nhận diện biển báo giao thông

Features:
- Detect traffic signs using YOLO11
- Extract speed limit from detected signs
- Track detected signs over multiple frames
- Support Vietnamese traffic signs
"""

import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import time

from .config import (
    TRAFFIC_SIGN_CLASSES,
    SPEED_LIMITS,
    TSR_CONF_THRESHOLD,
    TSR_IOU_THRESHOLD,
    TSR_MIN_SIZE,
    TSR_MEMORY_FRAMES,
    MODELS_DIR,
    COLOR_GREEN,
    COLOR_YELLOW,
    COLOR_RED,
    COLOR_WHITE,
)


class TrafficSignRecognizer:
    """
    Traffic Sign Recognition using YOLO11
    
    Detects and recognizes traffic signs, especially speed limit signs.
    Maintains memory of detected signs to provide stable output.
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        conf_threshold: float = TSR_CONF_THRESHOLD,
        use_yolo_general: bool = True  # Fallback to general YOLO if TSR model not available
    ):
        """
        Initialize Traffic Sign Recognizer
        
        Args:
            model_path: Path to traffic sign detection model
            conf_threshold: Confidence threshold for detection
            use_yolo_general: Use general YOLO11 if TSR model not found
        """
        self.conf_threshold = conf_threshold
        self.use_yolo_general = use_yolo_general
        
        # Load YOLO model
        if model_path is None:
            model_path = MODELS_DIR / "traffic_sign_yolo11n.pt"
            
        self.model_path = Path(model_path)
        self.model = self._load_model()
        
        # Sign tracking (memory)
        self.current_speed_limit = None
        self.speed_limit_frames = 0
        self.last_detected_signs = []
        
        # Statistics
        self.total_detections = 0
        self.frame_count = 0
        
        print(f"✅ TSR initialized: {self.model_path.name}")
    
    def _load_model(self):
        """Load YOLO model for traffic sign detection"""
        try:
            from ultralytics import YOLO
            
            # Try to load traffic sign model
            if self.model_path.exists():
                print(f"📦 Loading TSR model: {self.model_path}")
                return YOLO(str(self.model_path))
            
            # Fallback to general YOLO11
            if self.use_yolo_general:
                general_model = MODELS_DIR / "yolo11n.pt"
                print(f"⚠️  TSR model not found, using general YOLO: {general_model}")
                return YOLO(str(general_model))
            
            raise FileNotFoundError(f"TSR model not found: {self.model_path}")
            
        except Exception as e:
            print(f"❌ Failed to load TSR model: {e}")
            raise
    
    def detect_signs(
        self,
        frame: np.ndarray
    ) -> List[Dict]:
        """
        Detect traffic signs in frame
        
        Args:
            frame: Input image (BGR)
            
        Returns:
            List of detected signs with bbox, class, confidence
        """
        self.frame_count += 1
        
        # Run YOLO detection
        results = self.model.predict(
            frame,
            conf=self.conf_threshold,
            iou=TSR_IOU_THRESHOLD,
            verbose=False
        )
        
        detections = []
        
        if results and len(results) > 0:
            result = results[0]
            
            if result.boxes is not None and len(result.boxes) > 0:
                boxes = result.boxes.xyxy.cpu().numpy()
                confidences = result.boxes.conf.cpu().numpy()
                class_ids = result.boxes.cls.cpu().numpy().astype(int)
                
                for i, (box, conf, cls_id) in enumerate(zip(boxes, confidences, class_ids)):
                    x1, y1, x2, y2 = box
                    width = x2 - x1
                    height = y2 - y1
                    
                    # Filter small detections
                    if width < TSR_MIN_SIZE or height < TSR_MIN_SIZE:
                        continue
                    
                    # Get sign class name
                    sign_class = TRAFFIC_SIGN_CLASSES.get(cls_id, f"unknown_{cls_id}")
                    
                    detection = {
                        'bbox': [int(x1), int(y1), int(x2), int(y2)],
                        'confidence': float(conf),
                        'class_id': cls_id,
                        'class_name': sign_class,
                        'width': width,
                        'height': height,
                    }
                    
                    # Extract speed limit if applicable
                    if sign_class in SPEED_LIMITS:
                        detection['speed_limit'] = SPEED_LIMITS[sign_class]
                    
                    detections.append(detection)
                    self.total_detections += 1
        
        # Update sign memory
        self.last_detected_signs = detections
        self._update_speed_limit_memory(detections)
        
        return detections
    
    def _update_speed_limit_memory(self, detections: List[Dict]):
        """
        Update speed limit memory with temporal smoothing
        
        Args:
            detections: List of current detections
        """
        # Find speed limit signs in current detections
        speed_limits = [d['speed_limit'] for d in detections if 'speed_limit' in d]
        
        if speed_limits:
            # Use the lowest speed limit detected (most restrictive)
            new_limit = min(speed_limits)
            
            if new_limit == self.current_speed_limit:
                # Extend memory if same limit detected
                self.speed_limit_frames = min(self.speed_limit_frames + 1, TSR_MEMORY_FRAMES)
            else:
                # New speed limit detected
                self.current_speed_limit = new_limit
                self.speed_limit_frames = TSR_MEMORY_FRAMES
        else:
            # No speed limit detected, decay memory
            if self.speed_limit_frames > 0:
                self.speed_limit_frames -= 1
            else:
                self.current_speed_limit = None
    
    def get_current_speed_limit(self) -> Optional[int]:
        """
        Get current active speed limit
        
        Returns:
            Current speed limit in km/h or None
        """
        return self.current_speed_limit if self.speed_limit_frames > 0 else None
    
    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Dict],
        show_all: bool = True
    ) -> np.ndarray:
        """
        Draw traffic sign detections on frame
        
        Args:
            frame: Input image
            detections: List of detections from detect_signs()
            show_all: Show all signs or only speed limits
            
        Returns:
            Annotated frame
        """
        output = frame.copy()
        
        for det in detections:
            # Skip non-speed-limit signs if show_all=False
            if not show_all and 'speed_limit' not in det:
                continue
            
            x1, y1, x2, y2 = det['bbox']
            conf = det['confidence']
            class_name = det['class_name']
            
            # Color based on sign type
            if 'speed_limit' in det:
                color = COLOR_RED
                label = f"{det['speed_limit']} km/h ({conf:.2f})"
            else:
                color = COLOR_YELLOW
                label = f"{class_name} ({conf:.2f})"
            
            # Draw bounding box
            cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
            
            # Draw label background
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(
                output,
                (x1, y1 - label_size[1] - 10),
                (x1 + label_size[0], y1),
                color,
                -1
            )
            
            # Draw label text
            cv2.putText(
                output,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                COLOR_WHITE,
                2
            )
        
        return output
    
    def get_stats(self) -> Dict:
        """Get TSR statistics"""
        return {
            'total_detections': self.total_detections,
            'frames_processed': self.frame_count,
            'current_speed_limit': self.get_current_speed_limit(),
            'active_signs': len(self.last_detected_signs),
        }
    
    def reset(self):
        """Reset TSR state"""
        self.current_speed_limit = None
        self.speed_limit_frames = 0
        self.last_detected_signs = []
