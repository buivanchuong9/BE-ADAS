"""
DISTANCE ESTIMATION MODULE
==========================
Estimates distance to front vehicles using monocular vision.

Method:
- Uses bounding box height and perspective geometry
- Assumes standard vehicle dimensions
- Calibration based on camera parameters

Risk Levels:
- SAFE: > 30 meters
- CAUTION: 15-30 meters
- DANGER: < 15 meters

Author: Senior ADAS Engineer
Date: 2025-12-21
"""

import cv2
import numpy as np
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class DistanceEstimator:
    """
    Monocular distance estimator for ADAS applications.
    Estimates relative distance to vehicles in front.
    """
    
    # Standard vehicle dimensions (meters)
    VEHICLE_DIMENSIONS = {
        'car': {'height': 1.5, 'width': 1.8},
        'truck': {'height': 2.5, 'width': 2.4},
        'bus': {'height': 3.0, 'width': 2.5},
        'motorcycle': {'height': 1.2, 'width': 0.8}
    }
    
    # Risk thresholds (meters)
    SAFE_DISTANCE = 30.0
    CAUTION_DISTANCE = 15.0
    DANGER_DISTANCE = 7.0
    
    def __init__(self, focal_length: float = 700.0, camera_height: float = 1.2):
        """
        Initialize distance estimator.
        
        Args:
            focal_length: Camera focal length in pixels (estimated)
            camera_height: Camera mounting height in meters
        """
        self.focal_length = focal_length
        self.camera_height = camera_height
        
        # Distance history for smoothing
        self.distance_history = []
        self.max_history = 5
        
        logger.info(f"DistanceEstimator initialized (f={focal_length}px, h={camera_height}m)")
    
    def estimate_distance_bbox(
        self, 
        bbox: list, 
        vehicle_type: str,
        frame_height: int
    ) -> float:
        """
        Estimate distance using bounding box height.
        
        Args:
            bbox: [x1, y1, x2, y2] bounding box
            vehicle_type: 'car', 'truck', 'bus', or 'motorcycle'
            frame_height: Frame height in pixels
            
        Returns:
            Estimated distance in meters
        """
        x1, y1, x2, y2 = bbox
        
        # Bounding box height in pixels
        bbox_height = y2 - y1
        
        if bbox_height <= 0:
            return 100.0  # Invalid bbox
        
        # Get real vehicle height
        real_height = self.VEHICLE_DIMENSIONS.get(
            vehicle_type, 
            self.VEHICLE_DIMENSIONS['car']
        )['height']
        
        # Distance estimation using pinhole camera model
        # distance = (real_height * focal_length) / bbox_height
        distance = (real_height * self.focal_length) / bbox_height
        
        # Clamp to reasonable range
        distance = np.clip(distance, 1.0, 200.0)
        
        return float(distance)
    
    def estimate_distance_ground(
        self, 
        bbox: list, 
        frame_height: int
    ) -> float:
        """
        Estimate distance using ground plane geometry.
        Alternative method based on bottom of bbox.
        
        Args:
            bbox: [x1, y1, x2, y2] bounding box
            frame_height: Frame height in pixels
            
        Returns:
            Estimated distance in meters
        """
        x1, y1, x2, y2 = bbox
        
        # Distance from bottom of frame
        distance_from_bottom = frame_height - y2
        
        if distance_from_bottom <= 0:
            return 1.0  # Very close
        
        # Perspective scaling (empirical)
        # Objects at bottom of frame are close, at horizon are far
        max_distance = 100.0
        distance = (distance_from_bottom / frame_height) * max_distance
        
        return float(distance)
    
    def smooth_distance(self, distance: float) -> float:
        """
        Apply temporal smoothing to distance estimate.
        
        Args:
            distance: Raw distance estimate
            
        Returns:
            Smoothed distance
        """
        self.distance_history.append(distance)
        
        if len(self.distance_history) > self.max_history:
            self.distance_history.pop(0)
        
        # Moving average
        smoothed = np.mean(self.distance_history)
        return float(smoothed)
    
    def classify_risk(self, distance: float) -> str:
        """
        Classify risk level based on distance.
        
        Args:
            distance: Distance in meters
            
        Returns:
            Risk level: "SAFE", "CAUTION", or "DANGER"
        """
        if distance > self.SAFE_DISTANCE:
            return "SAFE"
        elif distance > self.CAUTION_DISTANCE:
            return "CAUTION"
        else:
            return "DANGER"
    
    def compute_ttc(
        self, 
        distance: float, 
        relative_speed: float = None,
        own_speed: float = 20.0  # m/s (default 72 km/h)
    ) -> Optional[float]:
        """
        Compute Time-to-Collision (TTC).
        
        Args:
            distance: Distance to vehicle in meters
            relative_speed: Relative closing speed in m/s (optional)
            own_speed: Own vehicle speed in m/s
            
        Returns:
            TTC in seconds, or None if not applicable
        """
        # If relative speed not available, assume worst case
        if relative_speed is None:
            # Assume front vehicle is stationary
            relative_speed = own_speed
        
        if relative_speed <= 0:
            # Not approaching or moving away
            return None
        
        ttc = distance / relative_speed
        return float(ttc)
    
    def draw_distance_info(
        self, 
        frame: np.ndarray, 
        bbox: list, 
        distance: float,
        risk_level: str,
        ttc: Optional[float] = None
    ) -> np.ndarray:
        """
        Draw distance and risk information on frame.
        
        Args:
            frame: RGB frame
            bbox: [x1, y1, x2, y2] bounding box
            distance: Distance in meters
            risk_level: "SAFE", "CAUTION", or "DANGER"
            ttc: Time-to-collision in seconds (optional)
            
        Returns:
            Annotated frame
        """
        annotated = frame.copy()
        x1, y1, x2, y2 = bbox
        
        # Color based on risk
        color_map = {
            "SAFE": (0, 255, 0),      # Green
            "CAUTION": (0, 165, 255),  # Orange
            "DANGER": (0, 0, 255)      # Red
        }
        color = color_map.get(risk_level, (255, 255, 255))
        
        # Draw distance text above bbox
        distance_text = f"{distance:.1f}m - {risk_level}"
        
        cv2.putText(
            annotated,
            distance_text,
            (x1, y1 - 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2
        )
        
        # Draw TTC if available
        if ttc is not None and ttc < 5.0:
            ttc_text = f"TTC: {ttc:.1f}s"
            cv2.putText(
                annotated,
                ttc_text,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )
        
        return annotated
    
    def process_detection(
        self, 
        detection: Dict, 
        frame_height: int,
        own_speed: float = 20.0
    ) -> Dict:
        """
        Process single vehicle detection for distance estimation.
        
        Args:
            detection: Detection dict from object detector
            frame_height: Frame height in pixels
            own_speed: Own vehicle speed in m/s
            
        Returns:
            Dict containing:
                - distance: Estimated distance in meters
                - distance_smoothed: Smoothed distance
                - risk_level: "SAFE", "CAUTION", or "DANGER"
                - ttc: Time-to-collision in seconds (if applicable)
        """
        bbox = detection['bbox']
        vehicle_type = detection['class_name']
        
        # Estimate distance using bbox method
        distance_bbox = self.estimate_distance_bbox(bbox, vehicle_type, frame_height)
        
        # Estimate distance using ground method
        distance_ground = self.estimate_distance_ground(bbox, frame_height)
        
        # Weighted average (bbox method is more reliable)
        distance = 0.7 * distance_bbox + 0.3 * distance_ground
        
        # Smooth distance
        distance_smoothed = self.smooth_distance(distance)
        
        # Classify risk
        risk_level = self.classify_risk(distance_smoothed)
        
        # Compute TTC
        ttc = self.compute_ttc(distance_smoothed, own_speed=own_speed)
        
        return {
            "distance": float(distance),
            "distance_smoothed": float(distance_smoothed),
            "risk_level": risk_level,
            "ttc": ttc
        }


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    estimator = DistanceEstimator()
    print("Distance Estimator initialized successfully")
    
    # Test with dummy detection
    test_detection = {
        'bbox': [200, 100, 400, 300],
        'class_name': 'car'
    }
    
    result = estimator.process_detection(test_detection, frame_height=720)
    print(f"Test result: {result}")
