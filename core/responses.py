"""
ADAS Backend - Standardized Response Models
Consistent API response structures for all endpoints
"""

from typing import Generic, TypeVar, Optional, List, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# ============ Response Status Enums ============

class ResponseStatus(str, Enum):
    """API response status"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    PENDING = "pending"


class ErrorCode(str, Enum):
    """Standardized error codes"""
    # Client errors (4xx)
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFLICT = "CONFLICT"
    
    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    MODEL_ERROR = "MODEL_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    
    # Business logic errors
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"


# ============ Generic Response Models ============

T = TypeVar('T')


class APIResponse(BaseModel, Generic[T]):
    """
    Standard API response wrapper
    
    Examples:
        Success: APIResponse(data=user, message="User created successfully")
        Error: APIResponse(status="error", error="User not found", error_code="NOT_FOUND")
    """
    status: ResponseStatus = ResponseStatus.SUCCESS
    data: Optional[T] = None
    message: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[ErrorCode] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {"id": 1, "name": "Example"},
                "message": "Operation completed successfully",
                "timestamp": "2025-11-27T10:00:00Z"
            }
        }


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response for list endpoints"""
    status: ResponseStatus = ResponseStatus.SUCCESS
    data: List[T] = []
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 0
    has_next: bool = False
    has_prev: bool = False
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    @classmethod
    def create(
        cls,
        data: List[T],
        total: int,
        page: int = 1,
        page_size: int = 50,
        message: Optional[str] = None
    ):
        """Helper to create paginated response"""
        total_pages = (total + page_size - 1) // page_size
        return cls(
            data=data,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
            message=message
        )


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "healthy"
    service: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    uptime_seconds: Optional[float] = None
    database: Optional[str] = None
    models_loaded: Optional[int] = None
    memory_usage_mb: Optional[float] = None


class StatusResponse(BaseModel):
    """Detailed status response"""
    status: str = "online"
    service: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    database: str = "unknown"
    features: Dict[str, bool] = {}
    endpoints: Dict[str, str] = {}
    system_info: Optional[Dict[str, Any]] = None


# ============ Detection & Inference Responses ============

class BoundingBox(BaseModel):
    """Bounding box coordinates"""
    x1: float = Field(..., description="Top-left X coordinate")
    y1: float = Field(..., description="Top-left Y coordinate")
    x2: float = Field(..., description="Bottom-right X coordinate")
    y2: float = Field(..., description="Bottom-right Y coordinate")
    
    @property
    def width(self) -> float:
        return self.x2 - self.x1
    
    @property
    def height(self) -> float:
        return self.y2 - self.y1
    
    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


class DetectionObject(BaseModel):
    """Single detected object"""
    class_id: int
    class_name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox: BoundingBox
    distance: Optional[float] = Field(None, description="Distance in meters")
    ttc: Optional[float] = Field(None, description="Time to collision in seconds")
    tracking_id: Optional[int] = None


class InferenceResult(BaseModel):
    """Real-time inference result"""
    frame_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    detections: List[DetectionObject] = []
    total_detections: int = 0
    processing_time_ms: float
    model_name: str
    image_size: tuple[int, int]
    warnings: List[str] = []


class DetectionStats(BaseModel):
    """Detection statistics"""
    total_detections: int = 0
    detections_by_class: Dict[str, int] = {}
    avg_confidence: float = 0.0
    date_range: Optional[Dict[str, datetime]] = None
    top_classes: List[Dict[str, Any]] = []


# ============ Alert Responses ============

class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"


class AlertResponse(BaseModel):
    """Alert notification response"""
    id: int
    alert_type: str
    severity: AlertSeverity
    message: str
    timestamp: datetime
    object_class: Optional[str] = None
    distance: Optional[float] = None
    ttc: Optional[float] = None
    confidence: float
    played: bool = False
    audio_file: Optional[str] = None


class AlertStats(BaseModel):
    """Alert statistics"""
    total_alerts: int = 0
    alerts_by_type: Dict[str, int] = {}
    alerts_by_severity: Dict[str, int] = {}
    recent_alerts: List[AlertResponse] = []
    critical_count_today: int = 0


# ============ Training & Dataset Responses ============

class TrainingStatus(str, Enum):
    """Training job status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrainingProgress(BaseModel):
    """Training progress information"""
    training_id: str
    status: TrainingStatus
    current_epoch: int = 0
    total_epochs: int
    loss: Optional[float] = None
    metrics: Dict[str, float] = {}
    progress_percent: float = 0.0
    eta_seconds: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class DatasetStats(BaseModel):
    """Dataset statistics"""
    total_videos: int = 0
    total_images: int = 0
    total_labels: int = 0
    labeled_images: int = 0
    unlabeled_images: int = 0
    classes_distribution: Dict[str, int] = {}
    storage_size_mb: float = 0.0
    last_updated: Optional[datetime] = None


# ============ Driver Monitoring Responses ============

class DriverState(str, Enum):
    """Driver state enumeration"""
    ALERT = "alert"
    DROWSY = "drowsy"
    DISTRACTED = "distracted"
    UNKNOWN = "unknown"


class DriverMonitoringResult(BaseModel):
    """Driver monitoring analysis result"""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    state: DriverState
    drowsiness_score: float = Field(..., ge=0.0, le=1.0)
    distraction_score: float = Field(..., ge=0.0, le=1.0)
    eye_closure_duration: Optional[float] = None
    head_pose: Optional[Dict[str, float]] = None
    attention_score: float = Field(..., ge=0.0, le=1.0)
    warnings: List[str] = []


# ============ Analytics Responses ============

class DashboardStats(BaseModel):
    """Dashboard overview statistics"""
    total_trips: int = 0
    total_detections: int = 0
    total_alerts: int = 0
    total_events: int = 0
    avg_safety_score: float = 100.0
    active_cameras: int = 0
    models_loaded: int = 0
    system_uptime_hours: float = 0.0
    detection_rate_per_hour: float = 0.0


class TripAnalytics(BaseModel):
    """Trip analytics data"""
    trip_id: int
    duration_minutes: float
    distance_km: Optional[float] = None
    avg_speed: Optional[float] = None
    total_detections: int
    total_alerts: int
    safety_score: float
    dangerous_events: int
    driver_performance: Dict[str, Any] = {}


class TimeSeriesData(BaseModel):
    """Time series data point"""
    timestamp: datetime
    value: float
    label: Optional[str] = None


class ChartData(BaseModel):
    """Chart data for visualization"""
    labels: List[str] = []
    datasets: List[Dict[str, Any]] = []
    title: Optional[str] = None
    type: Optional[str] = "line"  # line, bar, pie, etc.


# ============ WebSocket Messages ============

class WSMessageType(str, Enum):
    """WebSocket message types"""
    FRAME = "frame"
    DETECTION = "detection"
    ALERT = "alert"
    STATUS = "status"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class WSMessage(BaseModel):
    """WebSocket message format"""
    type: WSMessageType
    data: Optional[Any] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message: Optional[str] = None


# ============ Helper Functions ============

def success_response(
    data: Any = None,
    message: Optional[str] = None,
    status_code: int = 200
) -> APIResponse:
    """Create a success response"""
    return APIResponse(
        status=ResponseStatus.SUCCESS,
        data=data,
        message=message or "Operation completed successfully"
    )


def error_response(
    error: str,
    error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
    status_code: int = 500,
    data: Any = None
) -> APIResponse:
    """Create an error response"""
    return APIResponse(
        status=ResponseStatus.ERROR,
        error=error,
        error_code=error_code,
        data=data
    )


def validation_error_response(errors: List[Dict[str, Any]]) -> APIResponse:
    """Create a validation error response"""
    return APIResponse(
        status=ResponseStatus.ERROR,
        error="Validation failed",
        error_code=ErrorCode.VALIDATION_ERROR,
        data={"validation_errors": errors}
    )
