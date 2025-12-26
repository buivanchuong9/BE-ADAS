"""
DISTANCE ESTIMATION MODULE - Production Grade
==============================================
Estimates distance, velocity, and time-to-collision (TTC) for front vehicles.

PRODUCTION FEATURES:
- Monocular distance estimation with camera calibration
- Relative velocity computation from tracking data
- Time-to-collision (TTC) calculation
- Risk classification (SAFE, CAUTION, DANGER, CRITICAL)
- Temporal smoothing to reduce noise

Method:
- Uses bounding box height and perspective geometry
- Calibrated for Vietnamese dashcam setup
- Integrates with object tracking for velocity

Author: Senior ADAS Engineer
Date: 2025-12-26 (Production Enhancement)
"""

import cv2
import numpy as np
from typing import Dict, Optional, Tuple, List
from collections import deque
import logging

logger = logging.getLogger(__name__)


class DistanceEstimator:
    """
    Production-grade distance and TTC estimator for ADAS.
    Designed for Vietnamese traffic conditions.
    """
    
    # Standard vehicle dimensions (meters) - Vietnamese vehicles
    VEHICLE_DIMENSIONS = {
        'car': {'height': 1.5, 'width': 1.8, 'length': 4.5},
        'truck': {'height': 2.5, 'width': 2.4, 'length': 6.0},
        'bus': {'height': 3.0, 'width': 2.5, 'length': 10.0},
        'motorcycle': {'height': 1.2, 'width': 0.8, 'length': 2.0},
        'bicycle': {'height': 1.6, 'width': 0.6, 'length': 1.8},
        'person': {'height': 1.7, 'width': 0.5, 'length': 0.5}
    }
    
    # Risk thresholds (meters)
    SAFE_DISTANCE = 30.0
    CAUTION_DISTANCE = 15.0
    DANGER_DISTANCE = 7.0
    CRITICAL_DISTANCE = 3.0
    
    # TTC thresholds (seconds)
    SAFE_TTC = 5.0
    CAUTION_TTC = 3.0
    DANGER_TTC = 1.5
    CRITICAL_TTC = 0.5
    
    def __init__(
        self, 
        focal_length: float = 700.0, 
        camera_height: float = 1.2,
        frame_rate: float = 30.0,
        pixel_to_meter: float = 0.02
    ):
        """
        Initialize distance estimator with camera calibration.
        
        Args:
            focal_length: Camera focal length in pixels (calibrated)
            camera_height: Camera mounting height in meters
            frame_rate: Video frame rate for velocity calculation
            pixel_to_meter: Pixel to meter conversion at reference distance
        """
        self.focal_length = focal_length
        self.camera_height = camera_height
        self.frame_rate = frame_rate
        self.pixel_to_meter = pixel_to_meter
        
        # Track history for velocity estimation
        self.track_history = {}  # track_id -> deque of (distance, timestamp)
        self.max_history = 10
        
        logger.info(
            f"DistanceEstimator initialized "
            f"(f={focal_length}px, h={camera_height}m, fps={frame_rate})"
        )
    
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
    
    def estimate_velocity(
        self,
        track_id: int,
        distance: float,
        frame_number: int
    ) -> Tuple[float, float]:
        """
        Estimate relative velocity from distance history.
        
        Args:
            track_id: Persistent track ID
            distance: Current distance in meters
            frame_number: Current frame number
            
        Returns:
            Tuple of (relative_velocity_mps, acceleration_mps2)
            Positive = moving away, Negative = approaching
        """
        # Initialize history for new track
        if track_id not in self.track_history:
            self.track_history[track_id] = deque(maxlen=self.max_history)
        
        # Add current measurement
        self.track_history[track_id].append((distance, frame_number))
        
        history = self.track_history[track_id]
        
        if len(history) < 2:
            return 0.0, 0.0
        
        # Calculate velocity from last two measurements
        dist_curr, frame_curr = history[-1]
        dist_prev, frame_prev = history[-2]
        
        # Time delta in seconds
        dt = (frame_curr - frame_prev) / self.frame_rate
        
        if dt == 0:
            return 0.0, 0.0
        
        # Velocity in m/s (positive = moving away, negative = approaching)
        velocity = (dist_curr - dist_prev) / dt
        
        # Calculate acceleration if we have enough history
        acceleration = 0.0
        if len(history) >= 3:
            dist_prev2, frame_prev2 = history[-3]
            dt2 = (frame_prev - frame_prev2) / self.frame_rate
            
            if dt2 > 0:
                velocity_prev = (dist_prev - dist_prev2) / dt2
                acceleration = (velocity - velocity_prev) / dt
        
        return velocity, acceleration
    
    def compute_ttc(
        self, 
        distance: float, 
        relative_velocity: float,
        min_ttc: float = 0.1,
        max_ttc: float = 10.0
    ) -> Optional[float]:
        """
        Compute Time-To-Collision (TTC) in seconds.
        
        Args:
            distance: Distance to object in meters
            relative_velocity: Relative velocity in m/s (negative = approaching)
            min_ttc: Minimum TTC to return (avoid division by zero)
            max_ttc: Maximum TTC to return (cap for distant objects)
            
        Returns:
            TTC in seconds, or None if not approaching
        """
        # Only calculate TTC if approaching (negative velocity)
        if relative_velocity >= 0:
            return None  # Not approaching
        
        # TTC = distance / |closing_speed|
        ttc = distance / abs(relative_velocity)
        
        # Clamp to reasonable range
        ttc = np.clip(ttc, min_ttc, max_ttc)
        
        return float(ttc)
    
    def classify_risk(self, distance: float, ttc: Optional[float] = None) -> str:
        """
        Classify risk level based on distance and TTC.
        PRODUCTION: Use both metrics for safer assessment.
        
        Args:
            distance: Distance in meters
            ttc: Time-to-collision in seconds (if approaching)
            
        Returns:
            Risk level: "SAFE", "CAUTION", "DANGER", "CRITICAL"
        """
        # Check TTC first (more urgent)
        if ttc is not None:
            if ttc < self.CRITICAL_TTC:
                return "CRITICAL"
            elif ttc < self.DANGER_TTC:
                return "DANGER"
            elif ttc < self.CAUTION_TTC:
                return "CAUTION"
        
        # Check distance
        if distance < self.CRITICAL_DISTANCE:
            return "CRITICAL"
        elif distance < self.DANGER_DISTANCE:
            return "DANGER"
        elif distance < self.CAUTION_DISTANCE:
            return "CAUTION"
        else:
            return "SAFE"
    
    def process_tracked_object(
        self,
        tracked_obj: Dict,
        frame_height: int,
        frame_number: int
    ) -> Dict:
        """
        Process tracked object to estimate distance, velocity, and TTC.
        PRODUCTION METHOD: Complete analysis pipeline.
        
        Args:
            tracked_obj: Tracked object dict with 'id', 'bbox', 'class_name'
            frame_height: Frame height in pixels
            frame_number: Current frame number
            
        Returns:
            Enhanced dict with distance, velocity, TTC, risk metrics
        """
        bbox = tracked_obj['bbox']
        vehicle_type = tracked_obj.get('class_name', 'car')
        track_id = tracked_obj.get('id', -1)
        
        # Estimate distance
        distance = self.estimate_distance_bbox(bbox, vehicle_type, frame_height)
        
        # Estimate velocity and acceleration
        velocity, acceleration = self.estimate_velocity(track_id, distance, frame_number)
        
        # Compute TTC
        ttc = self.compute_ttc(distance, velocity)
        
        # Classify risk
        risk_level = self.classify_risk(distance, ttc)
        
        # Add metrics to object
        tracked_obj.update({
            'distance': float(distance),
            'relative_velocity': float(velocity),
            'acceleration': float(acceleration),
            'ttc': float(ttc) if ttc is not None else None,
            'risk_level': risk_level,
            'is_approaching': velocity < 0,
            'closing_speed': abs(velocity) if velocity < 0 else 0.0
        })
        
        return tracked_obj
    
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
