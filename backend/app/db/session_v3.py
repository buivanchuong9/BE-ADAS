"""
Database Session Management - PostgreSQL v3.0
==============================================
Native async PostgreSQL with asyncpg driver.
Fallback to SQL Server wrapper for migration period.
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
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from ..core.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# PostgreSQL Configuration (Primary - v3.0)
# ============================================================

# Async engine for PostgreSQL
_async_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker] = None


def get_postgres_url() -> str:
    """Generate PostgreSQL connection URL."""
    return (
        f"postgresql+asyncpg://{settings.PG_USER}:{settings.PG_PASSWORD}"
        f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_NAME}"
    )


def get_postgres_sync_url() -> str:
    """Generate sync PostgreSQL URL for migrations."""
    return (
        f"postgresql://{settings.PG_USER}:{settings.PG_PASSWORD}"
        f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_NAME}"
    )


async def init_postgres_db():
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
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL: {e}")
        return False


async def close_postgres_db():
    """Close PostgreSQL connection pool."""
    global _async_engine
    
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
        logger.info("PostgreSQL connections closed")


async def get_postgres_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for PostgreSQL database sessions.
    
    Usage:
        @router.post("/api/v3/videos")
        async def upload(db: AsyncSession = Depends(get_postgres_session)):
            ...
    """
    if not _async_session_factory:
        raise RuntimeError("PostgreSQL not initialized. Call init_postgres_db() first.")
    
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
async def postgres_session_context():
    """
    Context manager for PostgreSQL sessions in background tasks.
    
    Usage:
        async with postgres_session_context() as session:
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
# SQL Server Configuration (Legacy - for migration period)
# ============================================================

from sqlalchemy.orm import Session

# Sync engine for SQL Server (legacy)
_sync_engine = None
_sync_session_factory = None


def init_sqlserver_db():
    """Initialize SQL Server connection (legacy)."""
    global _sync_engine, _sync_session_factory
    
    try:
        _sync_engine = create_engine(
            settings.database_url,
            echo=settings.DB_ECHO,
            pool_pre_ping=True,
        )
        
        _sync_session_factory = sessionmaker(
            bind=_sync_engine,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        logger.info("SQL Server connection initialized (legacy mode)")
        return True
        
    except Exception as e:
        logger.warning(f"SQL Server not available: {e}")
        return False


class AsyncSessionWrapper:
    """Wraps sync session to work with async code (legacy SQL Server)."""
    
    def __init__(self, sync_session: Session):
        self.sync_session = sync_session
    
    async def execute(self, statement):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.sync_session.execute, statement)
    
    async def commit(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.sync_session.commit)
    
    async def rollback(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.sync_session.rollback)
    
    async def close(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.sync_session.close)
    
    def add(self, instance):
        return self.sync_session.add(instance)
    
    async def refresh(self, instance):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.sync_session.refresh, instance)


async def get_sqlserver_session() -> AsyncGenerator[AsyncSessionWrapper, None]:
    """Dependency for SQL Server sessions (legacy)."""
    if not _sync_session_factory:
        raise RuntimeError("SQL Server not initialized.")
    
    session = _sync_session_factory()
    wrapper = AsyncSessionWrapper(session)
    try:
        yield wrapper
    except Exception:
        await wrapper.rollback()
        raise
    finally:
        await wrapper.close()


# ============================================================
# Unified Interface (Auto-selects PostgreSQL or SQL Server)
# ============================================================

_use_postgres: bool = True  # Default to PostgreSQL


async def init_db():
    """
    Initialize database connection.
    Tries PostgreSQL first, falls back to SQL Server.
    """
    global _use_postgres
    
    # Try PostgreSQL first
    if await init_postgres_db():
        _use_postgres = True
        logger.info("Using PostgreSQL (v3.0 mode)")
        return
    
    # Fallback to SQL Server
    if init_sqlserver_db():
        _use_postgres = False
        logger.info("Using SQL Server (legacy mode)")
        return
    
    raise RuntimeError("No database available!")


async def close_db():
    """Close database connections."""
    if _use_postgres:
        await close_postgres_db()
    elif _sync_engine:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_engine.dispose)


async def get_db():
    """
    Unified database session dependency.
    Returns PostgreSQL session or SQL Server wrapper.
    """
    if _use_postgres:
        async for session in get_postgres_session():
            yield session
    else:
        async for session in get_sqlserver_session():
            yield session


def async_session_maker():
    """
    Create session context manager for background tasks.
    """
    if _use_postgres:
        return postgres_session_context()
    else:
        # SQL Server fallback
        class SQLServerSessionContext:
            async def __aenter__(self):
                self.session = _sync_session_factory()
                self.wrapper = AsyncSessionWrapper(self.session)
                return self.wrapper
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                if exc_type:
                    await self.wrapper.rollback()
                await self.wrapper.close()
        
        return SQLServerSessionContext()
