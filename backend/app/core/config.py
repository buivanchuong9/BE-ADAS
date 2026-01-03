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


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # Application
    APP_NAME: str = "ADAS Backend API"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development or production
    
    # API
    API_BASE_URL: str = "http://localhost:52000"  # Base URL for API
    API_V1_PREFIX: str = "/api/v3"
    HOST: str = "0.0.0.0"
    PORT: int = 52000
    
    # Database - PostgreSQL
    PG_HOST: str = "localhost"
    PG_PORT: int = 5432
    PG_NAME: str = "adas_db"  # Database created
    PG_USER: str = os.getenv("USER", "postgres")  # Current macOS user
    PG_PASSWORD: str = ""
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
    
    # Storage Paths
    STORAGE_ROOT: str = "./backend/storage"
    RAW_VIDEO_DIR: str = "./backend/storage/raw"
    PROCESSED_VIDEO_DIR: str = "./backend/storage/result"
    SNAPSHOT_DIR: str = "./backend/storage/snapshots"
    AUDIO_CACHE_DIR: str = "./backend/storage/audio_cache"
    LOG_DIR: str = "./backend/logs"
    
    # AI Models
    YOLO_MODEL_PATH: str = "./backend/models/yolov11n.pt"
    MEDIAPIPE_MODEL_PATH: str = "./backend/models"
    DEFAULT_DEVICE: str = "cpu"  # cpu or cuda
    
    # Processing Configuration
    MAX_VIDEO_SIZE_MB: int = 1024  # 1GB - Server mạnh, GPU T4 16GB VRAM
    MAX_CONCURRENT_JOBS: int = 2
    VIDEO_CHUNK_SIZE_MB: int = 10
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or console
    LOG_ROTATION: str = "daily"
    LOG_RETENTION_DAYS: int = 30
    
    # CORS - Production domain with all variations (http/https, with/without port)
    # IMPORTANT: Must include all possible Origin header values browsers might send
    CORS_ORIGINS: str = (
        "https://adas-api.aiotlab.edu.vn,"
        "https://adas-api.aiotlab.edu.vn:52000,"
        "http://adas-api.aiotlab.edu.vn,"
        "http://adas-api.aiotlab.edu.vn:52000,"
        "http://localhost:52000,"
        "http://localhost:3000,"
        "http://localhost:8080,"
        "http://127.0.0.1:52000,"
        "http://127.0.0.1:3000,"
        "http://127.0.0.1:8080"
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
        from urllib.parse import quote_plus
        password_encoded = quote_plus(self.PG_PASSWORD) if self.PG_PASSWORD else ""
        
        if password_encoded:
            return f"postgresql+asyncpg://{self.PG_USER}:{password_encoded}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_NAME}"
        else:
            return f"postgresql+asyncpg://{self.PG_USER}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_NAME}"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
