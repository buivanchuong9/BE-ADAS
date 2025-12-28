"""
Application Configuration
==========================
Uses Pydantic Settings for environment-based configuration.

Environment variables:
- DB_HOST: SQL Server host (default: localhost)
- DB_PORT: SQL Server port (default: 1433)
- DB_NAME: Database name (default: adas_production)
- DB_USER: Database user
- DB_PASSWORD: Database password
- DB_DRIVER: ODBC Driver name (default: ODBC Driver 17 for SQL Server)
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
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development or production
    
    # API
    API_BASE_URL: str = "http://localhost:52000"  # Base URL for API
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 52000
    
    # Database - SQL Server
    DB_HOST: str = "localhost"
    DB_PORT: int = 1433
    DB_NAME: str = "adas_production"
    DB_USER: str = "sa"
    DB_PASSWORD: str = "YourStrong@Passw0rd"
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False  # Set True for SQL query logging
    
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
    MAX_VIDEO_SIZE_MB: int = 500
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
        case_sensitive = True
    
    @property
    def database_url(self) -> str:
        """
        Generate SQLAlchemy database URL for SQL Server.
        
        ODBC Driver 18 requires explicit SSL/TLS configuration:
        - TrustServerCertificate=yes: Required for local/dev environments without valid SSL certs
        - For production: Use proper SSL certificates and set TrustServerCertificate=no
        
        Returns:
            Database connection URL with ODBC Driver 18 settings
        """
        # URL-encode password for special characters
        from urllib.parse import quote_plus
        
        password_encoded = quote_plus(self.DB_PASSWORD)
        driver_encoded = quote_plus(self.DB_DRIVER)
        
        # ODBC Driver 18 connection string with SSL settings
        return (
            f"mssql+pyodbc://{self.DB_USER}:{password_encoded}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?driver={driver_encoded}"
            f"&TrustServerCertificate=yes"  # Required for ODBC Driver 18
            f"&Encrypt=yes"  # Explicit encryption setting
        )
    
    @property
    def async_database_url(self) -> str:
        """
        Generate async database URL - Uses sync driver (pyodbc) with async wrapper.
        
        Note: We use mssql+pyodbc (sync driver) instead of mssql+aiodbc because:
        - More stable and mature
        - Better compatibility with ODBC Driver 18
        - Wrapped in async context via AsyncSessionWrapper
        
        Returns:
            Same as database_url (sync driver used in async context)
        """
        # Use same configuration as sync URL
        return self.database_url


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
