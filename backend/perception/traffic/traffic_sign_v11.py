"""
TRAFFIC SIGN RECOGNITION MODULE - YOLOv11
==========================================
Detects and classifies traffic signs from dashcam video.

PRODUCTION FEATURES (Phase 7):
- Vietnamese traffic sign recognition
- Speed limit violation detection
- Sign persistence (avoid re-detecting same sign)
- GPS/location association (if available)
- Temporal consistency validation

Supported Vietnamese Signs:
- Biển báo dừng (Stop sign)
- Biển giới hạn tốc độ (Speed limit: 30, 40, 50, 60, 70, 80, 90, 100, 110, 120 km/h)
- Biển báo cấm (No entry, No parking)
- Biển cảnh báo (Warning signs)
- Đèn tín hiệu giao thông (Traffic lights)

Features:
- YOLOv11-based detection with Vietnamese customization
- Speed violation logic (compares detected limit with vehicle speed)
- Sign deduplication (same sign not reported multiple times)
- Confidence-based filtering for Vietnamese road conditions

Author: Senior ADAS Engineer
Date: 2025-12-26 (Phase 7 Enhancement)
"""

import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from collections import deque
import logging

logger = logging.getLogger(__name__)


class SignTracker:
    """
    Tracks detected signs to avoid duplicate alerts.
    Uses spatial and temporal consistency.
    """
    
    def __init__(self, persistence_frames: int = 90, iou_threshold: float = 0.5):
        """
        Initialize sign tracker.
        
        Args:
            persistence_frames: Frames to remember a sign (90 = 3s @ 30fps)
            iou_threshold: IoU threshold for same sign detection
        """
        self.persistence_frames = persistence_frames
        self.iou_threshold = iou_threshold
        
        # Tracked signs: {sign_id: {'bbox', 'type', 'last_seen', 'count', 'speed_limit'}}
        self.tracked_signs = {}
        self.next_sign_id = 1
        self.frame_number = 0
    
    def _iou(self, bbox1: List[int], bbox2: List[int]) -> float:
        """Calculate Intersection over Union between two bboxes."""
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # Intersection
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        
        if x2_i < x1_i or y2_i < y1_i:
            return 0.0
        
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        
        # Union
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    def update(self, detections: List[Dict]) -> List[Dict]:
        """
        Update tracker with new detections.
        
        Args:
            detections: List of sign detections
            
        Returns:
            List of NEW signs (first time detected or re-appeared)
        """
        self.frame_number += 1
        new_signs = []
        
        for detection in detections:
            bbox = detection['bbox']
            sign_type = detection['sign_type']
            
            # Check if matches existing sign
            matched_id = None
            for sign_id, sign_data in self.tracked_signs.items():
                if sign_data['type'] == sign_type:
                    iou = self._iou(bbox, sign_data['bbox'])
                    if iou >= self.iou_threshold:
                        matched_id = sign_id
                        break
            
            if matched_id:
                # Update existing sign
                self.tracked_signs[matched_id]['last_seen'] = self.frame_number
                self.tracked_signs[matched_id]['count'] += 1
                self.tracked_signs[matched_id]['bbox'] = bbox  # Update position
            else:
                # New sign
                sign_id = self.next_sign_id
                self.next_sign_id += 1
                
                self.tracked_signs[sign_id] = {
                    'bbox': bbox,
                    'type': sign_type,
                    'last_seen': self.frame_number,
                    'count': 1,
                    'speed_limit': detection.get('speed_limit')
                }
                
                # Add sign ID to detection
                detection['sign_id'] = sign_id
                detection['is_new'] = True
                new_signs.append(detection)
        
        # Remove old signs
        to_remove = [
            sign_id for sign_id, sign_data in self.tracked_signs.items()
            if self.frame_number - sign_data['last_seen'] > self.persistence_frames
        ]
        
        for sign_id in to_remove:
            del self.tracked_signs[sign_id]
        
        return new_signs


class TrafficSignV11:
    """
    Traffic sign recognition using YOLOv11.
    Detects and classifies traffic signs for ADAS applications.
    """
    
    # Common traffic sign classes (Vietnamese road context)
    SIGN_CLASSES = {
        'stop sign': 11,      # COCO class ID
        'traffic light': 9,   # COCO class ID
    }
    
    # Vietnamese speed limit signs (custom trained model)
    VIETNAMESE_SPEED_LIMITS = [30, 40, 50, 60, 70, 80, 90, 100, 110, 120]
    
    # Additional sign types (if using custom trained model)
    CUSTOM_SIGNS = [
        'speed_limit_30', 'speed_limit_40', 'speed_limit_50', 'speed_limit_60',
        'speed_limit_70', 'speed_limit_80', 'speed_limit_90', 'speed_limit_100',
        'speed_limit_110', 'speed_limit_120',
        'yield', 'no_entry', 'no_parking', 'warning', 'pedestrian_crossing',
        'school_zone', 'construction'
    ]
    
    def __init__(
        self, 
        model_path: str = None, 
        device: str = "cpu",
        conf_threshold: float = 0.4,
        enable_tracking: bool = True
    ):
        """
        Initialize traffic sign detector.
        
        Args:
            model_path: Path to YOLOv11 weights (.pt file)
                       Use None for COCO pretrained model
                       Use custom path for Vietnamese traffic sign trained model
            device: "cuda" or "cpu" for inference
            conf_threshold: Confidence threshold for detections
            enable_tracking: Enable sign tracking to avoid duplicates
        """
        self.device = device
        self.conf_threshold = conf_threshold
        self.model = None
        self.is_custom_model = model_path is not None
        
        # Sign tracking (PRODUCTION)
        self.enable_tracking = enable_tracking
        self.tracker = SignTracker(persistence_frames=90, iou_threshold=0.5) if enable_tracking else None
        
        # Current speed limit (updated when speed limit sign detected)
        self.current_speed_limit = None  # km/h
        self.speed_limit_confidence = 0.0
        
        # Try to load YOLOv11 model
        try:
            from ultralytics import YOLO
            
            # Use default YOLOv11n if no path specified
            if model_path is None:
                model_path = "yolo11n.pt"  # COCO pretrained
                logger.info("Using COCO pretrained model (limited to stop signs and traffic lights)")
            
            self.model = YOLO(model_path)
            logger.info(f"Traffic Sign Detector loaded from {model_path} on {device}")
            
        except ImportError:
            logger.error("ultralytics package not installed. Install: pip install ultralytics")
            raise
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise
    
    def detect(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect traffic signs in frame.
        
        Args:
            frame: RGB frame from video
            
        Returns:
            List of sign detections, each containing:
                - class_id: Integer class ID
                - class_name: String class name
                - sign_type: Traffic sign type
                - confidence: Detection confidence (0-1)
                - bbox: [x1, y1, x2, y2] bounding box
        """
        if self.model is None:
            logger.warning("Model not loaded")
            return []
        
        try:
            # Run inference
            results = self.model(
                frame, 
                device=self.device,
                conf=self.conf_threshold,
                verbose=False
            )
            
            detections = []
            
            # Extract detections
            for result in results:
                boxes = result.boxes
                
                for box in boxes:
                    # Get box coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    
                    # Get class name
                    cls_name = result.names[cls_id]
                    
                    # Classify sign type
                    sign_type, speed_limit = self.classify_sign(cls_name, cls_id)
                    
                    if sign_type is None:
                        continue  # Not a traffic sign
                    
                    detection = {
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "sign_type": sign_type,
                        "confidence": conf,
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "speed_limit": speed_limit  # None if not a speed limit sign
                    }
                    
                    detections.append(detection)
            
            return detections
            
        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return []
    
    def classify_sign(self, class_name: str, class_id: int) -> Tuple[Optional[str], Optional[int]]:
        """
        Classify detected object as traffic sign type (Vietnamese context).
        
        Args:
            class_name: YOLO class name
            class_id: YOLO class ID
            
        Returns:
            Tuple of (sign_type, speed_limit) or (None, None) if not a traffic sign
        """
        # COCO model classes
        if class_name == 'stop sign':
            return ('STOP', None)
        elif class_name == 'traffic light':
            return ('TRAFFIC_LIGHT', None)
        
        # Custom model classes (if using trained model for Vietnamese signs)
        if self.is_custom_model:
            if 'speed_limit' in class_name:
                # Extract speed from class name (e.g., "speed_limit_50" → 50)
                try:
                    speed = int(class_name.split('_')[-1])
                    if speed in self.VIETNAMESE_SPEED_LIMITS:
                        return (f'SPEED_LIMIT_{speed}', speed)
                except ValueError:
                    pass
            elif class_name in self.CUSTOM_SIGNS:
                sign_type = class_name.upper().replace('_', ' ')
                return (sign_type, None)
        
        return (None, None)
    
    def get_sign_action(self, sign_type: str) -> str:
        """
        Get recommended action for detected sign.
        
        Args:
            sign_type: Traffic sign type
            
        Returns:
            Action string
        """
        actions = {
            'STOP': 'STOP REQUIRED',
            'TRAFFIC_LIGHT': 'CHECK TRAFFIC LIGHT',
            'YIELD': 'YIELD TO TRAFFIC',
            'NO_ENTRY': 'DO NOT ENTER',
            'WARNING': 'CAUTION AHEAD'
        }
        
        # Speed limits
        if 'SPEED LIMIT' in sign_type:
            return f'SPEED LIMIT: {sign_type.split()[-1]} km/h'
        
        return actions.get(sign_type, 'OBSERVE SIGN')
    
    def draw_signs(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """
        Draw traffic sign detections on frame.
        
        Args:
            frame: RGB frame
            detections: List of sign detections
            
        Returns:
            Annotated frame
        """
        annotated = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            sign_type = det['sign_type']
            conf = det['confidence']
            
            # Color based on sign type
            if sign_type == 'STOP':
                color = (0, 0, 255)  # Red
            elif sign_type == 'TRAFFIC_LIGHT':
                color = (0, 255, 255)  # Yellow
            elif 'SPEED LIMIT' in sign_type:
                color = (255, 0, 0)  # Blue
            else:
                color = (0, 165, 255)  # Orange
            
            # Draw bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
            
            # Draw label
            label = f"{sign_type}: {conf:.2f}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            
            # Background for text
            cv2.rectangle(
                annotated, 
                (x1, y1 - label_size[1] - 10), 
                (x1 + label_size[0], y1), 
                color, 
                -1
            )
            
            # Text
            cv2.putText(
                annotated, 
                label, 
                (x1, y1 - 5), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.7, 
                (255, 255, 255), 
                2
            )
            
            # Get action
            action = self.get_sign_action(sign_type)
            
            # Draw action below bbox
            cv2.putText(
                0.6,
                color,
                2
            )
    
    def check_speed_violation(
        self,
        vehicle_speed: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Check if vehicle speed violates current speed limit.
        
        Args:
            vehicle_speed: Current vehicle speed in km/h
                          (from GPS, CAN bus, or estimation)
            
        Returns:
            Dict with violation info, or None if no violation
        """
        if self.current_speed_limit is None or vehicle_speed is None:
            return None
        
        # Check violation (with 5 km/h tolerance)
        tolerance = 5.0
        if vehicle_speed > self.current_speed_limit + tolerance:
            overspeed = vehicle_speed - self.current_speed_limit
            violation_severity = "CRITICAL" if overspeed > 20 else "WARNING"
            
            return {
                "is_violation": True,
                "severity": violation_severity,
                "current_speed": vehicle_speed,
                "speed_limit": self.current_speed_limit,
                "overspeed_amount": overspeed,
                "message_vi": f"Vượt tốc độ! Giới hạn {self.current_speed_limit} km/h, đang đi {vehicle_speed:.0f} km/h"
            }
        
        return None
    
    def process_frame_with_tracking(
        self,
        frame: np.ndarray,
        vehicle_speed: Optional[float] = None
    ) -> Dict:
        """
        Process frame with sign tracking and speed violation detection (PRODUCTION).
        
        Args:
            frame: RGB frame from video
            vehicle_speed: Current vehicle speed in km/h (optional)
            
        Returns:
            Dict containing:
                - annotated_frame: Frame with sign overlays
                - detections: List of ALL sign detections
                - new_signs: List of NEW signs (not seen recently)
                - sign_count: Number of detected signs
                - critical_signs: List of critical signs (STOP, etc.)
                - current_speed_limit: Active speed limit (km/h)
                - speed_violation: Violation info if speeding
        """
        # Detect signs
        detections = self.detect(frame)
        
        # Update speed limit if detected
        for det in detections:
            if det.get('speed_limit'):
                # Update current speed limit (use highest confidence)
                if (self.current_speed_limit is None or 
                    det['confidence'] > self.speed_limit_confidence):
                    self.current_speed_limit = det['speed_limit']
                    self.speed_limit_confidence = det['confidence']
        
        # Track signs to identify new ones
        new_signs = []
        if self.enable_tracking and self.tracker:
            new_signs = self.tracker.update(detections)
        else:
            new_signs = detections
        
        # Check speed violation
        speed_violation = self.check_speed_violation(vehicle_speed)
        
        # Identify critical signs
        critical_types = ['STOP', 'YIELD', 'NO_ENTRY']
        critical_signs = [
            d for d in detections 
            if d['sign_type'] in critical_types
        ]
        
        # Draw detections
        annotated_frame = self.draw_signs(frame, detections)
        
        # Add speed limit overlay
        if self.current_speed_limit:
            cv2.putText(
                annotated_frame,
                f"Gioi han: {self.current_speed_limit} km/h",
                (10, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )
        
        # Add speed violation warning
        if speed_violation:
            cv2.putText(
                annotated_frame,
                speed_violation['message_vi'],
                (10, frame.shape[0] - 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 0, 255),
                3
            )
        
        return {
            "annotated_frame": annotated_frame,
            "detections": detections,
            "new_signs": new_signs,
            "sign_count": len(detections),
            "critical_signs": critical_signs,
            "current_speed_limit": self.current_speed_limit,
            "speed_violation": speed_violation
        }
    
        
        return annotated
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Process frame for traffic sign recognition.
        
        Args:
            frame: RGB frame from video
            
        Returns:
            Dict containing:
                - annotated_frame: Frame with sign overlays
                - detections: List of sign detections
                - sign_count: Number of detected signs
                - critical_signs: List of critical signs (STOP, etc.)
        """
        # Detect signs
        detections = self.detect(frame)
        
        # Identify critical signs
        critical_types = ['STOP', 'YIELD', 'NO_ENTRY']
        critical_signs = [
            d for d in detections 
            if d['sign_type'] in critical_types
        ]
        
        # Draw detections
        annotated_frame = self.draw_signs(frame, detections)
        
        # Add sign count overlay
        if detections:
            count_text = f"Traffic Signs: {len(detections)}"
            cv2.putText(
                annotated_frame,
                count_text,
                (10, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 0),
                2
            )
        
        return {
            "annotated_frame": annotated_frame,
            "detections": detections,
            "sign_count": len(detections),
            "critical_signs": critical_signs
        }


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    
    try:
        detector = TrafficSignV11(device="cpu")
        print("Traffic Sign Detector initialized successfully")
    except Exception as e:
        print(f"Failed to initialize: {e}")
