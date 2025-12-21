"""
Data models and in-memory storage for ADAS API
This module contains Pydantic models and in-memory storage for testing
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import uuid


# ============================================================================
# ENUMS
# ============================================================================

class VideoStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    COMPLETED = "completed"
    ERROR = "error"


class EventType(str, Enum):
    COLLISION = "collision"
    LANE_DEPARTURE = "lane_departure"
    FATIGUE = "fatigue"
    DISTRACTION = "distraction"
    SPEED = "speed"
    DRIVER_STATUS = "driver_status"


class EventSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class TripStatus(str, Enum):
    ONGOING = "ongoing"
    COMPLETED = "completed"


class ModelType(str, Enum):
    DETECTION = "detection"
    SEGMENTATION = "segmentation"
    DEPTH = "depth"


class StreamStatus(str, Enum):
    PROCESSING = "processing"
    STOPPED = "stopped"
    ERROR = "error"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class DetectionSaveRequest(BaseModel):
    video_id: Optional[int] = None
    camera_id: Optional[str] = None
    detections: List[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]] = None


class EventCreateRequest(BaseModel):
    type: EventType
    severity: EventSeverity
    description: str
    timestamp: str
    location: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    video_id: Optional[int] = None
    camera_id: Optional[str] = None


class TripCreateRequest(BaseModel):
    driver_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    start_location: Optional[str] = None
    end_location: Optional[str] = None
    distance_km: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class TripCompleteRequest(BaseModel):
    end_time: str
    distance_km: float


class DriverStatusRequest(BaseModel):
    driver_id: Optional[str] = None
    fatigue_level: int
    distraction_level: int
    eyes_closed: bool
    head_pose: Optional[Dict[str, Any]] = None
    timestamp: str
    camera_id: Optional[str] = None


class StreamStartRequest(BaseModel):
    source: Literal["webcam", "video"]
    model_id: str = "yolo11n"
    video_id: Optional[int] = None
    config: Optional[Dict[str, Any]] = None


class StreamStopRequest(BaseModel):
    session_id: str


class AIChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    context: Optional[Any] = None


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class DatasetItem(BaseModel):
    id: int
    filename: str
    file_path: str
    video_url: Optional[str] = None
    file_url: Optional[str] = None
    description: Optional[str] = None
    file_size_mb: float
    duration_seconds: Optional[float] = None
    uploaded_at: str
    status: VideoStatus = VideoStatus.UPLOADED
    ready_for_training: bool = False
    metadata: Optional[Dict[str, Any]] = None


class Detection(BaseModel):
    id: int
    class_name: str
    class_id: int
    confidence: float
    bbox: List[float]
    timestamp: str
    camera_id: Optional[str] = None
    video_id: Optional[int] = None


class Event(BaseModel):
    id: int
    type: str
    severity: str
    title: str
    description: str
    timestamp: str
    location: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    acknowledged: bool = False


class Alert(BaseModel):
    id: int
    type: str
    severity: AlertSeverity
    message: str
    timestamp: str
    played: bool = False
    data: Optional[Dict[str, Any]] = None


class Trip(BaseModel):
    id: int
    driver_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    distance_km: float = 0.0
    duration_minutes: int = 0
    safety_score: float = 85.0
    events_count: int = 0
    status: TripStatus = TripStatus.ONGOING


class ModelInfo(BaseModel):
    id: str
    name: str
    description: str
    type: ModelType
    size_mb: float
    accuracy: float
    speed_ms: float
    downloaded: bool
    file_path: Optional[str] = None
    download_url: Optional[str] = None
    classes: Optional[List[str]] = None
    input_size: Optional[List[int]] = None
    metadata: Optional[Dict[str, Any]] = None


class Video(BaseModel):
    id: int
    filename: str
    file_path: str
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_seconds: float = 0.0
    fps: float = 30.0
    resolution: Dict[str, int] = {"width": 1920, "height": 1080}
    file_size_mb: float
    uploaded_at: str
    processed: bool = False
    processing_time_seconds: Optional[float] = None
    detections_count: int = 0
    status: VideoStatus = VideoStatus.UPLOADED


class DriverStatus(BaseModel):
    fatigue_level: int
    distraction_level: int
    eyes_closed: bool
    last_updated: str
    alert_status: Literal["normal", "warning", "critical"] = "normal"


class StreamSession(BaseModel):
    session_id: str
    source: str
    model_id: str
    video_id: Optional[int] = None
    status: StreamStatus = StreamStatus.PROCESSING
    created_at: str
    fps: float = 30.0
    frame_count: int = 0


# ============================================================================
# IN-MEMORY STORAGE
# ============================================================================

class InMemoryStorage:
    """In-memory storage for testing purposes"""
    
    def __init__(self):
        # Counters for IDs
        self.dataset_counter = 1
        self.detection_counter = 1
        self.event_counter = 1
        self.alert_counter = 1
        self.trip_counter = 1
        self.video_counter = 1
        
        # Storage dictionaries
        self.datasets: Dict[int, DatasetItem] = {}
        self.detections: List[Detection] = []
        self.events: Dict[int, Event] = {}
        self.alerts: Dict[int, Alert] = {}
        self.trips: Dict[int, Trip] = {}
        self.videos: Dict[int, Video] = {}
        self.stream_sessions: Dict[str, StreamSession] = {}
        self.driver_status_history: List[Dict[str, Any]] = []
        self.chat_history: List[Dict[str, Any]] = []
        
        # Models catalog
        self.models_catalog: Dict[str, ModelInfo] = {
            "yolo11n": ModelInfo(
                id="yolo11n",
                name="YOLOv11 Nano",
                description="Lightweight object detection model for ADAS",
                type=ModelType.DETECTION,
                size_mb=6.2,
                accuracy=0.89,
                speed_ms=15.0,
                downloaded=True,
                file_path="/models/yolo11n.pt",
                classes=["person", "car", "motorcycle", "bus", "truck", "bicycle"],
                input_size=[640, 640]
            ),
            "yolo11s": ModelInfo(
                id="yolo11s",
                name="YOLOv11 Small",
                description="Balanced detection model",
                type=ModelType.DETECTION,
                size_mb=12.5,
                accuracy=0.92,
                speed_ms=25.0,
                downloaded=False,
                download_url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt",
                classes=["person", "car", "motorcycle", "bus", "truck", "bicycle"],
                input_size=[640, 640]
            ),
            "yolo11m": ModelInfo(
                id="yolo11m",
                name="YOLOv11 Medium",
                description="High accuracy detection model",
                type=ModelType.DETECTION,
                size_mb=25.8,
                accuracy=0.94,
                speed_ms=40.0,
                downloaded=False,
                download_url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt",
                classes=["person", "car", "motorcycle", "bus", "truck", "bicycle"],
                input_size=[640, 640]
            ),
            "depth-anything": ModelInfo(
                id="depth-anything",
                name="Depth Anything",
                description="Monocular depth estimation",
                type=ModelType.DEPTH,
                size_mb=335.0,
                accuracy=0.91,
                speed_ms=50.0,
                downloaded=False,
                download_url="https://huggingface.co/depth-anything/Depth-Anything-V2-Small",
                input_size=[518, 518]
            ),
            "mediapipe-face": ModelInfo(
                id="mediapipe-face",
                name="MediaPipe Face Detection",
                description="Face landmarks and drowsiness detection",
                type=ModelType.DETECTION,
                size_mb=8.5,
                accuracy=0.96,
                speed_ms=10.0,
                downloaded=True,
                file_path="/models/mediapipe/face_detection.tflite"
            )
        }
        
        # Initialize with sample data
        self._initialize_sample_data()
    
    def _initialize_sample_data(self):
        """Initialize with sample data for testing"""
        from datetime import datetime, timedelta
        
        # Sample datasets
        sample_datasets = [
            DatasetItem(
                id=self.dataset_counter,
                filename="dashcam_highway_01.mp4",
                file_path="/storage/videos/2025/12/dashcam_highway_01.mp4",
                video_url="/api/video/download/1/dashcam_highway_01.mp4",
                description="Highway driving - morning commute",
                file_size_mb=245.5,
                duration_seconds=180.0,
                uploaded_at=(datetime.now() - timedelta(days=2)).isoformat(),
                status=VideoStatus.READY,
                ready_for_training=True,
                metadata={"fps": 30, "resolution": "1920x1080"}
            ),
            DatasetItem(
                id=self.dataset_counter + 1,
                filename="urban_driving_02.mp4",
                file_path="/storage/videos/2025/12/urban_driving_02.mp4",
                video_url="/api/video/download/2/urban_driving_02.mp4",
                description="City traffic - rush hour",
                file_size_mb=189.2,
                duration_seconds=150.0,
                uploaded_at=(datetime.now() - timedelta(days=1)).isoformat(),
                status=VideoStatus.READY,
                ready_for_training=True
            )
        ]
        
        for ds in sample_datasets:
            self.datasets[ds.id] = ds
            self.dataset_counter += 1
        
        # Sample detections
        sample_classes = ["car", "person", "motorcycle", "truck", "bicycle"]
        for i in range(20):
            det = Detection(
                id=self.detection_counter,
                class_name=sample_classes[i % len(sample_classes)],
                class_id=i % len(sample_classes),
                confidence=0.75 + (i % 20) * 0.01,
                bbox=[100 + i * 10, 200 + i * 5, 300 + i * 10, 400 + i * 5],
                timestamp=(datetime.now() - timedelta(minutes=i * 5)).isoformat(),
                camera_id="cam_01",
                video_id=1
            )
            self.detections.append(det)
            self.detection_counter += 1
        
        # Sample events
        sample_events = [
            Event(
                id=self.event_counter,
                type="lane_departure",
                severity="warning",
                title="Lane Departure Warning",
                description="Vehicle drifted from lane without signal",
                timestamp=(datetime.now() - timedelta(hours=2)).isoformat(),
                location="Highway 101, Mile 45",
                acknowledged=False
            ),
            Event(
                id=self.event_counter + 1,
                type="collision",
                severity="critical",
                title="Forward Collision Risk",
                description="Sudden braking detected - potential collision avoided",
                timestamp=(datetime.now() - timedelta(hours=1)).isoformat(),
                location="Main St & 5th Ave",
                acknowledged=True
            )
        ]
        
        for evt in sample_events:
            self.events[evt.id] = evt
            self.event_counter += 1
        
        # Sample alerts
        sample_alerts = [
            Alert(
                id=self.alert_counter,
                type="fatigue_warning",
                severity=AlertSeverity.WARNING,
                message="Driver fatigue detected - consider taking a break",
                timestamp=(datetime.now() - timedelta(minutes=30)).isoformat(),
                played=False,
                data={"fatigue_level": 75}
            ),
            Alert(
                id=self.alert_counter + 1,
                type="speed_warning",
                severity=AlertSeverity.INFO,
                message="Speed limit exceeded - reduce speed",
                timestamp=(datetime.now() - timedelta(minutes=15)).isoformat(),
                played=True,
                data={"current_speed": 75, "speed_limit": 60}
            )
        ]
        
        for alert in sample_alerts:
            self.alerts[alert.id] = alert
            self.alert_counter += 1


# Global storage instance
storage = InMemoryStorage()
