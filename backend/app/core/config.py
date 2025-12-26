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
from typing import Optional
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
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 52000
    
    # Database - SQL Server
    DB_HOST: str = "localhost"
    DB_PORT: int = 1433
    DB_NAME: str = "adas_production"
    DB_USER: str = "sa"
    DB_PASSWORD: str = "YourStrong@Passw0rd"
    DB_DRIVER: str = "ODBC Driver 17 for SQL Server"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False  # Set True for SQL query logging
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production-min-32-characters-long"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Storage
    STORAGE_ROOT: str = "./backend/app/storage"
    RAW_VIDEO_DIR: str = "./backend/app/storage/videos/raw"
    PROCESSED_VIDEO_DIR: str = "./backend/app/storage/videos/processed"
    SNAPSHOT_DIR: str = "./backend/app/storage/snapshots"
    LOG_DIR: str = "./backend/app/storage/logs"
    
    # AI/Processing
    DEFAULT_DEVICE: str = "cpu"  # cpu or cuda
    MAX_VIDEO_SIZE_MB: int = 500
    MAX_CONCURRENT_JOBS: int = 2
    
    # CORS
    CORS_ORIGINS: list[str] = [
        "https://adas-api.aiotlab.edu.vn",
        "https://adas-api.aiotlab.edu.vn:52000",
        "http://localhost:3000",  # Development only
        "http://localhost:8080",  # Development only
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def database_url(self) -> str:
        """Generate SQLAlchemy database URL for SQL Server"""
        # URL-encode password for special characters
        from urllib.parse import quote_plus
        
        password_encoded = quote_plus(self.DB_PASSWORD)
        driver_encoded = quote_plus(self.DB_DRIVER)
        
        return (
            f"mssql+pyodbc://{self.DB_USER}:{password_encoded}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?driver={driver_encoded}"
            f"&TrustServerCertificate=yes"
        )
    
    @property
    def async_database_url(self) -> str:
        """Generate async database URL - Use SQLite for development, SQL Server for production"""
        # For development: use SQLite (no SQL Server needed)
        if self.ENVIRONMENT == "development" or not self.DB_HOST or self.DB_HOST == "localhost":
            return "sqlite+aiosqlite:///./backend/adas.db"
        
        # For production: use SQL Server with pyodbc (sync driver works with async)
        from urllib.parse import quote_plus
        
        password_encoded = quote_plus(self.DB_PASSWORD)
        driver_encoded = quote_plus(self.DB_DRIVER)
        
        # Use mssql+pyodbc instead of mssql+aiodbc (more stable)
        return (
            f"mssql+pyodbc://{self.DB_USER}:{password_encoded}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?driver={driver_encoded}"
            f"&TrustServerCertificate=yes"
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
