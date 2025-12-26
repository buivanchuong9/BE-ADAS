"""
Database Initialization Script
===============================
Creates database schema and seeds initial data.

Usage:
    python backend/scripts/init_db.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import init_db, engine
from app.core.config import settings
from app.core.logging import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


async def main():
    """Initialize database"""
    logger.info("=" * 80)
    logger.info("ADAS Database Initialization")
    logger.info("=" * 80)
    logger.info(f"Database: {settings.DB_NAME}")
    logger.info(f"Host: {settings.DB_HOST}:{settings.DB_PORT}")
    logger.info("")
    
    try:
        # Initialize database (create tables)
        logger.info("Creating database tables...")
        await init_db()
        logger.info("✓ Database tables created successfully")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("Database initialization complete!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Run seed script: python backend/scripts/seed_data.py")
        logger.info("2. Create first migration: alembic revision --autogenerate -m 'initial'")
        logger.info("3. Apply migration: alembic upgrade head")
        logger.info("")
        
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
