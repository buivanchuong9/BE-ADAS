"""
Seed Data Script
================
Populates database with initial test data.

Usage:
    python backend/scripts/seed_data.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import async_session_maker
from app.db.models import User, Vehicle, ModelVersion
from app.db.models.user import UserRole
from app.core.security import get_password_hash
from app.core.logging import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


async def seed_users(session):
    """Create initial users"""
    logger.info("Seeding users...")
    
    users_data = [
        {
            "username": "admin",
            "email": "admin@adas.com",
            "password": "Admin123!@#",
            "role": "admin",
            "full_name": "System Administrator",
        },
        {
            "username": "analyst",
            "email": "analyst@adas.com",
            "password": "analyst123",
            "role": "analyst",
            "full_name": "Data Analyst",
        },
        {
            "username": "driver1",
            "email": "driver1@adas.com",
            "password": "driver123",
            "role": "driver",
            "full_name": "Nguyễn Văn A",
        },
    ]
    
    for user_data in users_data:
        password = user_data.pop("password")
        user = User(
            **user_data,
            hashed_password=get_password_hash(password),
            is_active=1,
        )
        session.add(user)
    
    await session.commit()
    logger.info(f"  ✓ Created {len(users_data)} users")


async def seed_vehicles(session):
    """Create test vehicles"""
    logger.info("Seeding vehicles...")
    
    # Get driver user
    from sqlalchemy import select
    result = await session.execute(
        select(User).where(User.username == "driver1")
    )
    driver = result.scalar_one_or_none()
    
    if not driver:
        logger.warning("  ⚠ Driver user not found, skipping vehicles")
        return
    
    vehicles_data = [
        {
            "license_plate": "29A-12345",
            "vehicle_type": "car",
            "manufacturer": "Toyota",
            "model": "Camry",
            "year": 2023,
            "owner_id": driver.id,
        },
        {
            "license_plate": "30B-67890",
            "vehicle_type": "car",
            "manufacturer": "Honda",
            "model": "Civic",
            "year": 2023,
            "owner_id": driver.id,
        },
    ]
    
    for vehicle_data in vehicles_data:
        vehicle = Vehicle(**vehicle_data)
        session.add(vehicle)
    
    await session.commit()
    logger.info(f"  ✓ Created {len(vehicles_data)} vehicles")


async def seed_model_versions(session):
    """Create AI model version records"""
    logger.info("Seeding AI model versions...")
    
    models_data = [
        {
            "model_name": "YOLOv11",
            "model_type": "OBJECT_DETECTION",
            "version": "v11.0",
            "file_path": "models/yolov11n.pt",
            "is_active": 1,
            "description": "YOLOv11 nano for object detection",
        },
        {
            "model_name": "MediaPipe",
            "model_type": "FACE_MESH",
            "version": "v0.10.14",
            "file_path": "models/mediapipe",
            "is_active": 1,
            "description": "MediaPipe for driver monitoring",
        },
        {
            "model_name": "LaneNet",
            "model_type": "LANE_DETECTION",
            "version": "v1.0",
            "file_path": "models/lanenet",
            "is_active": 1,
            "description": "Custom lane detection model",
        },
    ]
    
    for model_data in models_data:
        model = ModelVersion(**model_data)
        session.add(model)
    
    await session.commit()
    logger.info(f"  ✓ Created {len(models_data)} model versions")


async def main():
    """Main seed function"""
    logger.info("=" * 80)
    logger.info("ADAS Database Seeding")
    logger.info("=" * 80)
    
    async with async_session_maker() as session:
        try:
            await seed_users(session)
            await seed_vehicles(session)
            await seed_model_versions(session)
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("Database seeding complete!")
            logger.info("=" * 80)
            logger.info("")
            logger.info("Test credentials:")
            logger.info("  Admin:   admin / admin123")
            logger.info("  Analyst: analyst / analyst123")
            logger.info("  Driver:  driver1 / driver123")
            logger.info("")
            
        except Exception as e:
            logger.error(f"✗ Seeding failed: {e}")
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(main())
