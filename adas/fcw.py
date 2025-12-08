"""
Forward Collision Warning (FCW) Module
Cảnh báo va chạm phía trước

Features:
- Detect vehicles ahead using YOLO11
- Estimate distance using monocular vision
- Calculate Time-To-Collision (TTC)
- Alert driver if collision risk detected
"""

import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional
import time

from .config import (
    VEHICLE_CLASSES,
    FCW_CONF_THRESHOLD,
    FCW_IOU_THRESHOLD,
    FCW_DANGER_DISTANCE,
    FCW_WARNING_DISTANCE,
    FCW_MIN_TTC,
    FOCAL_LENGTH,
    VEHICLE_SIZES,
    ALERT_NONE,
    ALERT_WARNING,
    ALERT_DANGER,
    COLOR_GREEN,
    COLOR_YELLOW,
    COLOR_RED,
    COLOR_WHITE,
)


class ForwardCollisionWarning:
    """
    Forward Collision Warning System
    
    Detects vehicles ahead and estimates distance using monocular vision.
    Provides collision warnings based on distance and Time-To-Collision.
    """
    
    def __init__(
        self,
        yolo_model,  # Shared YOLO11 model from main system
        focal_length: float = FOCAL_LENGTH,
        conf_threshold: float = FCW_CONF_THRESHOLD,
    ):
        """
        Initialize FCW system
        
        Args:
            yolo_model: YOLO11 model instance (shared from main)
            focal_length: Camera focal length in pixels
            conf_threshold: Confidence threshold for vehicle detection
        """
        self.model = yolo_model
        self.focal_length = focal_length
        self.conf_threshold = conf_threshold
        
        # State tracking
        self.last_vehicles = []
        self.last_distances = {}
        self.last_frame_time = time.time()
        
        # Statistics
        self.total_detections = 0
        self.frame_count = 0
        self.warning_count = 0
        self.danger_count = 0
        
        print("✅ FCW initialized")
    
    def detect_vehicles(
        self,
        frame: np.ndarray
    ) -> List[Dict]:
        """
        Detect vehicles in frame
        
        Args:
            frame: Input image (BGR)
            
        Returns:
            List of detected vehicles with bbox, class, distance, TTC
        """
        self.frame_count += 1
        current_time = time.time()
        dt = current_time - self.last_frame_time
        self.last_frame_time = current_time
        
        # Run YOLO detection
        results = self.model.predict(
            frame,
            conf=self.conf_threshold,
            iou=FCW_IOU_THRESHOLD,
            verbose=False,
            classes=list(VEHICLE_CLASSES.keys())  # Only detect vehicles
        )
        
        detections = []
        
        if results and len(results) > 0:
            result = results[0]
            
            if result.boxes is not None and len(result.boxes) > 0:
                boxes = result.boxes.xyxy.cpu().numpy()
                confidences = result.boxes.conf.cpu().numpy()
                class_ids = result.boxes.cls.cpu().numpy().astype(int)
                
                for box, conf, cls_id in zip(boxes, confidences, class_ids):
                    x1, y1, x2, y2 = box
                    
                    # Get vehicle class
                    vehicle_class = VEHICLE_CLASSES.get(cls_id, "unknown")
                    if vehicle_class == "unknown":
                        continue
                    
                    # Calculate bbox dimensions
                    bbox_width = x2 - x1
                    bbox_height = y2 - y1
                    
                    # Estimate distance
                    distance = self._estimate_distance(
                        bbox_width,
                        bbox_height,
                        vehicle_class
                    )
                    
                    # Calculate Time-To-Collision
                    ttc = self._calculate_ttc(
                        vehicle_id=f"{int(x1)}_{int(y1)}",
                        current_distance=distance,
                        dt=dt
                    )
                    
                    # Determine alert level
                    alert_level = self._get_alert_level(distance, ttc)
                    
                    detection = {
                        'bbox': [int(x1), int(y1), int(x2), int(y2)],
                        'confidence': float(conf),
                        'class_id': cls_id,
                        'class_name': vehicle_class,
                        'distance': distance,
                        'ttc': ttc,
                        'alert_level': alert_level,
                        'bbox_width': bbox_width,
                        'bbox_height': bbox_height,
                    }
                    
                    detections.append(detection)
                    self.total_detections += 1
                    
                    # Update statistics
                    if alert_level == ALERT_WARNING:
                        self.warning_count += 1
                    elif alert_level == ALERT_DANGER:
                        self.danger_count += 1
        
        self.last_vehicles = detections
        return detections
    
    def _estimate_distance(
        self,
        bbox_width: float,
        bbox_height: float,
        vehicle_class: str
    ) -> float:
        """
        Estimate distance to vehicle using monocular vision
        
        Uses similar triangles principle:
        distance = (real_width * focal_length) / bbox_width
        
        Args:
            bbox_width: Bounding box width in pixels
            bbox_height: Bounding box height in pixels
            vehicle_class: Type of vehicle (car, truck, bus, motorcycle)
            
        Returns:
            Estimated distance in meters
        """
        # Get real-world vehicle dimensions
        if vehicle_class in VEHICLE_SIZES:
            real_width, real_height = VEHICLE_SIZES[vehicle_class]
        else:
            real_width, real_height = VEHICLE_SIZES["car"]  # Default
        
        # Calculate distance using width and height, then average
        if bbox_width > 0:
            distance_from_width = (real_width * self.focal_length) / bbox_width
        else:
            distance_from_width = 100.0  # Default far distance
        
        if bbox_height > 0:
            distance_from_height = (real_height * self.focal_length) / bbox_height
        else:
            distance_from_height = 100.0
        
        # Average the two estimates for better accuracy
        distance = (distance_from_width + distance_from_height) / 2.0
        
        # Clamp to reasonable range (1-200 meters)
        distance = max(1.0, min(distance, 200.0))
        
        return distance
    
    def _calculate_ttc(
        self,
        vehicle_id: str,
        current_distance: float,
        dt: float
    ) -> Optional[float]:
        """
        Calculate Time-To-Collision (TTC)
        
        TTC = distance / relative_velocity
        
        Args:
            vehicle_id: Unique ID for vehicle tracking
            current_distance: Current distance to vehicle (meters)
            dt: Time since last frame (seconds)
            
        Returns:
            TTC in seconds or None if not approaching
        """
        if vehicle_id in self.last_distances:
            last_distance = self.last_distances[vehicle_id]
            
            # Calculate relative velocity (negative = approaching)
            if dt > 0:
                relative_velocity = (current_distance - last_distance) / dt
                
                # Only calculate TTC if approaching (velocity < 0)
                if relative_velocity < -0.5:  # At least 0.5 m/s closing speed
                    ttc = current_distance / abs(relative_velocity)
                    self.last_distances[vehicle_id] = current_distance
                    return ttc
        
        # Update distance history
        self.last_distances[vehicle_id] = current_distance
        return None
    
    def _get_alert_level(
        self,
        distance: float,
        ttc: Optional[float]
    ) -> int:
        """
        Determine alert level based on distance and TTC
        
        Args:
            distance: Distance to vehicle (meters)
            ttc: Time-To-Collision (seconds)
            
        Returns:
            Alert level (ALERT_NONE, ALERT_WARNING, ALERT_DANGER)
        """
        # Critical danger zone
        if distance < FCW_DANGER_DISTANCE:
            return ALERT_DANGER
        
        # TTC-based danger
        if ttc is not None and ttc < FCW_MIN_TTC:
            return ALERT_DANGER
        
        # Warning zone
        if distance < FCW_WARNING_DISTANCE:
            return ALERT_WARNING
        
        # TTC-based warning
        if ttc is not None and ttc < FCW_MIN_TTC * 2:
            return ALERT_WARNING
        
        return ALERT_NONE
    
    def get_closest_vehicle(self) -> Optional[Dict]:
        """
        Get the closest vehicle detection
        
        Returns:
            Closest vehicle dict or None
        """
        if not self.last_vehicles:
            return None
        
        return min(self.last_vehicles, key=lambda v: v['distance'])
    
    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Dict],
        show_all: bool = True
    ) -> np.ndarray:
        """
        Draw FCW detections on frame
        
        Args:
            frame: Input image
            detections: List of vehicle detections
            show_all: Show all vehicles or only dangerous ones
            
        Returns:
            Annotated frame
        """
        output = frame.copy()
        
        for det in detections:
            alert_level = det['alert_level']
            
            # Skip safe vehicles if show_all=False
            if not show_all and alert_level == ALERT_NONE:
                continue
            
            x1, y1, x2, y2 = det['bbox']
            conf = det['confidence']
            vehicle_class = det['class_name']
            distance = det['distance']
            ttc = det['ttc']
            
            # Color based on alert level
            if alert_level == ALERT_DANGER:
                color = COLOR_RED
                thickness = 3
            elif alert_level == ALERT_WARNING:
                color = COLOR_YELLOW
                thickness = 2
            else:
                color = COLOR_GREEN
                thickness = 2
            
            # Draw bounding box
            cv2.rectangle(output, (x1, y1), (x2, y2), color, thickness)
            
            # Prepare label
            label = f"{vehicle_class}: {distance:.1f}m"
            if ttc is not None:
                label += f" | TTC: {ttc:.1f}s"
            
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
            
            # Draw danger warning
            if alert_level == ALERT_DANGER:
                warning_text = "⚠ COLLISION WARNING ⚠"
                text_size, _ = cv2.getTextSize(warning_text, cv2.FONT_HERSHEY_DUPLEX, 1.2, 3)
                text_x = (frame.shape[1] - text_size[0]) // 2
                text_y = 60
                
                cv2.putText(
                    output,
                    warning_text,
                    (text_x, text_y),
                    cv2.FONT_HERSHEY_DUPLEX,
                    1.2,
                    COLOR_RED,
                    3
                )
        
        return output
    
    def get_stats(self) -> Dict:
        """Get FCW statistics"""
        return {
            'total_detections': self.total_detections,
            'frames_processed': self.frame_count,
            'warning_count': self.warning_count,
            'danger_count': self.danger_count,
            'active_vehicles': len(self.last_vehicles),
        }
    
    def reset(self):
        """Reset FCW state"""
        self.last_vehicles = []
        self.last_distances = {}
        self.last_frame_time = time.time()
