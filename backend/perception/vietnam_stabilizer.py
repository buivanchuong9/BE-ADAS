"""
Vietnam ADAS Stabilizer - v3.0
==============================
Temporal smoothing for stable, human-friendly alerts on Vietnam roads.

Features:
- EMA smoothing for lane detection
- Voting-based collision warnings
- Kalman filter for distance estimation
- No flickering/jumping alerts
"""

import logging
from collections import deque
from typing import Optional, Tuple, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)


class KalmanFilter1D:
    """Simple 1D Kalman filter for distance smoothing."""
    
    def __init__(self, process_variance: float = 0.1, measurement_variance: float = 10.0):
        self.process_variance = process_variance
        self.measurement_variance = measurement_variance
        self.estimate = 0.0
        self.error_covariance = 1.0
    
    def update(self, measurement: float) -> float:
        # Prediction
        self.error_covariance += self.process_variance
        
        # Update
        kalman_gain = self.error_covariance / (self.error_covariance + self.measurement_variance)
        self.estimate += kalman_gain * (measurement - self.estimate)
        self.error_covariance *= (1 - kalman_gain)
        
        return self.estimate
    
    def reset(self, value: float = 0.0):
        self.estimate = value
        self.error_covariance = 1.0


class VietnamADASStabilizer:
    """
    Stabilize ADAS alerts for Vietnam road conditions.
    
    Key improvements:
    - Handles faded/broken lane markings
    - Prioritizes motorbike detection
    - Reduces false positives in dense traffic
    - Smooth, human-readable alerts
    """
    
    # Vietnam-specific thresholds
    CONFIG = {
        'lane_detection': {
            'ema_alpha': 0.3,           # Lower = more stable
            'min_confidence': 0.4,      # Accept lower confidence for faded lanes
            'history_frames': 15,       # 0.5s at 30fps
            'departure_threshold': 0.6, # 60% of history must agree
        },
        'collision_warning': {
            'vote_window': 10,          # 10 frames for voting
            'danger_threshold': 6,      # 6/10 must agree for DANGER
            'warning_threshold': 3,     # 3/10 for WARNING
            'ttc_danger': 1.5,          # Time-to-collision thresholds
            'ttc_warning': 3.0,
        },
        'object_detection': {
            'min_confidence': {
                'motorcycle': 0.3,      # Lower for bikes (priority)
                'person': 0.4,
                'car': 0.5,
                'truck': 0.5,
            },
            'priority_classes': ['motorcycle', 'person', 'car'],
        },
        'distance': {
            'process_variance': 0.1,
            'measurement_variance': 10.0,
        }
    }
    
    def __init__(self):
        # Lane departure stabilization
        self.lane_history = deque(maxlen=self.CONFIG['lane_detection']['history_frames'])
        self.lane_ema = 0.0
        
        # Collision warning voting
        self.collision_votes = deque(maxlen=self.CONFIG['collision_warning']['vote_window'])
        
        # Distance estimation per tracked object
        self.distance_filters: Dict[int, KalmanFilter1D] = {}
        
        # State tracking
        self.last_lane_alert = False
        self.last_collision_level = 'SAFE'
        self.alert_cooldown = 0
    
    def stabilize_lane_departure(
        self,
        is_departure: bool,
        confidence: float,
        lane_position: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Stabilize lane departure detection.
        
        Args:
            is_departure: Raw detection result
            confidence: Detection confidence (0-1)
            lane_position: Vehicle position relative to lane center (-1 to 1)
            
        Returns:
            Tuple of (should_alert, reason)
        """
        config = self.CONFIG['lane_detection']
        
        # Filter low confidence detections
        if confidence < config['min_confidence']:
            is_departure = False
        
        # Add to history with confidence weighting
        self.lane_history.append((is_departure, confidence))
        
        # EMA update
        alpha = config['ema_alpha']
        self.lane_ema = alpha * (1.0 if is_departure else 0.0) + (1 - alpha) * self.lane_ema
        
        # Weighted voting
        weighted_sum = sum(d * c for d, c in self.lane_history)
        threshold = len(self.lane_history) * config['departure_threshold']
        
        should_alert = weighted_sum > threshold and self.lane_ema > 0.5
        
        # Cooldown to prevent rapid toggle
        if self.alert_cooldown > 0:
            self.alert_cooldown -= 1
            should_alert = self.last_lane_alert
        elif should_alert != self.last_lane_alert:
            self.alert_cooldown = 5  # 5 frame cooldown
        
        self.last_lane_alert = should_alert
        
        reason = ""
        if should_alert:
            if lane_position is not None:
                if lane_position < -0.3:
                    reason = "Xe đang lệch sang trái"
                elif lane_position > 0.3:
                    reason = "Xe đang lệch sang phải"
                else:
                    reason = "Cảnh báo lệch làn đường"
            else:
                reason = "Cảnh báo lệch làn đường"
        
        return should_alert, reason
    
    def stabilize_collision_warning(
        self,
        ttc: float,
        distance: float,
        object_class: str = "car"
    ) -> Tuple[str, str]:
        """
        Stabilize forward collision warning.
        
        Args:
            ttc: Time-to-collision in seconds
            distance: Distance to object in meters
            object_class: Type of object
            
        Returns:
            Tuple of (risk_level, message)
        """
        config = self.CONFIG['collision_warning']
        
        # Determine raw risk
        is_danger = ttc < config['ttc_danger'] and ttc > 0
        is_warning = ttc < config['ttc_warning'] and ttc > 0
        
        # Add vote
        self.collision_votes.append(2 if is_danger else (1 if is_warning else 0))
        
        # Count votes
        danger_votes = sum(1 for v in self.collision_votes if v == 2)
        warning_votes = sum(1 for v in self.collision_votes if v >= 1)
        
        # Determine level
        if danger_votes >= config['danger_threshold']:
            level = 'CRITICAL'
        elif warning_votes >= config['warning_threshold']:
            level = 'WARNING'
        else:
            level = 'SAFE'
        
        # Message generation
        message = ""
        if level == 'CRITICAL':
            message = f"⚠️ VA CHẠM! {object_class.upper()} cách {distance:.1f}m"
        elif level == 'WARNING':
            message = f"Chú ý: {object_class} phía trước ({distance:.1f}m)"
        
        self.last_collision_level = level
        return level, message
    
    def smooth_distance(self, track_id: int, raw_distance: float) -> float:
        """
        Apply Kalman filter to smooth distance estimation.
        
        Args:
            track_id: Object tracking ID
            raw_distance: Raw distance measurement
            
        Returns:
            Smoothed distance
        """
        if track_id not in self.distance_filters:
            self.distance_filters[track_id] = KalmanFilter1D(
                process_variance=self.CONFIG['distance']['process_variance'],
                measurement_variance=self.CONFIG['distance']['measurement_variance']
            )
            self.distance_filters[track_id].reset(raw_distance)
        
        return self.distance_filters[track_id].update(raw_distance)
    
    def filter_detections(
        self,
        detections: list
    ) -> list:
        """
        Filter detections based on Vietnam-specific thresholds.
        
        Args:
            detections: List of detection dicts with 'class', 'confidence', etc.
            
        Returns:
            Filtered detections
        """
        config = self.CONFIG['object_detection']
        filtered = []
        
        for det in detections:
            obj_class = det.get('class', 'unknown')
            confidence = det.get('confidence', 0)
            
            min_conf = config['min_confidence'].get(obj_class, 0.5)
            
            if confidence >= min_conf:
                # Add priority flag
                det['is_priority'] = obj_class in config['priority_classes']
                filtered.append(det)
        
        # Sort by priority
        filtered.sort(key=lambda x: (not x.get('is_priority', False), -x.get('confidence', 0)))
        
        return filtered
    
    def cleanup_old_tracks(self, active_track_ids: set):
        """Remove Kalman filters for objects no longer tracked."""
        to_remove = [tid for tid in self.distance_filters if tid not in active_track_ids]
        for tid in to_remove:
            del self.distance_filters[tid]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get current stabilizer state summary."""
        return {
            'lane_ema': self.lane_ema,
            'lane_alert_active': self.last_lane_alert,
            'collision_level': self.last_collision_level,
            'tracked_objects': len(self.distance_filters),
            'collision_votes': list(self.collision_votes),
        }


# Singleton instance
_stabilizer: Optional[VietnamADASStabilizer] = None


def get_stabilizer() -> VietnamADASStabilizer:
    """Get global stabilizer instance."""
    global _stabilizer
    if _stabilizer is None:
        _stabilizer = VietnamADASStabilizer()
    return _stabilizer
