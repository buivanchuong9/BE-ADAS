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
            "password": "admin123",
            "role": UserRole.ADMIN,
            "full_name": "System Administrator",
        },
        {
            "username": "analyst",
            "email": "analyst@adas.com",
            "password": "analyst123",
            "role": UserRole.ANALYST,
            "full_name": "Data Analyst",
        },
        {
            "username": "driver1",
            "email": "driver1@adas.com",
            "password": "driver123",
            "role": UserRole.DRIVER,
            "full_name": "Nguyễn Văn A",
            "phone": "0901234567",
        },
    ]
    
    for user_data in users_data:
        password = user_data.pop("password")
        user = User(
            **user_data,
            password_hash=get_password_hash(password),
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
            "plate_number": "29A-12345",
            "make": "Toyota",
            "model": "Camry",
            "year": 2022,
            "color": "Trắng",
            "user_id": driver.id,
        },
        {
            "plate_number": "30B-67890",
            "make": "Honda",
            "model": "Civic",
            "year": 2023,
            "color": "Đen",
            "user_id": driver.id,
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
            "model_name": "yolo11n",
            "version": "11.0.0",
            "model_type": "detection",
            "framework": "pytorch",
            "architecture": "YOLOv11",
            "file_path": "./models/yolo11n.pt",
            "is_active": 1,
            "is_production": 1,
            "description": "YOLOv11 Nano - Object detection for vehicles, pedestrians",
            "inference_time_ms": 15.0,
        },
        {
            "model_name": "lane_detector",
            "version": "1.0.0",
            "model_type": "segmentation",
            "framework": "opencv",
            "architecture": "Classical CV",
            "is_active": 1,
            "is_production": 1,
            "description": "Classical computer vision lane detection",
        },
        {
            "model_name": "driver_monitor",
            "version": "1.0.0",
            "model_type": "detection",
            "framework": "mediapipe",
            "architecture": "Face Mesh",
            "is_active": 1,
            "is_production": 1,
            "description": "MediaPipe Face Mesh for driver monitoring",
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
