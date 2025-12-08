"""
YOLO Detector
Wrapper cho YOLOv11 detection
"""
import torch
from ultralytics import YOLO
import cv2
import numpy as np
from typing import List, Dict, Any
from pathlib import Path


class YOLODetector:
    """
    YOLO Vehicle Detector (YOLOv11)
    """
    
    def __init__(self, model_path: str = None):
        """
        Args:
            model_path: Đường dẫn đến model weights. Nếu None, dùng yolo11n.pt mặc định
        """
        if model_path is None:
            # Dùng pretrained model
            model_path = "yolo11n.pt"
        
        self.model = YOLO(model_path)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"YOLOv11 Detector initialized on {self.device}")
        
        # COCO classes cho vehicle
        self.vehicle_classes = {
            2: 'car',
            3: 'motorcycle',
            5: 'bus',
            7: 'truck'
        }
    
    def detect(self, frame: np.ndarray, conf_threshold: float = 0.5) -> List[Dict[str, Any]]:
        """
        Detect vehicles trong frame
        
        Args:
            frame: OpenCV image (BGR)
            conf_threshold: Confidence threshold
        
        Returns:
            List of detections:
            [
                {
                    "class_id": int,
                    "class_name": str,
                    "confidence": float,
                    "bbox": [x_center, y_center, width, height],  # normalized
                    "bbox_pixels": [x1, y1, x2, y2],  # pixels
                    "x": int,  # center x in pixels
                    "y": int   # center y in pixels
                }
            ]
        """
        results = self.model(frame, conf=conf_threshold, verbose=False)
        
        detections = []
        
        if len(results) > 0:
            result = results[0]
            boxes = result.boxes
            
            h, w = frame.shape[:2]
            
            for box in boxes:
                class_id = int(box.cls[0])
                
                # Chỉ lấy vehicle classes
                if class_id not in self.vehicle_classes:
                    continue
                
                confidence = float(box.conf[0])
                
                # Bounding box (x1, y1, x2, y2) in pixels
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                
                # Convert to YOLO format (center, width, height) normalized
                x_center = ((x1 + x2) / 2) / w
                y_center = ((y1 + y2) / 2) / h
                width = (x2 - x1) / w
                height = (y2 - y1) / h
                
                detection = {
                    "class_id": class_id,
                    "class_name": self.vehicle_classes[class_id],
                    "confidence": round(confidence, 3),
                    "bbox": [
                        round(x_center, 4),
                        round(y_center, 4),
                        round(width, 4),
                        round(height, 4)
                    ],
                    "bbox_pixels": [
                        int(x1), int(y1), int(x2), int(y2)
                    ],
                    "x": int((x1 + x2) / 2),
                    "y": int((y1 + y2) / 2)
                }
                
                detections.append(detection)
        
        return detections
    
    def detect_and_draw(self, frame: np.ndarray, conf_threshold: float = 0.5) -> tuple:
        """
        Detect và vẽ bounding boxes
        
        Returns:
            (annotated_frame, detections)
        """
        detections = self.detect(frame, conf_threshold)
        
        # Vẽ bounding boxes
        annotated = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = det['bbox_pixels']
            label = f"{det['class_name']} {det['confidence']:.2f}"
            
            # Vẽ box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Vẽ label
            cv2.putText(
                annotated,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )
        
        return annotated, detections
