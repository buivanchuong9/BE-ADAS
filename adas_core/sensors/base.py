"""
Sensor Base Interface - ISensor abstraction following SOLID principles
All sensors must implement this interface for plug-and-play architecture
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
import numpy as np


class SensorType(Enum):
    """Enumeration of supported sensor types"""
    CAMERA = "camera"
    LIDAR = "lidar"
    RADAR = "radar"
    ULTRASONIC = "ultrasonic"
    GPS = "gps"
    IMU = "imu"
    CAN_BUS = "can_bus"


class SensorStatus(Enum):
    """Sensor operational status for safety monitoring"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Functioning but with reduced performance
    FAILED = "failed"      # Complete failure
    OFFLINE = "offline"    # Not connected
    INITIALIZING = "initializing"


@dataclass
class SensorData:
    """
    Standardized sensor data container
    All sensors return data in this format for fusion
    """
    timestamp: datetime
    sensor_type: SensorType
    sensor_id: str
    data: Any  # Raw sensor data (frame, point cloud, distance array, etc.)
    confidence: float  # Quality/confidence score [0.0-1.0]
    metadata: Dict[str, Any]  # Additional sensor-specific data
    
    # Safety-critical fields
    checksum: Optional[str] = None  # Data integrity verification
    sequence_number: Optional[int] = None  # For detecting dropped frames


class ISensor(ABC):
    """
    Abstract Base Class for all sensors
    
    Design principles:
    - Single Responsibility: Each sensor handles ONE type of input
    - Interface Segregation: Minimal required methods
    - Dependency Inversion: Depend on abstraction, not concrete implementation
    
    Safety requirements (ISO 26262):
    - Health monitoring
    - Fail-safe behavior
    - Diagnostic error codes
    - Redundancy support
    """
    
    def __init__(self, sensor_id: str, config: Dict[str, Any]):
        """
        Initialize sensor with configuration
        
        Args:
            sensor_id: Unique identifier for this sensor instance
            config: Sensor-specific configuration parameters
        """
        self.sensor_id = sensor_id
        self.config = config
        self._status = SensorStatus.OFFLINE
        self._last_health_check = None
        self._error_count = 0
        self._max_errors = config.get('max_errors', 10)  # Fail after N errors
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize sensor hardware/connection
        
        Returns:
            True if initialization successful, False otherwise
            
        Safety: Must handle exceptions and return False on failure
        """
        pass
    
    @abstractmethod
    async def read(self) -> Optional[SensorData]:
        """
        Read data from sensor (async, non-blocking)
        
        Returns:
            SensorData object or None if read failed
            
        Safety: Must include timeout and error handling
        Performance: <10ms target latency for critical sensors
        """
        pass
    
    @abstractmethod
    def calibrate(self, calibration_data: Dict[str, Any]) -> bool:
        """
        Apply calibration parameters
        
        Args:
            calibration_data: Sensor-specific calibration values
            
        Returns:
            True if calibration successful
            
        Safety: Validate calibration bounds before applying
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """
        Verify sensor operational status
        
        Returns:
            True if sensor healthy, False if degraded/failed
            
        Safety: Must be called periodically (e.g., every 100ms)
        """
        pass
    
    @abstractmethod
    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Retrieve diagnostic information for debugging
        
        Returns:
            Dictionary containing:
            - error_codes: List of active error codes
            - warnings: List of warning messages
            - metrics: Performance metrics (latency, fps, etc.)
            - status: Current sensor status
            
        ISO 26262: Diagnostic Error Management (DEM) requirement
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """
        Gracefully shutdown sensor
        
        Safety: Must release hardware resources and close connections
        """
        pass
    
    # Common helper methods (implemented in base class)
    
    def get_status(self) -> SensorStatus:
        """Get current sensor status"""
        return self._status
    
    def set_status(self, status: SensorStatus) -> None:
        """Update sensor status with logging"""
        if self._status != status:
            print(f"[{self.sensor_id}] Status changed: {self._status.value} → {status.value}")
            self._status = status
    
    def increment_error(self) -> bool:
        """
        Increment error counter and check if threshold exceeded
        
        Returns:
            True if sensor should fail-safe, False otherwise
            
        Safety: Automatic fail-safe when error threshold reached
        """
        self._error_count += 1
        if self._error_count >= self._max_errors:
            self.set_status(SensorStatus.FAILED)
            return True
        elif self._error_count > self._max_errors // 2:
            self.set_status(SensorStatus.DEGRADED)
        return False
    
    def reset_errors(self) -> None:
        """Reset error counter after successful read"""
        if self._error_count > 0:
            self._error_count = max(0, self._error_count - 1)
