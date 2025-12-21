"""
TRAFFIC SIGN RECOGNITION MODULE - YOLOv11
==========================================
Detects and classifies traffic signs from dashcam video.

Supported Signs:
- Stop sign
- Speed limit signs
- Warning signs
- Yield sign
- Traffic lights

Features:
- YOLOv11-based detection
- Sign classification
- Real-time recognition

Author: Senior ADAS Engineer
Date: 2025-12-21
"""

import cv2
import numpy as np
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class TrafficSignV11:
    """
    Traffic sign recognition using YOLOv11.
    Detects and classifies traffic signs for ADAS applications.
    """
    
    # Common traffic sign classes (can be extended)
    SIGN_CLASSES = {
        'stop sign': 11,      # COCO class ID
        'traffic light': 9,   # COCO class ID
    }
    
    # Additional sign types (if using custom trained model)
    CUSTOM_SIGNS = [
        'speed_limit_30',
        'speed_limit_50',
        'speed_limit_70',
        'speed_limit_90',
        'yield',
        'no_entry',
        'warning'
    ]
    
    def __init__(
        self, 
        model_path: str = None, 
        device: str = "cpu",
        conf_threshold: float = 0.4
    ):
        """
        Initialize traffic sign detector.
        
        Args:
            model_path: Path to YOLOv11 weights (.pt file)
                       Use None for COCO pretrained model
                       Use custom path for traffic sign trained model
            device: "cuda" or "cpu" for inference
            conf_threshold: Confidence threshold for detections
        """
        self.device = device
        self.conf_threshold = conf_threshold
        self.model = None
        self.is_custom_model = model_path is not None
        
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
                    # Extract box data
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    cls_id = int(box.cls[0].cpu().numpy())
                    
                    # Get class name
                    cls_name = result.names[cls_id]
                    
                    # Filter for traffic sign classes
                    sign_type = self.classify_sign(cls_name, cls_id)
                    
                    if sign_type is None:
                        continue  # Not a traffic sign
                    
                    detection = {
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "sign_type": sign_type,
                        "confidence": conf,
                        "bbox": [int(x1), int(y1), int(x2), int(y2)]
                    }
                    
                    detections.append(detection)
            
            return detections
            
        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return []
    
    def classify_sign(self, class_name: str, class_id: int) -> Optional[str]:
        """
        Classify detected object as traffic sign type.
        
        Args:
            class_name: YOLO class name
            class_id: YOLO class ID
            
        Returns:
            Sign type string or None if not a traffic sign
        """
        # COCO model classes
        if class_name == 'stop sign':
            return 'STOP'
        elif class_name == 'traffic light':
            return 'TRAFFIC_LIGHT'
        
        # Custom model classes (if using trained model)
        if self.is_custom_model:
            if 'speed_limit' in class_name:
                # Extract speed from class name
                return class_name.upper().replace('_', ' ')
            elif class_name in self.CUSTOM_SIGNS:
                return class_name.upper().replace('_', ' ')
        
        return None
    
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
                annotated,
                action,
                (x1, y2 + 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2
            )
        
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
