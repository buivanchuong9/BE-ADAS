"""
Sensor Fusion Core - Extended Kalman Filter (EKF) implementation
Fuses data from multiple sensors: Camera, LiDAR, Radar, GPS, IMU

Purpose:
- Combine redundant sensor data for robust perception
- Filter noise and outliers
- Provide unified world model
- Handle sensor failures gracefully

Algorithm: Extended Kalman Filter (EKF)
- State estimation with nonlinear models
- Recursive Bayesian filtering
- Optimal fusion of heterogeneous sensors
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from .base import SensorData, SensorType, SensorStatus


@dataclass
class FusedState:
    """
    Unified state estimate from all sensors
    
    State vector components:
    - Position: (x, y, z) in meters
    - Velocity: (vx, vy, vz) in m/s
    - Orientation: (roll, pitch, yaw) in radians
    - Angular velocity: (wx, wy, wz) in rad/s
    """
    timestamp: datetime
    
    # Position and velocity
    position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    
    # Orientation (Euler angles)
    orientation: np.ndarray = field(default_factory=lambda: np.zeros(3))
    angular_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    
    # Covariance matrix (uncertainty)
    covariance: np.ndarray = field(default_factory=lambda: np.eye(12))
    
    # Sensor contributions (for debugging)
    contributors: List[str] = field(default_factory=list)
    confidence: float = 1.0


class ExtendedKalmanFilter:
    """
    Extended Kalman Filter for nonlinear state estimation
    
    State vector (12D):
    [x, y, z, vx, vy, vz, roll, pitch, yaw, wx, wy, wz]
    
    Process model: Constant velocity + angular velocity
    Measurement models: Sensor-specific observation functions
    """
    
    def __init__(self, dt: float = 0.033):  # 30 Hz default
        """
        Initialize EKF
        
        Args:
            dt: Time step in seconds (e.g., 0.033 for 30 Hz)
        """
        self.dt = dt
        
        # State vector (12D)
        self.x = np.zeros(12)
        
        # Covariance matrix (12x12)
        self.P = np.eye(12) * 10.0  # Initial uncertainty
        
        # Process noise covariance (tuning parameters)
        self.Q = self._init_process_noise()
        
        # Measurement noise covariance (sensor-specific)
        self.R_camera = np.eye(3) * 0.5  # Camera measurement noise
        self.R_lidar = np.eye(3) * 0.1   # LiDAR is more accurate
        self.R_radar = np.eye(3) * 0.3   # Radar moderate noise
        self.R_gps = np.eye(3) * 2.0     # GPS less accurate
        self.R_imu = np.eye(6) * 0.2     # IMU for orientation + angular vel
    
    def _init_process_noise(self) -> np.ndarray:
        """
        Initialize process noise covariance Q
        
        Models uncertainty in system dynamics:
        - Position uncertainty from velocity integration
        - Velocity uncertainty from acceleration noise
        - Orientation uncertainty from angular velocity integration
        
        Returns:
            12x12 process noise matrix
        """
        Q = np.eye(12)
        
        # Position noise (small, since we have velocity)
        Q[0:3, 0:3] *= 0.1
        
        # Velocity noise (moderate, from unknown acceleration)
        Q[3:6, 3:6] *= 0.5
        
        # Orientation noise (small)
        Q[6:9, 6:9] *= 0.05
        
        # Angular velocity noise (moderate)
        Q[9:12, 9:12] *= 0.3
        
        return Q
    
    def predict(self, dt: Optional[float] = None) -> None:
        """
        Prediction step: Propagate state forward using process model
        
        State transition model:
        x_{k+1} = F * x_k + w_k
        
        where F is the state transition matrix and w_k ~ N(0, Q)
        
        Args:
            dt: Time step (uses default if None)
        """
        if dt is None:
            dt = self.dt
        
        # State transition matrix F (12x12)
        F = self._compute_state_transition(dt)
        
        # Predict state
        self.x = F @ self.x
        
        # Predict covariance
        self.P = F @ self.P @ F.T + self.Q
    
    def update_camera(self, position_obs: np.ndarray) -> None:
        """
        Update step with camera observation (position only)
        
        Args:
            position_obs: Observed position [x, y, z] from camera
        """
        # Measurement matrix (observe position only)
        H = np.zeros((3, 12))
        H[0:3, 0:3] = np.eye(3)
        
        # Innovation (measurement residual)
        z = position_obs
        y = z - (H @ self.x)
        
        # Innovation covariance
        S = H @ self.P @ H.T + self.R_camera
        
        # Kalman gain
        K = self.P @ H.T @ np.linalg.inv(S)
        
        # Update state
        self.x = self.x + K @ y
        
        # Update covariance
        I = np.eye(12)
        self.P = (I - K @ H) @ self.P
    
    def update_lidar(self, position_obs: np.ndarray) -> None:
        """
        Update step with LiDAR observation (high-precision position)
        
        Args:
            position_obs: Observed position [x, y, z] from LiDAR
        """
        # Similar to camera but with lower noise
        H = np.zeros((3, 12))
        H[0:3, 0:3] = np.eye(3)
        
        z = position_obs
        y = z - (H @ self.x)
        S = H @ self.P @ H.T + self.R_lidar
        K = self.P @ H.T @ np.linalg.inv(S)
        
        self.x = self.x + K @ y
        I = np.eye(12)
        self.P = (I - K @ H) @ self.P
    
    def update_gps(self, position_obs: np.ndarray) -> None:
        """
        Update step with GPS observation (global position)
        
        Args:
            position_obs: GPS position [lat, lon, alt] converted to [x, y, z]
        """
        H = np.zeros((3, 12))
        H[0:3, 0:3] = np.eye(3)
        
        z = position_obs
        y = z - (H @ self.x)
        S = H @ self.P @ H.T + self.R_gps
        K = self.P @ H.T @ np.linalg.inv(S)
        
        self.x = self.x + K @ y
        I = np.eye(12)
        self.P = (I - K @ H) @ self.P
    
    def update_imu(self, orientation_obs: np.ndarray, angular_vel_obs: np.ndarray) -> None:
        """
        Update step with IMU observation (orientation + angular velocity)
        
        Args:
            orientation_obs: [roll, pitch, yaw] in radians
            angular_vel_obs: [wx, wy, wz] in rad/s
        """
        # Measurement matrix (observe orientation and angular velocity)
        H = np.zeros((6, 12))
        H[0:3, 6:9] = np.eye(3)    # Orientation
        H[3:6, 9:12] = np.eye(3)   # Angular velocity
        
        z = np.concatenate([orientation_obs, angular_vel_obs])
        y = z - (H @ self.x)
        S = H @ self.P @ H.T + self.R_imu
        K = self.P @ H.T @ np.linalg.inv(S)
        
        self.x = self.x + K @ y
        I = np.eye(12)
        self.P = (I - K @ H) @ self.P
    
    def get_state(self) -> FusedState:
        """
        Get current fused state estimate
        
        Returns:
            FusedState object with position, velocity, orientation
        """
        return FusedState(
            timestamp=datetime.now(),
            position=self.x[0:3].copy(),
            velocity=self.x[3:6].copy(),
            orientation=self.x[6:9].copy(),
            angular_velocity=self.x[9:12].copy(),
            covariance=self.P.copy(),
            confidence=self._compute_confidence()
        )
    
    def _compute_state_transition(self, dt: float) -> np.ndarray:
        """
        Compute state transition matrix F
        
        Constant velocity model:
        position_{k+1} = position_k + velocity_k * dt
        velocity_{k+1} = velocity_k
        orientation_{k+1} = orientation_k + angular_velocity_k * dt
        angular_velocity_{k+1} = angular_velocity_k
        
        Returns:
            12x12 state transition matrix
        """
        F = np.eye(12)
        
        # Position = position + velocity * dt
        F[0:3, 3:6] = np.eye(3) * dt
        
        # Orientation = orientation + angular_velocity * dt
        F[6:9, 9:12] = np.eye(3) * dt
        
        return F
    
    def _compute_confidence(self) -> float:
        """
        Compute overall confidence based on covariance trace
        
        Lower covariance = higher confidence
        
        Returns:
            Confidence score [0.0-1.0]
        """
        # Use trace of covariance as uncertainty metric
        trace = np.trace(self.P)
        
        # Map to confidence (inverse relationship)
        # Tuned so trace ~ 10 gives confidence ~ 0.9
        confidence = 1.0 / (1.0 + trace / 100.0)
        
        return float(np.clip(confidence, 0.0, 1.0))


class SensorFusionCore:
    """
    High-level sensor fusion manager
    
    Responsibilities:
    - Collect data from multiple sensors
    - Run Extended Kalman Filter
    - Detect and handle sensor failures
    - Provide fused state estimate
    
    Safety features:
    - Sensor redundancy (continues if 1-2 sensors fail)
    - Outlier rejection (Mahalanobis distance check)
    - Fail-safe degraded mode
    """
    
    def __init__(self, sensors: List[Any], update_rate_hz: float = 30.0):
        """
        Initialize sensor fusion
        
        Args:
            sensors: List of ISensor objects to fuse
            update_rate_hz: Fusion update rate (e.g., 30 Hz)
        """
        self.sensors = sensors
        self.update_rate = update_rate_hz
        self.dt = 1.0 / update_rate_hz
        
        # Extended Kalman Filter
        self.ekf = ExtendedKalmanFilter(dt=self.dt)
        
        # Last fused state
        self._last_state: Optional[FusedState] = None
        
        # Sensor health tracking
        self._sensor_health: Dict[str, bool] = {}
        
    async def fuse(self) -> Optional[FusedState]:
        """
        Perform one fusion cycle
        
        Steps:
        1. Predict state forward
        2. Read from all sensors
        3. Update with each measurement
        4. Return fused state
        
        Returns:
            Fused state estimate or None if all sensors failed
        """
        # Prediction step
        self.ekf.predict(dt=self.dt)
        
        # Collect measurements from all sensors
        sensor_data_list = await self._collect_sensor_data()
        
        # Update with each sensor measurement
        for sensor_data in sensor_data_list:
            self._update_with_sensor(sensor_data)
        
        # Get fused state
        fused_state = self.ekf.get_state()
        
        # Add contributor information
        fused_state.contributors = [s.sensor_id for s in sensor_data_list]
        
        self._last_state = fused_state
        return fused_state
    
    async def _collect_sensor_data(self) -> List[SensorData]:
        """
        Asynchronously read from all sensors
        
        Returns:
            List of valid sensor data (filters out failures)
        """
        # Read all sensors concurrently
        tasks = [sensor.read() for sensor in self.sensors]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter valid data and check health
        valid_data = []
        for sensor, result in zip(self.sensors, results):
            if isinstance(result, SensorData):
                # Check if data passes outlier rejection
                if self._is_valid_measurement(result):
                    valid_data.append(result)
                    self._sensor_health[sensor.sensor_id] = True
            else:
                # Sensor failed or returned None
                self._sensor_health[sensor.sensor_id] = False
        
        return valid_data
    
    def _update_with_sensor(self, sensor_data: SensorData) -> None:
        """
        Update EKF with sensor-specific measurement
        
        Args:
            sensor_data: Sensor measurement to incorporate
        """
        sensor_type = sensor_data.sensor_type
        
        # Route to appropriate update function
        if sensor_type == SensorType.CAMERA:
            # Extract position from camera data (object detection)
            # Placeholder: In reality, you'd extract 3D position from detections
            pass
        
        elif sensor_type == SensorType.LIDAR:
            # LiDAR provides accurate 3D point cloud
            pass
        
        elif sensor_type == SensorType.GPS:
            # GPS provides global position
            pass
        
        elif sensor_type == SensorType.IMU:
            # IMU provides orientation and angular velocity
            pass
    
    def _is_valid_measurement(self, sensor_data: SensorData) -> bool:
        """
        Outlier rejection using Mahalanobis distance
        
        Args:
            sensor_data: Measurement to validate
            
        Returns:
            True if measurement is valid (not an outlier)
        """
        # Placeholder: Implement Mahalanobis distance check
        # Reject if distance > threshold (e.g., 3 standard deviations)
        return True
    
    def get_health_status(self) -> Dict[str, bool]:
        """
        Get health status of all sensors
        
        Returns:
            Dictionary mapping sensor_id to healthy (True/False)
        """
        return self._sensor_health.copy()
