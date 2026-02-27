"""
Application Configuration - v3.0 (PostgreSQL)
==============================================
Uses Pydantic Settings for environment-based configuration.

Environment variables:
- PG_HOST: PostgreSQL host (default: localhost)
- PG_PORT: PostgreSQL port (default: 5432)
- PG_NAME: Database name (default: adas_db)
- PG_USER: Database user (default: adas_user)
- PG_PASSWORD: Database password
- SECRET_KEY: JWT secret key
- ALGORITHM: JWT algorithm (default: HS256)
- ACCESS_TOKEN_EXPIRE_MINUTES: Token expiry (default: 30)
"""

from pydantic_settings import BaseSettings
from typing import Optional, List
from functools import lru_cache
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # Application
    APP_NAME: str = "ADAS Backend API"
    APP_VERSION: str = "3.0.2"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development or production
    
    # API
    API_BASE_URL: str = "http://localhost:52000"  # Base URL for API
    API_V1_PREFIX: str = "/api/v3"
    HOST: str = "0.0.0.0"
    PORT: int = 52000
    
    # Database - PostgreSQL
    PG_HOST: str = "127.0.0.1"
    PG_PORT: int = 5432
    PG_NAME: str = "adas_db"
    PG_USER: str = "adas_user"
    PG_PASSWORD: str = "adas123"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False  # Set True for SQL query logging
        
    # v3.0 Storage Paths (production: /hdd3/adas/)
    HDD3_ROOT: str = "/hdd3/adas"
    VIDEOS_RAW_DIR: str = "/hdd3/adas/videos/raw"
    VIDEOS_OUTPUT_DIR: str = "/hdd3/adas/videos/output"
    
    # Security & Authentication
    SECRET_KEY: str = "your-secret-key-change-in-production-min-32-characters-long"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Supabase Authentication
    SUPABASE_PROJECT_ID: str = "kijdjdtuyeywmthhuoac"
    SUPABASE_PROJECT_URL: str = "https://kijdjdtuyeywmthhuoac.supabase.co"
    SUPABASE_JWKS_URL: str = "https://kijdjdtuyeywmthhuoac.supabase.co/auth/v1/.well-known/jwks.json"
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    SUPABASE_JWT_ALGORITHM: str = "ES256"
    # Anon key for Supabase client (public, safe to expose)
    SUPABASE_ANON_KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtpamRqZHR1eWV5d210aGh1b2FjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjczMzY0MTUsImV4cCI6MjA4MjkxMjQxNX0.T2UOrxb53Op_xfMMoaTvQIUs0c_PJbPdlezz4B1-9Lg"  # Set via environment variable
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None  # Required for server-side logging (bypassing RLS)
    
    # Storage Paths
    STORAGE_ROOT: str = "./backend/storage"
    RAW_VIDEO_DIR: str = "./backend/storage/raw"
    PROCESSED_VIDEO_DIR: str = "./backend/storage/result"
    SNAPSHOT_DIR: str = "./backend/storage/snapshots"
    AUDIO_CACHE_DIR: str = "./backend/storage/audio_cache"
    LOG_DIR: str = "./backend/logs"
    
    # AI Models - LINH HOẠT: Có thể override qua env hoặc auto-detect
    YOLO_MODEL_PATH: str = "./backend/models/yolo11x.pt"  # Default fallback
    MEDIAPIPE_MODEL_PATH: str = "./backend/models"
    DEFAULT_DEVICE: str = "cpu"  # cpu or cuda
    
    # Auto-detect: Tự động tìm model mới nhất
    AUTO_USE_LATEST_MODEL: bool = False  # Set True để tự động dùng model mới nhất
    TRAINING_DIR: str = "./backend/training"  # Folder chứa model train
    MODEL_PRIORITY: str = "best"  # "best", "last", hoặc "latest" (newest file)
    
    def get_yolo_model_path(self) -> str:
        """
        🚀 TỰ ĐỘNG TÌM MODEL - LINH HOẠT 100%
        
        Thứ tự ưu tiên:
        1. Env YOLO_MODEL_PATH (cao nhất - manual override)
        2. Auto-detect từ training/ nếu AUTO_USE_LATEST_MODEL=True
           - MODEL_PRIORITY="best" → training/best_training.pt
           - MODEL_PRIORITY="last" → training/last.pt  
           - MODEL_PRIORITY="latest" → file .pt mới nhất theo thời gian
        3. Fallback: models/yolo11x.pt (default)
        
        Ví dụ sử dụng:
        - export AUTO_USE_LATEST_MODEL=true MODEL_PRIORITY=best
        - export YOLO_MODEL_PATH=./backend/training/lane_vip_v1.pt
        """
        # Priority 1: Manual override qua env
        env_path = os.getenv("YOLO_MODEL_PATH")
        if env_path and env_path != self.YOLO_MODEL_PATH:
            if Path(env_path).exists():
                print(f"✅ Using MANUAL model: {env_path}")
                return env_path
            else:
                print(f"⚠️ WARNING: {env_path} not found, falling back...")
        
        # Priority 2: Auto-detect từ training/
        auto_use = os.getenv("AUTO_USE_LATEST_MODEL", str(self.AUTO_USE_LATEST_MODEL)).lower() == "true"
        if auto_use:
            training_dir = Path(os.getenv("TRAINING_DIR", self.TRAINING_DIR))
            if training_dir.exists():
                priority = os.getenv("MODEL_PRIORITY", self.MODEL_PRIORITY).lower()
                
                # Tìm theo tên cụ thể
                if priority == "best":
                    best_path = training_dir / "best_training.pt"
                    if best_path.exists():
                        print(f"🔥 AUTO: Using BEST model: {best_path}")
                        return str(best_path)
                elif priority == "last":
                    last_path = training_dir / "last.pt"
                    if last_path.exists():
                        print(f"🔥 AUTO: Using LAST model: {last_path}")
                        return str(last_path)
                
                # Tìm file .pt mới nhất
                if priority == "latest" or priority not in ["best", "last"]:
                    pt_files = list(training_dir.glob("*.pt"))
                    if pt_files:
                        latest = max(pt_files, key=lambda p: p.stat().st_mtime)
                        print(f"🔥 AUTO: Using LATEST model: {latest}")
                        return str(latest)
        
        # Priority 3: Fallback default
        print(f"ℹ️ Using DEFAULT model: {self.YOLO_MODEL_PATH}")
        return self.YOLO_MODEL_PATH
    
    # Processing Configuration
    MAX_VIDEO_SIZE_MB: int = 1024  # 1GB - Server mạnh, GPU T4 16GB VRAM
    MAX_CONCURRENT_JOBS: int = 12  # Increased to 12 for GPU A30 (24GB VRAM)
    VIDEO_CHUNK_SIZE_MB: int = 10
    
    # === ADAS CONFIGURATION - HỆ THỐNG ADAS THUẦN VIỆT ===
    # GPU Configuration
    ADAS_GPU_DEVICE: str = "cuda"  # GPU device for ADAS models
    ADAS_GPU_MEMORY_FRACTION: float = 0.8  # Use 80% GPU memory
    ADAS_BATCH_SIZE: int = 1  # Batch size for video processing
    
    # Model Performance Thresholds
    ADAS_OBJECT_CONFIDENCE: float = 0.5   # Confidence threshold for object detection  
    ADAS_LANE_CONFIDENCE: float = 0.4     # Confidence threshold for lane detection
    ADAS_TRAFFIC_CONFIDENCE: float = 0.6  # Confidence threshold for traffic signs
    ADAS_DRIVER_CONFIDENCE: float = 0.7   # Confidence threshold for driver monitoring
    
    # Distance & Risk Assessment (Vietnamese driving conditions)
    ADAS_CRITICAL_DISTANCE_M: float = 3.0     # Critical collision distance (meters)
    ADAS_DANGER_DISTANCE_M: float = 8.0       # Danger zone distance (meters) 
    ADAS_CAUTION_DISTANCE_M: float = 15.0     # Caution zone distance (meters)
    ADAS_CRITICAL_TTC_S: float = 1.0          # Critical time-to-collision (seconds)
    ADAS_DANGER_TTC_S: float = 2.5            # Danger TTC threshold
    ADAS_CAUTION_TTC_S: float = 4.0           # Caution TTC threshold
    
    # Vietnamese-specific settings
    ADAS_MOTORCYCLE_FACTOR: float = 0.7       # Distance factor for motorcycles (closer following)
    ADAS_URBAN_SPEED_FACTOR: float = 0.8      # Speed factor for urban areas
    ADAS_VOICE_WARNINGS: bool = True          # Enable Vietnamese voice warnings
    ADAS_WARNING_COOLDOWN_S: float = 3.0      # Seconds between voice warnings
    
    # Output Settings
    ADAS_OUTPUT_RESOLUTION: str = "1280x720"  # HD output for clear Vietnamese text
    ADAS_OVERLAY_ALPHA: float = 0.7           # Transparency for overlays
    ADAS_HUD_ENABLED: bool = True             # Enable Vietnamese HUD
    ADAS_LANE_COLOR: str = "cyan"             # Tesla-style cyan lanes
    
    # Processing Features Toggle
    ADAS_ENABLE_OBJECT_DETECTION: bool = True
    ADAS_ENABLE_LANE_DETECTION: bool = True
    ADAS_ENABLE_DISTANCE_ESTIMATION: bool = True
    ADAS_ENABLE_DRIVER_MONITORING: bool = True
    ADAS_ENABLE_TRAFFIC_SIGNS: bool = True
    ADAS_ENABLE_RISK_ASSESSMENT: bool = True
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or console
    LOG_ROTATION: str = "daily"
    LOG_RETENTION_DAYS: int = 30
    
    # CORS - Production domain with all variations (http/https, with/without port)
    # IMPORTANT: Must include all possible Origin header values browsers might send
    CORS_ORIGINS: str = (
        "https://adas.aiotlab.edu.vn,"
        "https://www.adas.aiotlab.edu.vn,"
        "http://adas.aiotlab.edu.vn,"  # Fix: Add HTTP origin for Safari/Cloudflare edge cases
        "https://adas-api.aiotlab.edu.vn,"
        "https://adas-api.aiotlab.edu.vn:52000,"
        "https://adas-api.aiotlab.edu.vn/docs,"
        "http://adas-api.aiotlab.edu.vn,"
        "http://adas-api.aiotlab.edu.vn:52000,"
        "http://localhost:52000,"
        "http://localhost:3000,"
        "http://localhost:5173,"
        "http://localhost:8080,"
        "http://127.0.0.1:52000,"
        "http://127.0.0.1:3000,"
        "http://127.0.0.1:8080,"
        "http://127.0.0.1:5173"
    )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS string into list"""
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return self.CORS_ORIGINS
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"  # Allow extra env vars from old MSSQL config
    
    @property
    def database_url(self) -> str:
        """Generate PostgreSQL database URL."""
        return f"postgresql+asyncpg://{self.PG_USER}:{self.PG_PASSWORD}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_NAME}"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
