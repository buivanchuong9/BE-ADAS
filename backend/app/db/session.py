"""
Database Session Management - PostgreSQL v3.0
==============================================
Native async PostgreSQL with asyncpg driver.
"""

import asyncio
import logging
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncSession, 
    AsyncEngine,
    create_async_engine, 
    async_sessionmaker
)

from ..core.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# PostgreSQL Configuration
# ============================================================

_async_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker] = None


def get_postgres_url() -> str:
    """Generate PostgreSQL connection URL."""
    if settings.PG_PASSWORD:
        return (
            f"postgresql+asyncpg://{settings.PG_USER}:{settings.PG_PASSWORD}"
            f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_NAME}"
        )
    else:
        return (
            f"postgresql+asyncpg://{settings.PG_USER}"
            f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_NAME}"
        )


async def init_db():
    """Initialize PostgreSQL connection pool."""
    global _async_engine, _async_session_factory
    
    try:
        _async_engine = create_async_engine(
            get_postgres_url(),
            echo=settings.DB_ECHO,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=30,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        
        _async_session_factory = async_sessionmaker(
            bind=_async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        # Test connection
        async with _async_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        
        logger.info("PostgreSQL connection initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL: {e}")
        raise


async def close_db():
    """Close PostgreSQL connection pool."""
    global _async_engine
    
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
        logger.info("PostgreSQL connections closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for PostgreSQL database sessions.
    
    Usage:
        @router.post("/api/v3/videos")
        async def upload(db: AsyncSession = Depends(get_db)):
            ...
    """
    if not _async_session_factory:
        raise RuntimeError("PostgreSQL not initialized. Call init_db() first.")
    
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def async_session_maker():
    """
    Context manager for PostgreSQL sessions in background tasks.
    
    Usage:
        async with async_session_maker() as session:
            await session.execute(...)
    """
    if not _async_session_factory:
        raise RuntimeError("PostgreSQL not initialized.")
    
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ============================================================
# Synchronous Session (For Celery Tasks)
# ============================================================

def get_sync_postgres_url() -> str:
    """Generate synchronous PostgreSQL connection URL."""
    # Use psycopg2 driver instead of asyncpg
    url = get_postgres_url()
    return url.replace("postgresql+asyncpg://", "postgresql://")

_sync_engine = None
_sync_session_factory = None

def get_sync_engine():
    global _sync_engine
    if not _sync_engine:
        _sync_engine = create_engine(
            get_sync_postgres_url(),
            echo=settings.DB_ECHO,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True
        )
    return _sync_engine

def SessionLocal():
    """
    Synchronous Database Session for Celery/Threads.
    Use this ONLY in background tasks where async is not available.
    """
    global _sync_session_factory
    
    if not _sync_session_factory:
        from sqlalchemy.orm import sessionmaker
        engine = get_sync_engine()
        _sync_session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine
        )
    
    return _sync_session_factory()
