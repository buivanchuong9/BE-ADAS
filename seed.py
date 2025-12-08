# Seed initial data for ADAS database

from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import Base, Camera, AIModel, Driver
from datetime import datetime

def seed_cameras(db: Session):
    """Seed initial cameras"""
    cameras = [
        Camera(
            name="Web Camera (máy tính)",
            type="webcam",
            status="ready",
            resolution="1280x720",
            frame_rate=30,
            instructions="Sử dụng webcam tích hợp hoặc USB camera của máy tính",
            created_at=datetime.utcnow()
        ),
        Camera(
            name="Smartphone (RTMP Stream)",
            type="smartphone",
            status="disconnected",
            url="rtmp://localhost:1935/live",
            instructions="1. Cài app IP Camera trên điện thoại\n2. Nhập URL: rtmp://[YOUR_PC_IP]:1935/live\n3. Bắt đầu phát",
            created_at=datetime.utcnow()
        ),
        Camera(
            name="Smartphone (WebRTC)",
            type="smartphone",
            status="disconnected",
            url="ws://localhost:8000/ws/camera",
            instructions="1. Cài app WebRTC cho điện thoại\n2. Kết nối tới: ws://[YOUR_PC_IP]:8000/ws/camera",
            created_at=datetime.utcnow()
        ),
        Camera(
            name="IP Camera",
            type="ip-camera",
            status="disconnected",
            url="rtsp://192.168.1.100:554/stream",
            instructions="1. Nhập URL RTSP/RTMP của camera IP\n2. Ví dụ: rtsp://192.168.1.100:554/stream",
            created_at=datetime.utcnow()
        )
    ]
    
    db.bulk_save_objects(cameras)
    db.commit()
    print("✅ Seeded cameras")

def seed_ai_models(db: Session):
    """Seed AI models"""
    models = [
        AIModel(
            model_id="yolo11n",
            name="YOLOv11 Nano",
            size="5.4 MB",
            downloaded=True,
            accuracy=82.1,
            url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
            version="11.0",
            description="Model nhẹ nhất YOLOv11, nhanh hơn v8 15%",
            is_active=True,
            created_at=datetime.utcnow()
        ),
        AIModel(
            model_id="yolo11s",
            name="YOLOv11 Small",
            size="21.5 MB",
            downloaded=False,
            accuracy=88.3,
            url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt",
            version="11.0",
            description="Cân bằng tốc độ và độ chính xác",
            is_active=False,
            created_at=datetime.utcnow()
        ),
        AIModel(
            model_id="yolo11m",
            name="YOLOv11 Medium",
            size="47.8 MB",
            downloaded=False,
            accuracy=90.1,
            url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt",
            version="11.0",
            description="Độ chính xác cao, yêu cầu GPU",
            is_active=False,
            created_at=datetime.utcnow()
        ),
        AIModel(
            model_id="yolo11l",
            name="YOLOv11 Large",
            size="96.5 MB",
            downloaded=False,
            accuracy=91.8,
            url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11l.pt",
            version="11.0",
            description="YOLOv11 Large - độ chính xác rất cao",
            is_active=False,
            created_at=datetime.utcnow()
        )
    ]
    
    db.bulk_save_objects(models)
    db.commit()
    print("✅ Seeded AI models")

def seed_demo_driver(db: Session):
    """Seed demo driver"""
    driver = Driver(
        name="Demo Driver",
        email="demo@adas.com",
        phone="0123456789",
        license_number="DL-001",
        safety_score=85,
        status="active",
        total_trips=0,
        total_distance_km=0,
        created_at=datetime.utcnow()
    )
    
    db.add(driver)
    db.commit()
    print("✅ Seeded demo driver")

def seed_all():
    """Seed all initial data"""
    print("=" * 50)
    print("🌱 Seeding database...")
    print("=" * 50)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    print("✅ Created tables")
    
    # Create session
    db = SessionLocal()
    
    try:
        # Check if already seeded
        if db.query(Camera).count() > 0:
            print("⚠️  Database already seeded. Skipping...")
            return
        
        # Seed data
        seed_cameras(db)
        seed_ai_models(db)
        seed_demo_driver(db)
        
        print("=" * 50)
        print("✅ Database seeded successfully!")
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ Seeding failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_all()
