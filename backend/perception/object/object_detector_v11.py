"""
OBJECT DETECTION MODULE - YOLOv8/v11 with Vietnamese Traffic Optimization
==========================================================================
Detects and tracks vehicles and pedestrians from dashcam video.
Integrated with ByteTrack for persistent object IDs.

VIETNAM CUSTOM MODEL SUPPORT:
- Automatically detects and uses 'best_vehicle.pt' if available
- Custom classes: Car, Moto_Static, Bus, Truck, Person, Rider
- DANGER alert for Rider (xe máy tạt đầu)
- Ignores Moto_Static (xe máy đứng yên)

Standard COCO classes (fallback):
- car, truck, bus (vehicles)
- motorcycle, bicycle (two-wheelers)
- person (pedestrians)

Features:
- CPU/GPU inference with automatic device selection
- Multi-object tracking with persistent IDs
- Confidence filtering
- Vietnamese traffic optimized

Author: Senior ADAS Engineer
Date: 2026-01-17 (Vietnam Custom Model Integration)
"""

import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple
import logging
from pathlib import Path

from .object_tracker import ByteTracker
from ...core.config import settings

logger = logging.getLogger(__name__)


class ObjectDetectorV11:
    """
    YOLOv8/v11-based object detector with ByteTrack integration.
    Production-grade tracking for Vietnamese traffic conditions.
    
    SMART MODEL DETECTION:
    - Prioritizes 'best_vehicle.pt' (Vietnam custom model)
    - Falls back to standard COCO models
    """
    
    # ========================================
    # VIETNAM CUSTOM MODEL - best_vehicle.pt
    # ========================================
    VIETNAM_CUSTOM_CLASSES = {
        0: 'car',
        1: 'moto_static',      # BỎ QUA - Xe máy đứng yên
        2: 'bus',
        3: 'truck',
        4: 'person',
        5: 'rider'             # CẢNH BÁO DANGER - Xe máy tạt đầu
    }
    
    VIETNAM_LABELS_VI = {
        'car': 'Ô tô',
        'moto_static': 'Xe máy (Đứng)',
        'bus': 'Xe buýt',
        'truck': 'Xe tải',
        'person': 'Người đi bộ',
        'rider': 'Xe máy (Nguy hiểm)'
    }
    
    # ========================================
    # STANDARD COCO CLASSES (Fallback)
    # ========================================
    COCO_ADAS_CLASSES = {
        'person': 0,
        'bicycle': 1,
        'car': 2,
        'motorcycle': 3,
        'bus': 5,
        'truck': 7
    }
    
    COCO_LABELS_VI = {
        'person': 'Người',
        'bicycle': 'Xe đạp',
        'car': 'Ô tô',
        'motorcycle': 'Xe máy',
        'bus': 'Xe buýt',
        'truck': 'Xe tải'
    }
    
    # Class names mapping (will be set dynamically)
    CLASS_NAMES = {}
    VIETNAMESE_LABELS = {}
    
    def __init__(
        self, 
        model_path: str = None, 
        device: str = "cpu", 
        conf_threshold: float = 0.20,  # Lowered for better recall
        enable_tracking: bool = True
    ):
        """
        Initialize object detector with SMART model detection.
        
        PRIORITY:
        1. best_vehicle.pt (Vietnam custom model) - if exists
        2. User-specified model_path
        3. yolo11n.pt (fallback)
        
        Args:
            model_path: Path to YOLO weights (.pt file), None for auto-detect
            device: "cuda" or "cpu" for inference
            conf_threshold: Confidence threshold for detections
            enable_tracking: Enable ByteTrack multi-object tracking
        """
        self.device = device
        self.conf_threshold = conf_threshold
        self.enable_tracking = enable_tracking
        self.model = None
        self.is_vietnam_custom = False  # Flag to track model type
        
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
        
        # ========================================
        # 🚀 SMART MODEL DETECTION - DÙNG CONFIG LINH HOẠT
        # ========================================
        try:
            from ultralytics import YOLO
            
            # Priority 1: Dùng model_path nếu user chỉ định manual
            if model_path is not None:
                logger.info(f"📌 Using MANUAL model path: {model_path}")
            else:
                # Priority 2: Dùng settings.get_yolo_model_path() - TỰ ĐỘNG TÌM MODEL!
                model_path = settings.get_yolo_model_path()
                logger.info(f"🔍 AUTO-DETECTED model from config: {model_path}")
            
            # Kiểm tra file có tồn tại không
            model_file = Path(model_path)
            if not model_file.exists():
                raise FileNotFoundError(f"❌ Model file not found: {model_path}")
            
            # Phát hiện loại model (Vietnam custom hay COCO standard)
            # Check by filename - nếu có "vehicle" hoặc "best" thì là Vietnam custom
            model_name = model_file.stem.lower()
            if "vehicle" in model_name or ("best" in model_name and "lane" not in model_name):
                self.is_vietnam_custom = True
                logger.info(f"🇻🇳 VIETNAM CUSTOM MODEL detected: {model_path}")
                self.CLASS_NAMES = self.VIETNAM_CUSTOM_CLASSES.copy()
                self.VIETNAMESE_LABELS = self.VIETNAM_LABELS_VI.copy()
            else:
                self.is_vietnam_custom = False
                logger.info(f"📦 STANDARD COCO MODEL: {model_path}")
                self.CLASS_NAMES = {v: k for k, v in self.COCO_ADAS_CLASSES.items()}
                self.VIETNAMESE_LABELS = self.COCO_LABELS_VI.copy()
            
            # Load model
            logger.info(f"⏳ Loading YOLO model: {model_path}...")
            self.model = YOLO(model_path)
            logger.info(f"✅ Model loaded successfully on {device}")
            logger.info(f"   📊 Model type: {'Vietnam Custom' if self.is_vietnam_custom else 'Standard COCO'}")
            logger.info(f"   🏷️  Classes: {list(self.CLASS_NAMES.values())}")
            
        except ImportError:
            logger.error("❌ ultralytics package not installed. Install: pip install ultralytics")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to load YOLO model: {e}")
            raise
    
    def detect(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect objects in frame with SMART class filtering.
        
        VIETNAM CUSTOM MODEL:
        - Skips class 1 (moto_static)
        - Adds 'is_danger' flag for class 5 (rider)
        
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
                - is_danger: True if Rider (Vietnam custom only)
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
                    
                    # ========================================
                    # VIETNAM CUSTOM MODEL LOGIC
                    # ========================================
                    if self.is_vietnam_custom:
                        # Get class name from custom mapping
                        cls_name = self.CLASS_NAMES.get(cls_id, 'unknown')
                        
                        # SKIP moto_static (class 1)
                        if cls_id == 1 or cls_name == 'moto_static':
                            continue
                        
                        # Mark Rider as DANGER
                        is_danger = (cls_id == 5 or cls_name == 'rider')
                        
                    # ========================================
                    # STANDARD COCO MODEL LOGIC
                    # ========================================
                    else:
                        # Get class name from YOLO result
                        cls_name = result.names[cls_id]
                        
                        # Filter for ADAS-relevant classes only
                        if cls_name not in self.COCO_ADAS_CLASSES:
                            continue
                        
                        is_danger = False  # No danger flag for COCO
                    
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
                        "area": float(area),
                        "is_danger": is_danger  # True for Rider
                    }
                    
                    detections.append(detection)
            
            return detections
            
        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return []
    
    def detect_batch(self, frames: List[np.ndarray]) -> List[List[Dict]]:
        """
        Batch detection for improved GPU utilization (PRODUCTION OPTIMIZATION).
        Process multiple frames at once to maximize GPU throughput.
        
        Args:
            frames: List of RGB frames
            
        Returns:
            List of detection lists (one per frame)
        """
        if self.model is None:
            logger.warning("Model not loaded")
            return [[] for _ in frames]
        
        if not frames:
            return []
        
        try:
            # Run batch inference
            results = self.model(
                frames,  # List of numpy arrays
                device=self.device,
                conf=self.conf_threshold,
                verbose=False
            )
            
            all_detections = []
            
            # Extract detections for each frame
            for result in results:
                frame_detections = []
                boxes = result.boxes
                
                for box in boxes:
                    # Extract box data
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    cls_id = int(box.cls[0].cpu().numpy())
                    
                    # ========================================
                    # VIETNAM CUSTOM MODEL LOGIC
                    # ========================================
                    if self.is_vietnam_custom:
                        cls_name = self.CLASS_NAMES.get(cls_id, 'unknown')
                        
                        # SKIP moto_static (class 1)
                        if cls_id == 1 or cls_name == 'moto_static':
                            continue
                        
                        is_danger = (cls_id == 5 or cls_name == 'rider')
                        
                    # ========================================
                    # STANDARD COCO MODEL LOGIC
                    # ========================================
                    else:
                        cls_name = result.names[cls_id]
                        
                        # Filter for ADAS-relevant classes only
                        if cls_name not in self.COCO_ADAS_CLASSES:
                            continue
                        
                        is_danger = False
                    
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
                        "area": float(area),
                        "is_danger": is_danger
                    }
                    
                    frame_detections.append(detection)
                
                all_detections.append(frame_detections)
            
            return all_detections
            
        except Exception as e:
            logger.error(f"Batch detection failed: {e}")
            return [[] for _ in frames]
    
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
    
    def check_rider_danger(
        self, 
        detections: List[Dict], 
        frame_width: int, 
        frame_height: int
    ) -> Tuple[bool, Optional[Dict], str]:
        """
        Check for dangerous Rider (xe máy tạt đầu) in Vietnam custom model.
        
        DANGER CRITERIA:
        1. Class is 'rider' (class 5)
        2. Position: Center 1/3 of frame horizontally (tạt giữa)
        3. Position: Lower 2/3 of frame vertically (gần camera)
        4. Large bbox area (close to camera)
        
        Args:
            detections: List of all detections
            frame_width: Frame width in pixels
            frame_height: Frame height in pixels
            
        Returns:
            Tuple of (is_danger, rider_detection, warning_message)
        """
        if not self.is_vietnam_custom:
            return False, None, ""
        
        # Find all riders
        riders = [d for d in detections if d.get('is_danger', False)]
        
        if not riders:
            return False, None, ""
        
        # Define danger zone
        center_x_min = frame_width * 0.33   # Left 1/3
        center_x_max = frame_width * 0.67   # Right 1/3
        lower_y_min = frame_height * 0.33   # Lower 2/3 of frame
        
        # Check each rider
        for rider in riders:
            bbox = rider['bbox']
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            area = rider['area']
            
            # Check if in danger zone (center + close)
            in_center = center_x_min <= center_x <= center_x_max
            is_close = center_y >= lower_y_min
            is_large = area > (frame_width * frame_height * 0.05)  # > 5% of frame
            
            if in_center and is_close:
                # DANGER DETECTED!
                warning = f"⚠️ NGUY HIỂM: Xe máy tạt đầu ở giữa đường! (Conf: {rider['confidence']:.0%})"
                return True, rider, warning
        
        # Riders detected but not in danger zone
        return False, None, ""

    
    def draw_detections(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """
        Draw bounding boxes and labels on frame with Vietnamese text.
        
        VIETNAM CUSTOM MODEL:
        - Rider (class 5): RED box with DANGER warning
        - Other classes: Standard colors
        
        Args:
            frame: RGB frame
            detections: List of detections
            
        Returns:
            Annotated frame
        """
        annotated = frame.copy()
        
        # ========================================
        # COLOR MAPPING
        # ========================================
        # Vietnam custom model colors
        vietnam_color_map = {
            'car': (0, 255, 0),         # Green
            'bus': (0, 255, 255),       # Cyan
            'truck': (0, 255, 255),     # Cyan
            'person': (255, 100, 0),    # Orange
            'rider': (0, 0, 255),       # RED - DANGER!
        }
        
        # Standard COCO colors
        coco_color_map = {
            'person': (255, 0, 0),      # Red
            'bicycle': (255, 165, 0),   # Orange
            'motorcycle': (255, 165, 0), # Orange
            'car': (0, 255, 0),         # Green
            'truck': (0, 255, 255),     # Cyan
            'bus': (0, 255, 255)        # Cyan
        }
        
        color_map = vietnam_color_map if self.is_vietnam_custom else coco_color_map
        
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cls_name = det['class_name']
            conf = det['confidence']
            is_danger = det.get('is_danger', False)
            
            # Get color
            color = color_map.get(cls_name, (255, 255, 255))
            
            # ========================================
            # DANGER ALERT for Rider
            # ========================================
            if is_danger:
                # Thick RED box for Rider
                thickness = 4
                color = (0, 0, 255)  # Pure RED (BGR)
                
                # Draw pulsing effect (double box)
                cv2.rectangle(annotated, (x1-2, y1-2), (x2+2, y2+2), (0, 0, 255), 2)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thickness)
                
                # DANGER label
                label_vi = "⚠️ NGUY HIỂM - XE MÁY TẠT ĐẦU"
                label = f"DANGER - RIDER: {conf:.0%}"
            else:
                # Normal box
                thickness = 2
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thickness)
                
                # Get Vietnamese label
                label_vi = self.VIETNAMESE_LABELS.get(cls_name, cls_name)
                label = f"{cls_name.upper()}: {conf:.0%}"
            
            # ========================================
            # DRAW LABEL
            # ========================================
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            
            # Background for text
            cv2.rectangle(
                annotated, 
                (x1, y1 - label_size[1] - 10), 
                (x1 + label_size[0] + 5, y1), 
                color, 
                -1
            )
            
            # Text with anti-aliasing
            cv2.putText(
                annotated, 
                label, 
                (x1 + 2, y1 - 5), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.6, 
                (255, 255, 255), 
                2,
                cv2.LINE_AA
            )
        
        return annotated
    
    def process_frame(self, frame: np.ndarray) -> Dict:
        """
        Process frame for object detection with Vietnam custom model support.
        
        VIETNAM CUSTOM MODEL:
        - Detects Rider (xe máy tạt đầu)
        - Returns DANGER warning if Rider in danger zone
        
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
                - rider_danger: True if dangerous Rider detected (Vietnam custom only)
                - danger_rider: Rider detection dict if dangerous
                - danger_warning: Warning message for Rider
        """
        height, width = frame.shape[:2]
        
        # Detect objects
        detections = self.detect(frame)
        
        # ========================================
        # VIETNAM CUSTOM MODEL - Check Rider Danger
        # ========================================
        rider_danger, danger_rider, danger_warning = self.check_rider_danger(
            detections, width, height
        )
        
        # Filter front vehicles
        front_vehicles = self.filter_front_vehicles(detections, height)
        
        # Get closest vehicle
        closest_vehicle = self.get_closest_vehicle(front_vehicles)
        
        # Count objects
        if self.is_vietnam_custom:
            vehicle_classes = ['car', 'truck', 'bus', 'rider']
            pedestrian_classes = ['person']
        else:
            vehicle_classes = ['car', 'truck', 'bus', 'motorcycle']
            pedestrian_classes = ['person', 'bicycle']
        
        vehicle_count = sum(1 for d in detections if d['class_name'] in vehicle_classes)
        pedestrian_count = sum(1 for d in detections if d['class_name'] in pedestrian_classes)
        
        # Draw detections
        annotated_frame = self.draw_detections(frame, detections)
        
        # ========================================
        # DRAW DANGER WARNING on frame if needed
        # ========================================
        if rider_danger and danger_warning:
            # Draw big red warning banner at top
            cv2.rectangle(
                annotated_frame,
                (0, 0),
                (width, 60),
                (0, 0, 255),  # Red background
                -1
            )
            cv2.putText(
                annotated_frame,
                danger_warning,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 255),  # White text
                3,
                cv2.LINE_AA
            )
        
        return {
            "annotated_frame": annotated_frame,
            "detections": detections,
            "front_vehicles": front_vehicles,
            "closest_vehicle": closest_vehicle,
            "vehicle_count": vehicle_count,
            "pedestrian_count": pedestrian_count,
            # Vietnam custom model fields
            "rider_danger": rider_danger,
            "danger_rider": danger_rider,
            "danger_warning": danger_warning
        }


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    
    try:
        detector = ObjectDetectorV11(device="cpu")
        print("Object Detector initialized successfully")
    except Exception as e:
        print(f"Failed to initialize: {e}")
