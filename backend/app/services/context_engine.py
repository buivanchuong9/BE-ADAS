"""
CONTEXT ENGINE SERVICE
=======================
Phase 4: Temporal context aggregation for ADAS system.

PURPOSE:
Aggregates perception outputs into temporal context state for intelligent decision-making.
Maintains rolling buffers of perception data to understand sustained patterns vs. transient noise.

RESPONSIBILITIES:
1. Rolling buffer management (3-5 second windows)
2. Temporal metric aggregation (lane stability, traffic density, driver alertness)
3. State persistence to SQL Server
4. Context-aware feature extraction

PRODUCTION FEATURES:
- Frame-level perception → Context-level understanding
- Temporal consistency scoring
- Multi-factor context states
- Database persistence for audit/replay

DESIGN PHILOSOPHY:
This is the "working memory" of the ADAS system. While perception modules provide
frame-by-frame observations, the Context Engine maintains temporal context to distinguish
between:
- Momentary vs. sustained lane departure
- Single vehicle vs. dense traffic
- Transient vs. chronic driver distraction

Author: Senior ADAS Engineer
Date: 2025-12-26 (Phase 4)
"""

import numpy as np
from typing import Dict, List, Optional, Any
from collections import deque
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ContextEngine:
    """
    Temporal context aggregation engine.
    Maintains rolling buffers and computes aggregate metrics.
    """
    
    def __init__(
        self,
        window_seconds: float = 3.0,
        frame_rate: int = 30,
        enable_persistence: bool = True
    ):
        """
        Initialize context engine.
        
        Args:
            window_seconds: Rolling window duration (3-5 seconds recommended)
            frame_rate: Video frame rate (fps)
            enable_persistence: Enable database persistence
        """
        self.window_size = int(window_seconds * frame_rate)
        self.frame_rate = frame_rate
        self.enable_persistence = enable_persistence
        
        # Rolling buffers for perception outputs
        self.lane_buffers = {
            'left_confidence': deque(maxlen=self.window_size),
            'right_confidence': deque(maxlen=self.window_size),
            'offset': deque(maxlen=self.window_size),
            'departure_flags': deque(maxlen=self.window_size)
        }
        
        self.object_buffers = {
            'tracked_count': deque(maxlen=self.window_size),
            'vehicle_count': deque(maxlen=self.window_size),
            'pedestrian_count': deque(maxlen=self.window_size),
            'min_distance': deque(maxlen=self.window_size),
            'min_ttc': deque(maxlen=self.window_size),
            'critical_risk_count': deque(maxlen=self.window_size)
        }
        
        self.driver_buffers = {
            'ear': deque(maxlen=self.window_size),
            'mar': deque(maxlen=self.window_size),
            'drowsy_flags': deque(maxlen=self.window_size),
            'distraction_flags': deque(maxlen=self.window_size)
        }
        
        # Frame counter
        self.frame_number = 0
        
        # Current aggregate state
        self.current_state = {}
        
        logger.info(f"ContextEngine initialized: window={window_seconds}s, fps={frame_rate}")
    
    def update_lane_context(self, lane_output: Dict[str, Any]) -> None:
        """
        Update lane detection context.
        
        Args:
            lane_output: Output from lane_detector_v11.py process_frame()
        """
        self.lane_buffers['left_confidence'].append(lane_output.get('left_confidence', 0.0))
        self.lane_buffers['right_confidence'].append(lane_output.get('right_confidence', 0.0))
        self.lane_buffers['offset'].append(lane_output.get('offset', 0.0))
        self.lane_buffers['departure_flags'].append(lane_output.get('lane_departure', False))
    
    def update_object_context(self, tracked_objects: List[Dict[str, Any]]) -> None:
        """
        Update object tracking context.
        
        Args:
            tracked_objects: List of tracked objects from distance_estimator process_tracked_object()
        """
        # Count objects by type
        vehicle_classes = {'car', 'truck', 'bus', 'motorcycle'}
        pedestrian_classes = {'person', 'bicycle'}
        
        vehicle_count = sum(1 for obj in tracked_objects if obj.get('class_name') in vehicle_classes)
        pedestrian_count = sum(1 for obj in tracked_objects if obj.get('class_name') in pedestrian_classes)
        
        self.object_buffers['tracked_count'].append(len(tracked_objects))
        self.object_buffers['vehicle_count'].append(vehicle_count)
        self.object_buffers['pedestrian_count'].append(pedestrian_count)
        
        # Extract safety metrics
        distances = [obj.get('distance', float('inf')) for obj in tracked_objects if obj.get('distance')]
        ttcs = [obj.get('ttc') for obj in tracked_objects if obj.get('ttc') is not None]
        critical_risks = [1 for obj in tracked_objects if obj.get('risk_level') == 'CRITICAL']
        
        self.object_buffers['min_distance'].append(min(distances) if distances else float('inf'))
        self.object_buffers['min_ttc'].append(min(ttcs) if ttcs else float('inf'))
        self.object_buffers['critical_risk_count'].append(sum(critical_risks))
    
    def update_driver_context(self, driver_output: Dict[str, Any]) -> None:
        """
        Update driver monitoring context.
        
        Args:
            driver_output: Output from driver_monitor_v11.py process_frame()
        """
        if not driver_output.get('face_detected', False):
            return
        
        self.driver_buffers['ear'].append(driver_output.get('smoothed_ear', 0.0))
        self.driver_buffers['mar'].append(driver_output.get('smoothed_mar', 0.0))
        self.driver_buffers['drowsy_flags'].append(driver_output.get('is_sustained_drowsy', False))
        
        # Check for distraction (head pose)
        head_pose = driver_output.get('head_pose', {})
        is_distracted = abs(head_pose.get('yaw', 0)) > 30
        self.driver_buffers['distraction_flags'].append(is_distracted)
    
    def compute_lane_stability_score(self) -> float:
        """
        Calculate lane detection stability score (0-1).
        
        Returns:
            Stability score: 1.0 = perfect stability, 0.0 = unstable
        """
        if len(self.lane_buffers['left_confidence']) < self.window_size // 2:
            return 0.0
        
        # Average confidence
        avg_left_conf = np.mean(list(self.lane_buffers['left_confidence']))
        avg_right_conf = np.mean(list(self.lane_buffers['right_confidence']))
        avg_confidence = (avg_left_conf + avg_right_conf) / 2.0
        
        # Offset consistency (lower variance = more stable)
        offset_variance = np.var(list(self.lane_buffers['offset']))
        offset_stability = max(0.0, 1.0 - offset_variance * 2.0)
        
        # Combine metrics
        stability = 0.6 * avg_confidence + 0.4 * offset_stability
        
        return float(np.clip(stability, 0.0, 1.0))
    
    def compute_traffic_density_score(self) -> float:
        """
        Calculate traffic density score (0-1).
        
        Returns:
            Density score: 0.0 = empty road, 1.0 = heavy traffic
        """
        if len(self.object_buffers['tracked_count']) < self.window_size // 2:
            return 0.0
        
        # Average vehicle count
        avg_count = np.mean(list(self.object_buffers['tracked_count']))
        
        # Normalize (assume 0-10 vehicles is typical range)
        density = avg_count / 10.0
        
        return float(np.clip(density, 0.0, 1.0))
    
    def compute_driver_alertness_score(self) -> float:
        """
        Calculate driver alertness score (0-1).
        
        Returns:
            Alertness score: 1.0 = fully alert, 0.0 = drowsy/distracted
        """
        if len(self.driver_buffers['ear']) < self.window_size // 2:
            return 1.0  # Assume alert if no data
        
        # Drowsiness penalty
        drowsy_rate = np.mean(list(self.driver_buffers['drowsy_flags']))
        distraction_rate = np.mean(list(self.driver_buffers['distraction_flags']))
        
        # EAR score (higher EAR = more alert)
        avg_ear = np.mean(list(self.driver_buffers['ear']))
        ear_score = min(avg_ear / 0.3, 1.0)  # Normalize around 0.3 baseline
        
        # Combine metrics
        alertness = ear_score * (1.0 - drowsy_rate * 0.5) * (1.0 - distraction_rate * 0.3)
        
        return float(np.clip(alertness, 0.0, 1.0))
    
    def compute_vehicle_dynamics(self) -> Dict[str, Any]:
        """
        Compute vehicle dynamics from perception data.
        
        Returns:
            Dict with dynamics metrics
        """
        if len(self.object_buffers['min_distance']) < 2:
            return {
                'estimated_speed': 0.0,
                'acceleration': 0.0,
                'is_accelerating': False,
                'is_braking': False
            }
        
        # Estimate ego vehicle speed from distance changes
        recent_distances = list(self.object_buffers['min_distance'])[-10:]
        
        # Simple speed estimation (this would ideally use IMU/GPS data)
        estimated_speed = 50.0  # km/h (placeholder - would use real sensor data)
        
        return {
            'estimated_speed': estimated_speed,
            'acceleration': 0.0,
            'is_accelerating': False,
            'is_braking': False
        }
    
    def get_context_state(self) -> Dict[str, Any]:
        """
        Get current aggregated context state.
        
        Returns:
            Dict containing all aggregate metrics
        """
        self.frame_number += 1
        
        # Compute aggregate metrics
        lane_stability = self.compute_lane_stability_score()
        traffic_density = self.compute_traffic_density_score()
        driver_alertness = self.compute_driver_alertness_score()
        vehicle_dynamics = self.compute_vehicle_dynamics()
        
        # Check for sustained lane departure
        departure_count = sum(self.lane_buffers['departure_flags'])
        sustained_departure = departure_count >= (self.window_size * 0.5)
        
        # Check for critical proximity
        min_distance = min(self.object_buffers['min_distance']) if self.object_buffers['min_distance'] else float('inf')
        min_ttc = min(self.object_buffers['min_ttc']) if self.object_buffers['min_ttc'] else float('inf')
        critical_proximity = min_distance < 5.0 or min_ttc < 1.0
        
        # Build context state
        self.current_state = {
            'timestamp': datetime.utcnow().isoformat(),
            'frame_number': self.frame_number,
            
            # Aggregate scores
            'lane_stability_score': lane_stability,
            'traffic_density_score': traffic_density,
            'driver_alertness_score': driver_alertness,
            
            # Sustained conditions
            'sustained_lane_departure': sustained_departure,
            'critical_proximity': critical_proximity,
            
            # Vehicle dynamics
            'vehicle_dynamics': vehicle_dynamics,
            
            # Safety metrics
            'min_distance': min_distance if min_distance != float('inf') else None,
            'min_ttc': min_ttc if min_ttc != float('inf') else None,
            
            # Traffic composition
            'avg_vehicle_count': np.mean(list(self.object_buffers['vehicle_count'])) if self.object_buffers['vehicle_count'] else 0,
            'avg_pedestrian_count': np.mean(list(self.object_buffers['pedestrian_count'])) if self.object_buffers['pedestrian_count'] else 0,
            
            # Driver state
            'is_drowsy': np.mean(list(self.driver_buffers['drowsy_flags'])) > 0.7 if self.driver_buffers['drowsy_flags'] else False,
            'is_distracted': np.mean(list(self.driver_buffers['distraction_flags'])) > 0.5 if self.driver_buffers['distraction_flags'] else False
        }
        
        return self.current_state
    
    def reset(self) -> None:
        """Reset all buffers and state."""
        for buffer_dict in [self.lane_buffers, self.object_buffers, self.driver_buffers]:
            for buffer in buffer_dict.values():
                buffer.clear()
        
        self.frame_number = 0
        self.current_state = {}
        logger.info("ContextEngine reset")
    
    async def persist_state(self, session) -> None:
        """
        Persist current context state to database (FUTURE IMPLEMENTATION).
        
        Args:
            session: AsyncSession for database operations
        """
        if not self.enable_persistence:
            return
        
        # TODO: Implement database persistence
        # Would create context_states table with columns:
        # - id, job_id, timestamp, frame_number
        # - lane_stability_score, traffic_density_score, driver_alertness_score
        # - sustained_lane_departure, critical_proximity
        # - json_metadata (full state)
        
        logger.debug(f"Context state at frame {self.frame_number} (persistence not yet implemented)")


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    
    engine = ContextEngine(window_seconds=3.0, frame_rate=30)
    print("Context Engine initialized successfully")
    
    # Simulate updates
    for i in range(100):
        # Simulate lane detection
        engine.update_lane_context({
            'left_confidence': 0.8 + np.random.normal(0, 0.05),
            'right_confidence': 0.85 + np.random.normal(0, 0.05),
            'offset': np.random.normal(0, 0.1),
            'lane_departure': False
        })
        
        # Simulate object tracking
        engine.update_object_context([
            {'class_name': 'car', 'distance': 20.0, 'ttc': 3.0, 'risk_level': 'CAUTION'}
        ])
        
        # Simulate driver monitoring
        engine.update_driver_context({
            'face_detected': True,
            'smoothed_ear': 0.28,
            'smoothed_mar': 0.4,
            'is_sustained_drowsy': False,
            'head_pose': {'yaw': 5.0, 'pitch': -10.0}
        })
    
    state = engine.get_context_state()
    print(f"\nContext State after 100 frames:")
    print(f"  Lane Stability: {state['lane_stability_score']:.2f}")
    print(f"  Traffic Density: {state['traffic_density_score']:.2f}")
    print(f"  Driver Alertness: {state['driver_alertness_score']:.2f}")
