"""
OBJECT TRACKING MODULE - ByteTrack Integration
===============================================
Multi-object tracking for ADAS using ByteTrack algorithm.
Maintains persistent IDs across frames for vehicles and pedestrians.

Features:
- Persistent object IDs across frames
- Track lifecycle management (birth, active, lost, dead)
- Velocity and acceleration estimation
- Designed for Vietnamese traffic (motorcycles, mixed traffic)

Author: Senior ADAS Engineer
Date: 2025-12-26 (Production)
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)


class KalmanBoxTracker:
    """
    Kalman Filter for tracking bounding boxes in image space.
    State: [x_center, y_center, area, aspect_ratio, vx, vy, va, vr]
    """
    
    count = 0  # Global track ID counter
    
    def __init__(self, bbox: np.ndarray, class_id: int, confidence: float):
        """
        Initialize Kalman filter tracker.
        
        Args:
            bbox: [x1, y1, x2, y2] bounding box
            class_id: Object class ID
            confidence: Detection confidence
        """
        from filterpy.kalman import KalmanFilter
        
        # State: [cx, cy, area, ratio, vx, vy, va, vr]
        self.kf = KalmanFilter(dim_x=8, dim_z=4)
        
        # State transition matrix
        self.kf.F = np.array([
            [1, 0, 0, 0, 1, 0, 0, 0],
            [0, 1, 0, 0, 0, 1, 0, 0],
            [0, 0, 1, 0, 0, 0, 1, 0],
            [0, 0, 0, 1, 0, 0, 0, 1],
            [0, 0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 0, 1]
        ])
        
        # Measurement matrix
        self.kf.H = np.array([
            [1, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0, 0]
        ])
        
        # Measurement noise
        self.kf.R *= 1.0
        
        # Process noise
        self.kf.Q[-1, -1] *= 0.01
        self.kf.Q[4:, 4:] *= 0.01
        
        # Initial state
        self.kf.x[:4] = self._convert_bbox_to_z(bbox)
        
        # Track metadata
        self.id = KalmanBoxTracker.count
        KalmanBoxTracker.count += 1
        
        self.class_id = class_id
        self.confidence = confidence
        self.time_since_update = 0
        self.hits = 1
        self.hit_streak = 1
        self.age = 0
        
        # Velocity history
        self.velocity_history = deque(maxlen=10)
        
    @staticmethod
    def _convert_bbox_to_z(bbox: np.ndarray) -> np.ndarray:
        """
        Convert [x1, y1, x2, y2] to [cx, cy, area, ratio].
        Returns shape (4, 1) for Kalman filter compatibility.
        """
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        cx = bbox[0] + w / 2.0
        cy = bbox[1] + h / 2.0
        area = w * h
        ratio = w / float(h) if h > 0 else 1.0
        return np.array([[cx], [cy], [area], [ratio]])
    
    @staticmethod
    def _convert_z_to_bbox(z: np.ndarray) -> np.ndarray:
        """
        Convert [cx, cy, area, ratio] to [x1, y1, x2, y2].
        """
        w = np.sqrt(z[2] * z[3])
        h = z[2] / w if w > 0 else 1.0
        x1 = z[0] - w / 2.0
        y1 = z[1] - h / 2.0
        x2 = z[0] + w / 2.0
        y2 = z[1] + h / 2.0
        return np.array([x1, y1, x2, y2])
    
    def update(self, bbox: np.ndarray, confidence: float):
        """
        Update tracker with new detection.
        
        Args:
            bbox: [x1, y1, x2, y2] bounding box
            confidence: Detection confidence
        """
        self.time_since_update = 0
        self.hits += 1
        self.hit_streak += 1
        self.confidence = confidence
        
        # Update Kalman filter
        z = self._convert_bbox_to_z(bbox)
        self.kf.update(z)
        
        # Update velocity
        if len(self.velocity_history) > 0:
            prev_state = self.velocity_history[-1]
            dx = self.kf.x[0] - prev_state[0]
            dy = self.kf.x[1] - prev_state[1]
            self.velocity_history.append([self.kf.x[0], self.kf.x[1], dx, dy])
        else:
            self.velocity_history.append([self.kf.x[0], self.kf.x[1], 0, 0])
    
    def predict(self) -> np.ndarray:
        """
        Predict next state and return predicted bounding box.
        
        Returns:
            Predicted [x1, y1, x2, y2] bounding box
        """
        # Predict
        self.kf.predict()
        
        self.age += 1
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        
        # Return predicted bbox
        return self._convert_z_to_bbox(self.kf.x[:4])
    
    def get_state(self) -> Dict:
        """
        Get current track state.
        
        Returns:
            Dict with bbox, velocity, metadata
        """
        bbox = self._convert_z_to_bbox(self.kf.x[:4])
        
        # Calculate velocity in pixels/frame
        vx = self.kf.x[4]
        vy = self.kf.x[5]
        speed = np.sqrt(vx**2 + vy**2)
        
        return {
            'id': self.id,
            'bbox': bbox,
            'class_id': self.class_id,
            'confidence': self.confidence,
            'velocity': [vx, vy],
            'speed': speed,
            'hits': self.hits,
            'age': self.age,
            'time_since_update': self.time_since_update
        }


class ByteTracker:
    """
    ByteTrack implementation for multi-object tracking.
    Robust tracking for Vietnamese traffic conditions.
    """
    
    def __init__(
        self,
        track_thresh: float = 0.5,
        match_thresh: float = 0.8,
        track_buffer: int = 30,
        frame_rate: int = 30
    ):
        """
        Initialize ByteTracker.
        
        Args:
            track_thresh: Detection confidence threshold for track initialization
            match_thresh: IoU threshold for matching
            track_buffer: Number of frames to keep lost tracks
            frame_rate: Video frame rate
        """
        self.track_thresh = track_thresh
        self.match_thresh = match_thresh
        self.track_buffer = track_buffer
        self.frame_rate = frame_rate
        
        self.tracked_tracks = []  # Active tracks
        self.lost_tracks = []     # Recently lost tracks
        self.removed_tracks = []  # Dead tracks
        
        self.frame_id = 0
        
        logger.info(f"ByteTracker initialized with thresh={track_thresh}, match={match_thresh}")
    
    @staticmethod
    def _iou(bbox1: np.ndarray, bbox2: np.ndarray) -> float:
        """
        Calculate IoU between two bounding boxes.
        
        Args:
            bbox1: [x1, y1, x2, y2]
            bbox2: [x1, y1, x2, y2]
            
        Returns:
            IoU score [0-1]
        """
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])
        
        inter_area = max(0, x2 - x1) * max(0, y2 - y1)
        
        bbox1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        bbox2_area = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        
        union_area = bbox1_area + bbox2_area - inter_area
        
        if union_area == 0:
            return 0.0
        
        return inter_area / union_area
    
    def update(self, detections: List[Dict]) -> List[Dict]:
        """
        Update tracker with new detections.
        
        Args:
            detections: List of detection dicts with 'bbox', 'class_id', 'confidence'
            
        Returns:
            List of tracked objects with persistent IDs
        """
        self.frame_id += 1
        
        # Separate high and low confidence detections
        # Support both 'confidence' and 'score' keys
        high_conf_dets = [d for d in detections if d.get('confidence', d.get('score', 0)) >= self.track_thresh]
        low_conf_dets = [d for d in detections if d.get('confidence', d.get('score', 0)) < self.track_thresh]
        
        # Predict all tracks
        for track in self.tracked_tracks:
            track.predict()
        
        # Match high confidence detections to tracked tracks
        matched, unmatched_tracks, unmatched_dets = self._match(
            self.tracked_tracks,
            high_conf_dets
        )
        
        # Update matched tracks
        for track_idx, det_idx in matched:
            track = self.tracked_tracks[track_idx]
            det = high_conf_dets[det_idx]
            confidence = det.get('confidence', det.get('score', 0.5))
            track.update(det['bbox'], confidence)
        
        # Initialize new tracks from unmatched high confidence detections
        for det_idx in unmatched_dets:
            det = high_conf_dets[det_idx]
            confidence = det.get('confidence', det.get('score', 0.5))
            new_track = KalmanBoxTracker(det['bbox'], det['class_id'], confidence)
            self.tracked_tracks.append(new_track)
        
        # Move unmatched tracks to lost
        for track_idx in unmatched_tracks:
            track = self.tracked_tracks[track_idx]
            self.lost_tracks.append(track)
        
        self.tracked_tracks = [t for i, t in enumerate(self.tracked_tracks) 
                              if i not in unmatched_tracks]
        
        # Try to recover lost tracks with low confidence detections
        if len(low_conf_dets) > 0 and len(self.lost_tracks) > 0:
            matched_lost, unmatched_lost, _ = self._match(
                self.lost_tracks,
                low_conf_dets
            )
            
            # Recover matched lost tracks
            for track_idx, det_idx in matched_lost:
                track = self.lost_tracks[track_idx]
                det = low_conf_dets[det_idx]
                track.update(det['bbox'], det['confidence'])
                self.tracked_tracks.append(track)
            
            self.lost_tracks = [t for i, t in enumerate(self.lost_tracks)
                               if i not in [m[0] for m in matched_lost]]
        
        # Remove old lost tracks
        self.lost_tracks = [t for t in self.lost_tracks 
                           if t.time_since_update <= self.track_buffer]
        
        # Get output tracks
        output_tracks = []
        for track in self.tracked_tracks:
            if track.hit_streak >= 3 or self.frame_id <= 3:
                state = track.get_state()
                output_tracks.append(state)
        
        return output_tracks
    
    def _match(
        self,
        tracks: List[KalmanBoxTracker],
        detections: List[Dict]
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        Match tracks to detections using IoU.
        
        Args:
            tracks: List of tracks
            detections: List of detections
            
        Returns:
            Tuple of (matched_pairs, unmatched_track_indices, unmatched_det_indices)
        """
        if len(tracks) == 0:
            return [], [], list(range(len(detections)))
        
        if len(detections) == 0:
            return [], list(range(len(tracks))), []
        
        # Calculate IoU matrix
        iou_matrix = np.zeros((len(tracks), len(detections)))
        
        for t_idx, track in enumerate(tracks):
            track_bbox = track.get_state()['bbox']
            for d_idx, det in enumerate(detections):
                iou_matrix[t_idx, d_idx] = self._iou(track_bbox, det['bbox'])
        
        # Hungarian matching
        from scipy.optimize import linear_sum_assignment
        
        track_indices, det_indices = linear_sum_assignment(-iou_matrix)
        
        # Filter matches by IoU threshold
        matched = []
        unmatched_tracks = list(range(len(tracks)))
        unmatched_dets = list(range(len(detections)))
        
        for t_idx, d_idx in zip(track_indices, det_indices):
            if iou_matrix[t_idx, d_idx] >= self.match_thresh:
                matched.append((t_idx, d_idx))
                unmatched_tracks.remove(t_idx)
                unmatched_dets.remove(d_idx)
        
        return matched, unmatched_tracks, unmatched_dets
    
    def reset(self):
        """Reset tracker state."""
        self.tracked_tracks = []
        self.lost_tracks = []
        self.removed_tracks = []
        self.frame_id = 0
        KalmanBoxTracker.count = 0
