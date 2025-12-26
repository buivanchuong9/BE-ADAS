"""
OBJECT DETECTION MODULE - YOLOv11 with Tracking
================================================
Detects and tracks vehicles and pedestrians from dashcam video using YOLOv11.
Integrated with ByteTrack for persistent object IDs.

Supported classes:
- car, truck, bus (vehicles)
- motorcycle, bicycle (two-wheelers)
- person (pedestrians)

Features:
- CPU/GPU inference with automatic device selection
- Multi-object tracking with persistent IDs
- Confidence filtering
- Vietnamese traffic optimized

Author: Senior ADAS Engineer
Date: 2025-12-26 (Production Enhancement)
"""

import cv2
import numpy as np
from typing import List, Dict, Optional
import logging

from .object_tracker import ByteTracker

logger = logging.getLogger(__name__)


class ObjectDetectorV11:
    """
    YOLOv11-based object detector with ByteTrack integration.
    Production-grade tracking for Vietnamese traffic conditions.
    """
    
    # COCO class IDs for relevant objects
    ADAS_CLASSES = {
        'person': 0,
        'bicycle': 1,
        'car': 2,
        'motorcycle': 3,
        'bus': 5,
        'truck': 7
    }
    
    # Class names mapping
    CLASS_NAMES = {
        0: 'person',
        1: 'bicycle',
        2: 'car',
        3: 'motorcycle',
        5: 'bus',
        7: 'truck'
    }
    
    def __init__(
        self, 
        model_path: str = None, 
        device: str = "cpu", 
        conf_threshold: float = 0.25,
        enable_tracking: bool = True
    ):
        """
        Initialize object detector with tracking.
        
        Args:
            model_path: Path to YOLOv11 weights (.pt file)
            device: "cuda" or "cpu" for inference
            conf_threshold: Confidence threshold for detections
            enable_tracking: Enable ByteTrack multi-object tracking
        """
        self.device = device
        self.conf_threshold = conf_threshold
        self.enable_tracking = enable_tracking
        self.model = None
        
        # Initialize tracker
        if self.enable_tracking:
            self.tracker = ByteTracker(
                track_thresh=0.5,
                match_thresh=0.8,
                track_buffer=30,
                frame_rate=30
            )
        else:
            self.tracker = None
        
        # Try to load YOLOv11 model
        try:
            from ultralytics import YOLO
            
            # Use default YOLOv11n if no path specified
            if model_path is None:
                model_path = "yolo11n.pt"  # Lightweight model for CPU
            
            self.model = YOLO(model_path)
            logger.info(f"YOLOv11 loaded from {model_path} on {device}")
            
        except ImportError:
            logger.error("ultralytics package not installed. Install: pip install ultralytics")
            raise
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise
    
    def detect(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect objects in frame.
        
        Args:
            frame: RGB frame from video
            
        Returns:
            List of detections, each containing:
                - class_id: Integer class ID
                - class_name: String class name
                - confidence: Detection confidence (0-1)
                - bbox: [x1, y1, x2, y2] bounding box
                - center: [cx, cy] center point
                - area: Bounding box area
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
                    
                    # Filter for ADAS-relevant classes only
                    if cls_name not in self.ADAS_CLASSES:
                        continue
                    
                    # Calculate center and area
                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)
                    area = (x2 - x1) * (y2 - y1)
                    
                    detection = {
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "confidence": conf,
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "center": [cx, cy],
                        "area": float(area)
                    }
                    
                    detections.append(detection)
            
            return detections
            
        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return []
    
    def detect_and_track(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect and track objects with persistent IDs.
        PRODUCTION METHOD: Use this for real ADAS processing.
        
        Args:
            frame: RGB frame from video
            
        Returns:
            List of tracked objects with:
                - id: Persistent track ID
                - class_id: Object class ID
                - class_name: Object class name
                - confidence: Detection confidence
                - bbox: [x1, y1, x2, y2] bounding box
                - center: [cx, cy] center point
                - velocity: [vx, vy] in pixels/frame
                - speed: Scalar speed in pixels/frame
                - hits: Number of times detected
                - age: Track age in frames
        """
        # Get detections
        detections = self.detect(frame)
        
        if not self.enable_tracking or self.tracker is None:
            # Return detections without tracking
            return detections
        
        # Update tracker
        tracked_objects = self.tracker.update(detections)
        
        # Add class names to tracked objects
        for obj in tracked_objects:
            obj['class_name'] = self.CLASS_NAMES.get(obj['class_id'], 'unknown')
            
            # Calculate center from bbox
            bbox = obj['bbox']
            obj['center'] = [
                int((bbox[0] + bbox[2]) / 2),
                int((bbox[1] + bbox[3]) / 2)
            ]
        
        return tracked_objects
    
    def filter_front_vehicles(self, detections: List[Dict], frame_height: int) -> List[Dict]:
        """
        Filter detections to keep only vehicles in front (lower half of frame).
        
        Args:
            detections: List of all detections
            frame_height: Frame height in pixels
            
        Returns:
            Filtered list of front vehicle detections
        """
        front_vehicles = []
        
        vehicle_classes = ['car', 'truck', 'bus', 'motorcycle']
        mid_y = frame_height / 2
        
        for det in detections:
            # Check if it's a vehicle
            if det['class_name'] not in vehicle_classes:
                continue
            
            # Check if in lower half of frame (vehicles in front)
            bbox = det['bbox']
            center_y = (bbox[1] + bbox[3]) / 2
            
            if center_y > mid_y:
                front_vehicles.append(det)
        
        return front_vehicles
    
    def get_closest_vehicle(self, detections: List[Dict]) -> Optional[Dict]:
        """
        Get closest vehicle (largest bbox area).
        
        Args:
            detections: List of vehicle detections
            
        Returns:
            Detection dict of closest vehicle or None
        """
        if not detections:
            return None
        
        # Closest vehicle has largest bbox (bottom area of frame)
        closest = max(detections, key=lambda x: x['area'])
        return closest
    
    def draw_detections(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """
        Draw bounding boxes and labels on frame.
        
        Args:
            frame: RGB frame
            detections: List of detections
            
        Returns:
            Annotated frame
        """
        annotated = frame.copy()
        
        # Color mapping for different classes
        color_map = {
            'person': (255, 0, 0),      # Red
            'bicycle': (255, 165, 0),   # Orange
            'motorcycle': (255, 165, 0), # Orange
            'car': (0, 255, 0),         # Green
            'truck': (0, 255, 255),     # Cyan
            'bus': (0, 255, 255)        # Cyan
        }
        
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cls_name = det['class_name']
            conf = det['confidence']
            
            # Get color
            color = color_map.get(cls_name, (255, 255, 255))
            
            # Draw bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            
            # Draw label
            label = f"{cls_name}: {conf:.2f}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            
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
                0.6, 
                (0, 0, 0), 
                2
            )
        
        return annotated
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Process frame for object detection.
        
        Args:
            frame: RGB frame from video
            
        Returns:
            Dict containing:
                - annotated_frame: Frame with bounding boxes
                - detections: List of all detections
                - front_vehicles: List of vehicles in front
                - closest_vehicle: Closest vehicle detection
                - vehicle_count: Number of detected vehicles
                - pedestrian_count: Number of detected pedestrians
        """
        height, width = frame.shape[:2]
        
        # Detect objects
        detections = self.detect(frame)
        
        # Filter front vehicles
        front_vehicles = self.filter_front_vehicles(detections, height)
        
        # Get closest vehicle
        closest_vehicle = self.get_closest_vehicle(front_vehicles)
        
        # Count objects
        vehicle_classes = ['car', 'truck', 'bus', 'motorcycle']
        vehicle_count = sum(1 for d in detections if d['class_name'] in vehicle_classes)
        pedestrian_count = sum(1 for d in detections if d['class_name'] in ['person', 'bicycle'])
        
        # Draw detections
        annotated_frame = self.draw_detections(frame, detections)
        
        return {
            "annotated_frame": annotated_frame,
            "detections": detections,
            "front_vehicles": front_vehicles,
            "closest_vehicle": closest_vehicle,
            "vehicle_count": vehicle_count,
            "pedestrian_count": pedestrian_count
        }


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    
    try:
        detector = ObjectDetectorV11(device="cpu")
        print("Object Detector initialized successfully")
    except Exception as e:
        print(f"Failed to initialize: {e}")
