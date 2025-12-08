"""
ADAS Backend - Centralized Configuration
Production-ready configuration management with environment variable support
"""

import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """Application settings with validation"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra fields from .env
    )
    
    # ============ Application Info ============
    APP_NAME: str = "ADAS Backend API"
    APP_VERSION: str = "3.0.0"
    APP_DESCRIPTION: str = "Advanced Driver Assistance System - AI-Powered Backend"
    DEBUG: bool = False
    
    # ============ Server Configuration ============
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    RELOAD: bool = True
    WORKERS: int = 1
    
    # ============ Database Configuration ============
    # SQL Server (Production)
    SQL_SERVER: Optional[str] = None
    SQL_DATABASE: str = "ADAS_DB"
    SQL_USERNAME: Optional[str] = None
    SQL_PASSWORD: Optional[str] = None
    SQL_DRIVER: str = "ODBC Driver 17 for SQL Server"
    
    # SQLite (Development fallback) - DISABLED
    SQLITE_DB_PATH: str = "adas_dev.db"
    
    @property
    def DATABASE_URL(self) -> str:
        """Get database connection URL - Always use in-memory SQLite"""
        # Use in-memory SQLite (no file I/O issues in Docker)
        return "sqlite:///:memory:"
    
    # ============ CORS Configuration ============
    ALLOWED_ORIGINS: List[str] = ["*"]
    ALLOWED_METHODS: List[str] = ["*"]
    ALLOWED_HEADERS: List[str] = ["*"]
    
    # ============ AI/ML Models Configuration ============
    @property
    def BASE_DIR(self) -> Path:
        """Base directory (backend-python folder)"""
        return Path(__file__).parent.parent
    
    @property
    def MODELS_DIR(self) -> Path:
        return self.BASE_DIR / "ai_models" / "weights"
    
    @property
    def DATASET_DIR(self) -> Path:
        return self.BASE_DIR / "dataset"
    
    @property
    def RAW_DATASET_PATH(self) -> Path:
        return self.DATASET_DIR / "raw"
    
    @property
    def LABELS_PATH(self) -> Path:
        return self.DATASET_DIR / "labels"
    
    @property
    def AUTO_COLLECT_PATH(self) -> Path:
        return self.DATASET_DIR / "auto_collected"
    
    @property
    def WEIGHTS_DIR(self) -> Path:
        return self.MODELS_DIR
    
    # YOLOv11 Model Configuration
    YOLO_MODEL_NAME: str = "yolo11n.pt"
    YOLO_CONFIDENCE_THRESHOLD: float = 0.25
    YOLO_IOU_THRESHOLD: float = 0.45
    YOLO_MAX_DETECTIONS: int = 300
    
    # Training Configuration
    TRAINING_EPOCHS: int = 100
    TRAINING_BATCH_SIZE: int = 16
    TRAINING_IMAGE_SIZE: int = 640
    
    # ============ Alert Configuration ============
    ALERT_DISTANCE_THRESHOLD: float = 30.0  # meters
    ALERT_TTC_THRESHOLD: float = 3.0  # seconds
    ALERT_CONFIDENCE_THRESHOLD: float = 0.7
    VOICE_ALERT_ENABLED: bool = True
    
    # ============ Driver Monitoring ============
    DROWSINESS_THRESHOLD: float = 0.6
    DISTRACTION_THRESHOLD: float = 0.7
    DRIVER_MONITOR_FPS: int = 10
    
    # ============ WebSocket Configuration ============
    WS_HEARTBEAT_INTERVAL: int = 30  # seconds
    WS_MAX_CONNECTIONS: int = 100
    
    # ============ Logging Configuration ============
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    @property
    def LOG_DIR(self) -> Path:
        return self.BASE_DIR / "logs"
    
    @property
    def ALERT_LOG_DIR(self) -> Path:
        return self.LOG_DIR / "alerts"
    
    # ============ External Services ============
    PERPLEXITY_API_KEY: Optional[str] = None
    MODEL_WORKER_URL: str = "http://localhost:8001"
    
    # ============ Performance & Limits ============
    MAX_UPLOAD_SIZE: int = 500 * 1024 * 1024  # 500MB
    MAX_VIDEO_DURATION: int = 600  # 10 minutes
    DETECTION_RETENTION_DAYS: int = 30
    ALERT_RETENTION_DAYS: int = 90
    
    # ============ Feature Flags ============
    ENABLE_VOICE_ALERTS: bool = True
    ENABLE_DRIVER_MONITORING: bool = True
    ENABLE_DATASET_COLLECTION: bool = True
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create necessary directories
        self._create_directories()
    
    def _create_directories(self):
        """Create necessary directories if they don't exist"""
        dirs = [
            self.RAW_DATASET_PATH,
            self.LABELS_PATH,
            self.AUTO_COLLECT_PATH,
            self.LOG_DIR,
            self.ALERT_LOG_DIR,
            self.WEIGHTS_DIR,
        ]
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    @property
    def yolo_model_path(self) -> Path:
        """Get full path to YOLO model"""
        return self.MODELS_DIR / self.YOLO_MODEL_NAME
    
    def get_detection_classes(self) -> List[str]:
        """Get list of detection classes"""
        return [
            "person", "bicycle", "car", "motorcycle", "bus", "truck",
            "traffic light", "stop sign", "parking meter", "bench"
        ]


# Global settings instance
settings = Settings()


# ============ Helper Functions ============

def get_settings() -> Settings:
    """Get application settings instance"""
    return settings


def is_production() -> bool:
    """Check if running in production mode"""
    return not settings.DEBUG and settings.SQL_SERVER is not None


def get_device() -> str:
    """Get compute device (cuda/mps/cpu)"""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def print_startup_info():
    """Print startup information"""
    print("=" * 80)
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION}")
    print("=" * 80)
    print(f"Environment: {'Production' if is_production() else 'Development'}")
    print(f"Debug Mode: {settings.DEBUG}")
    print(f"Server: http://{settings.HOST}:{settings.PORT}")
    print(f"Database: {settings.DATABASE_URL.split('://')[0]}://...")
    print(f"Models Dir: {settings.MODELS_DIR}")
    print(f"Dataset Dir: {settings.DATASET_DIR}")
    print(f"Device: {get_device()}")
    print(f"Voice Alerts: {'Enabled' if settings.ENABLE_VOICE_ALERTS else 'Disabled'}")
    print("=" * 80)
    print(f"📊 API Docs: http://localhost:{settings.PORT}/docs")
    print(f"🔌 WebSocket: ws://localhost:{settings.PORT}/ws/infer")
    print(f"💚 Health Check: http://localhost:{settings.PORT}/health")
    print("=" * 80)
