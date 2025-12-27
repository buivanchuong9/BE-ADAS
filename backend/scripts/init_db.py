"""
Database Initialization Script
===============================
Creates database schema and seeds initial data.

Usage:
    python backend/scripts/init_db.py
"""

import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import sync_engine
from app.db.base import Base
from app.core.config import settings
from app.core.logging import setup_logging, get_logger

# Import all models to register them
from app.db.models.user import User
from app.db.models.vehicle import Vehicle
from app.db.models.trip import Trip
from app.db.models.video_job import VideoJob
from app.db.models.safety_event import SafetyEvent
from app.db.models.driver_state import DriverState
from app.db.models.traffic_sign import TrafficSign
from app.db.models.alert import Alert
from app.db.models.model_version import ModelVersion

setup_logging()
logger = get_logger(__name__)


def main():
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
        Base.metadata.create_all(sync_engine)
        logger.info("✓ Database tables created successfully")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("Database initialization complete!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Run seed script: python backend/scripts/seed_data.py")
        logger.info("")
        
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
        raise


if __name__ == "__main__":
    main()
