"""
Database Session Management
============================
Async SQLAlchemy session configuration with sync driver (pyodbc).
Uses run_sync to execute sync operations in async context.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator
import logging
import asyncio

from ..core.config import settings

logger = logging.getLogger(__name__)

# Create sync engine (pyodbc is sync driver)
sync_engine = create_engine(
    settings.database_url,  # Use sync URL
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
)

# Create sync session factory
sync_session_factory = sessionmaker(
    sync_engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# Async wrapper for sync session
class AsyncSessionWrapper:
    """Wraps sync session to work with async code"""
    
    def __init__(self, sync_session):
        self.sync_session = sync_session
    
    async def execute(self, statement):
        """Execute statement in thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.sync_session.execute, statement)
    
    async def commit(self):
        """Commit in thread pool"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.sync_session.commit)
    
    async def rollback(self):
        """Rollback in thread pool"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.sync_session.rollback)
    
    async def close(self):
        """Close in thread pool"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.sync_session.close)
    
    def add(self, instance):
        """Add instance (sync operation)"""
        return self.sync_session.add(instance)
    
    async def refresh(self, instance):
        """Refresh in thread pool"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.sync_session.refresh, instance)


async def get_db() -> AsyncGenerator[AsyncSessionWrapper, None]:
    """
    Dependency for database sessions.
    Returns async wrapper around sync session.
    """
    session = sync_session_factory()
    async_wrapper = AsyncSessionWrapper(session)
    try:
        yield async_wrapper
    except Exception:
        await async_wrapper.rollback()
        raise
    finally:
        await async_wrapper.close()


def async_session_maker():
    """
    Create a new async session wrapper.
    Use this for background tasks that need their own session.
    
    Returns:
        AsyncSessionWrapper context manager
    """
    class SessionContextManager:
        async def __aenter__(self):
            self.session = sync_session_factory()
            self.wrapper = AsyncSessionWrapper(self.session)
            return self.wrapper
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            if exc_type:
                await self.wrapper.rollback()
            await self.wrapper.close()
    
    return SessionContextManager()


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
    
    # Use sync engine to create tables
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, Base.metadata.create_all, sync_engine)
    
    logger.info("Database initialized successfully")


async def close_db():
    """Close database connections"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, sync_engine.dispose)
    logger.info("Database connections closed")
