"""
Perception Base Interface - IPerception abstraction
All perception modules implement this interface
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from enum import Enum
import numpy as np


class ObjectClass(Enum):
    """Object classification categories"""
    # Vehicles
    CAR = "car"
    TRUCK = "truck"
    BUS = "bus"
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"
    
    # Vulnerable road users
    PEDESTRIAN = "pedestrian"
    CYCLIST = "cyclist"
    
    # Traffic infrastructure
    TRAFFIC_LIGHT = "traffic_light"
    STOP_SIGN = "stop_sign"
    YIELD_SIGN = "yield_sign"
    SPEED_LIMIT_SIGN = "speed_limit_sign"
    
    # Road features
    LANE_MARKING = "lane_marking"
    ROAD_EDGE = "road_edge"
    CURB = "curb"
    
    # Other
    UNKNOWN = "unknown"


class DangerLevel(Enum):
    """Risk assessment for detected objects"""
    CRITICAL = "critical"  # Immediate collision risk (TTC < 2s)
    HIGH = "high"          # High risk (TTC < 3.5s)
    MEDIUM = "medium"      # Moderate risk
    LOW = "low"            # Safe
    NONE = "none"          # No risk


@dataclass
class BoundingBox:
    """
    2D bounding box in image coordinates
    """
    x_min: float  # Top-left x
    y_min: float  # Top-left y
    x_max: float  # Bottom-right x
    y_max: float  # Bottom-right y
    
    def area(self) -> float:
        """Calculate box area"""
        return (self.x_max - self.x_min) * (self.y_max - self.y_min)
    
    def center(self) -> Tuple[float, float]:
        """Calculate box center"""
        cx = (self.x_min + self.x_max) / 2
        cy = (self.y_min + self.y_max) / 2
        return (cx, cy)
    
    def to_array(self) -> np.ndarray:
        """Convert to numpy array [x_min, y_min, x_max, y_max]"""
        return np.array([self.x_min, self.y_min, self.x_max, self.y_max])


@dataclass
class DetectionObject:
    """
    Detected object with full metadata
    
    Contains:
    - Classification (class, confidence)
    - Localization (2D box, 3D position, distance)
    - Tracking (track_id, velocity)
    - Risk assessment (danger level, TTC)
    """
    # Classification
    class_name: ObjectClass
    confidence: float  # [0.0-1.0]
    
    # 2D localization
    bbox: BoundingBox
    
    # 3D localization (optional)
    position_3d: Optional[np.ndarray] = None  # [x, y, z] in meters
    distance: Optional[float] = None  # Distance in meters
    
    # Tracking
    track_id: Optional[int] = None
    velocity: Optional[np.ndarray] = None  # [vx, vy, vz] in m/s
    
    # Risk assessment
    danger_level: DangerLevel = DangerLevel.NONE
    ttc: Optional[float] = None  # Time to collision in seconds
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_vehicle(self) -> bool:
        """Check if object is a vehicle"""
        return self.class_name in [
            ObjectClass.CAR,
            ObjectClass.TRUCK,
            ObjectClass.BUS,
            ObjectClass.MOTORCYCLE,
            ObjectClass.BICYCLE,
        ]
    
    def is_vulnerable(self) -> bool:
        """Check if object is vulnerable road user (pedestrian, cyclist)"""
        return self.class_name in [
            ObjectClass.PEDESTRIAN,
            ObjectClass.CYCLIST,
        ]


@dataclass
class Lane:
    """
    Lane marking detection result
    """
    # Lane points (pixel coordinates)
    points: List[Tuple[float, float]]
    
    # Lane type
    lane_type: str  # "solid", "dashed", "double"
    
    # Lane position
    side: str  # "left", "right", "center"
    
    # Curve fitting coefficients (polynomial)
    coefficients: Optional[np.ndarray] = None
    
    # Confidence
    confidence: float = 1.0
    
    def fit_polynomial(self, degree: int = 2) -> np.ndarray:
        """
        Fit polynomial to lane points
        
        Args:
            degree: Polynomial degree (2 for quadratic, 3 for cubic)
            
        Returns:
            Polynomial coefficients [a0, a1, a2, ...]
        """
        if len(self.points) < degree + 1:
            return np.zeros(degree + 1)
        
        x = np.array([p[0] for p in self.points])
        y = np.array([p[1] for p in self.points])
        
        self.coefficients = np.polyfit(x, y, degree)
        return self.coefficients


@dataclass
class PerceptionResult:
    """
    Complete perception output for one frame
    
    Contains all detected objects, lanes, and scene understanding
    """
    timestamp: datetime
    
    # Detected objects
    objects: List[DetectionObject] = field(default_factory=list)
    
    # Lane markings
    lanes: List[Lane] = field(default_factory=list)
    
    # Scene understanding
    free_space: Optional[np.ndarray] = None  # Free-space map
    drivable_area: Optional[np.ndarray] = None  # Drivable area mask
    
    # Performance metrics
    inference_time_ms: float = 0.0
    fps: float = 0.0
    
    # Quality indicators
    confidence: float = 1.0  # Overall perception confidence
    
    def get_critical_objects(self) -> List[DetectionObject]:
        """Get all objects with critical danger level"""
        return [obj for obj in self.objects if obj.danger_level == DangerLevel.CRITICAL]
    
    def get_vehicles(self) -> List[DetectionObject]:
        """Get all detected vehicles"""
        return [obj for obj in self.objects if obj.is_vehicle()]
    
    def get_pedestrians(self) -> List[DetectionObject]:
        """Get all detected pedestrians"""
        return [obj for obj in self.objects 
                if obj.class_name == ObjectClass.PEDESTRIAN]


class IPerception(ABC):
    """
    Abstract Base Class for perception modules
    
    Design principles:
    - Single Responsibility: Each module handles ONE perception task
    - Open/Closed: Easy to add new perception modules
    - Liskov Substitution: All modules interchangeable
    
    Performance requirements:
    - Real-time: < 50ms per frame for critical modules
    - Accuracy: > 90% mAP for safety-critical detection
    - Reliability: Graceful degradation on failure
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize perception module
        
        Args:
            config: Module-specific configuration
        """
        self.config = config
        self._is_initialized = False
        self._frame_count = 0
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize perception module (load models, allocate resources)
        
        Returns:
            True if initialization successful
        """
        pass
    
    @abstractmethod
    async def process(self, frame: np.ndarray) -> PerceptionResult:
        """
        Process one frame and return perception results
        
        Args:
            frame: Input image (BGR format, uint8)
            
        Returns:
            PerceptionResult with detected objects/lanes
            
        Performance: Target < 50ms for critical modules
        """
        pass
    
    @abstractmethod
    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Get module diagnostics for monitoring
        
        Returns:
            Diagnostic information (fps, memory, errors, etc.)
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """
        Clean shutdown (release models, free memory)
        """
        pass
    
    def is_initialized(self) -> bool:
        """Check if module is initialized"""
        return self._is_initialized
    
    def get_frame_count(self) -> int:
        """Get total frames processed"""
        return self._frame_count
