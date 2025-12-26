"""
Database Session Management
============================
Async SQLAlchemy session configuration and dependency injection.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator
import logging

from ..core.config import settings

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    # Use NullPool for better compatibility with SQL Server
    poolclass=NullPool,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for database sessions.
    
    Usage in FastAPI:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database (create tables if not exist)"""
    from .base import Base
    # Import all models to register them with SQLAlchemy
    from .models.user import User
    from .models.vehicle import Vehicle
    from .models.trip import Trip
    from .models.video_job import VideoJob
    from .models.safety_event import SafetyEvent
    from .models.driver_state import DriverState
    from .models.traffic_sign import TrafficSign
    from .models.alert import Alert
    from .models.model_version import ModelVersion
    
    async with engine.begin() as conn:
        # In production, use Alembic migrations instead
        # This is for development/testing
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database initialized successfully")


async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("Database connections closed")
