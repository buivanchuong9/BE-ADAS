"""
Seed Demo Data for ADAS System
Tạo dữ liệu mẫu để demo cho thầy
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import Base, Camera, Driver, Trip, Detection, Event, Alert
import random

# Create tables
Base.metadata.create_all(bind=engine)

def seed_data():
    db = SessionLocal()
    
    try:
        print("🌱 Starting to seed demo data...")
        
        # Check if data already exists
        existing_detections = db.query(Detection).count()
        if existing_detections > 0:
            print(f"⚠️  Database already has {existing_detections} detections. Skipping seed.")
            return
        
        # 1. Create Cameras
        print("📹 Creating cameras...")
        cameras = [
            Camera(
                name="Camera Dashboard",
                type="dashboard",
                url="rtsp://camera1.local/stream",
                status="active",
                resolution="1920x1080",
                frame_rate=30
            ),
            Camera(
                name="Camera Rear",
                type="rear",
                url="rtsp://camera2.local/stream",
                status="active",
                resolution="1280x720",
                frame_rate=25
            )
        ]
        db.add_all(cameras)
        db.commit()
        print(f"✅ Created {len(cameras)} cameras")
        
        # 2. Create Drivers
        print("👤 Creating drivers...")
        drivers = [
            Driver(
                name="Nguyễn Văn A",
                license_number="79A-12345",
                email="nguyenvana@example.com",
                phone="0901234567",
                safety_score=95,
                total_trips=15,
                total_distance_km=450.5,
                status="active"
            ),
            Driver(
                name="Trần Thị B",
                license_number="79B-67890",
                email="tranthib@example.com",
                phone="0907654321",
                safety_score=88,
                total_trips=8,
                total_distance_km=230.2,
                status="active"
            )
        ]
        db.add_all(drivers)
        db.commit()
        print(f"✅ Created {len(drivers)} drivers")
        
        # 3. Create Trips
        print("🚗 Creating trips...")
        trips = []
        for i in range(10):
            start_time = datetime.now() - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23))
            end_time = start_time + timedelta(minutes=random.randint(15, 120))
            
            trip = Trip(
                driver_id=random.choice(drivers).id,
                camera_id=random.choice(cameras).id,
                start_time=start_time,
                end_time=end_time,
                distance_km=round(random.uniform(5.0, 50.0), 2),
                duration_minutes=round((end_time - start_time).total_seconds() / 60, 1),
                average_speed=random.randint(30, 80),
                max_speed=random.randint(60, 120),
                status="completed",
                total_events=random.randint(0, 5),
                critical_events=random.randint(0, 2)
            )
            trips.append(trip)
        
        db.add_all(trips)
        db.commit()
        print(f"✅ Created {len(trips)} trips")
        
        # 4. Create Detections (YOLOv11 detections)
        print("🎯 Creating detections...")
        classes = ["car", "truck", "bus", "motorcycle", "person", "bicycle", "traffic light", "stop sign"]
        detections = []
        
        for trip in trips:
            # Tạo 20-50 detections per trip
            num_detections = random.randint(20, 50)
            trip_duration = (trip.end_time - trip.start_time).total_seconds()
            
            for i in range(num_detections):
                detection_time = trip.start_time + timedelta(seconds=random.uniform(0, trip_duration))
                
                # Bounding box as JSON string
                bbox = {
                    "x1": random.randint(100, 800),
                    "y1": random.randint(50, 400),
                    "x2": random.randint(900, 1800),
                    "y2": random.randint(500, 1000)
                }
                
                detection = Detection(
                    trip_id=trip.id,
                    camera_id=trip.camera_id,
                    class_name=random.choice(classes),
                    confidence=round(random.uniform(0.65, 0.99), 3),
                    bounding_box=str(bbox),  # Store as string/JSON
                    distance_meters=round(random.uniform(5.0, 100.0), 2),
                    timestamp=detection_time
                )
                detections.append(detection)
        
        db.add_all(detections)
        db.commit()
        print(f"✅ Created {len(detections)} detections")
        
        # 5. Create Events
        print("⚠️  Creating events...")
        event_types = [
            ("lane_departure", "warning"),
            ("following_distance", "high"),
            ("speed_limit", "medium"),
            ("collision_warning", "critical"),
            ("hard_brake", "high")
        ]
        
        events = []
        for trip in trips[:7]:  # Events for some trips
            num_events = random.randint(1, 5)
            trip_duration = (trip.end_time - trip.start_time).total_seconds()
            
            for i in range(num_events):
                event_type, severity = random.choice(event_types)
                event_time = trip.start_time + timedelta(seconds=random.uniform(0, trip_duration))
                
                event = Event(
                    trip_id=trip.id,
                    camera_id=trip.camera_id,
                    driver_id=trip.driver_id,
                    event_type=event_type,
                    severity=severity,
                    timestamp=event_time,
                    description=f"{event_type.replace('_', ' ').title()} detected"
                )
                events.append(event)
        
        db.add_all(events)
        db.commit()
        print(f"✅ Created {len(events)} events")
        
        # 6. Create Alerts
        print("🔔 Creating alerts...")
        alerts = []
        for event in events:
            if event.severity in ["critical", "high"]:
                alert = Alert(
                    event_id=event.id,
                    severity=event.severity,
                    alert_type=event.event_type,
                    message=f"⚠️ {event.description}",
                    ttc=round(random.uniform(1.5, 5.0), 2) if "collision" in event.event_type else None,
                    distance=round(random.uniform(10.0, 50.0), 2),
                    relative_speed=round(random.uniform(-20.0, 20.0), 2),
                    played=random.choice([True, False]),
                    created_at=event.timestamp
                )
                alerts.append(alert)
        
        db.add_all(alerts)
        db.commit()
        print(f"✅ Created {len(alerts)} alerts")
        
        # Summary
        print("\n" + "="*50)
        print("✨ SEED DATA SUMMARY:")
        print("="*50)
        print(f"📹 Cameras: {len(cameras)}")
        print(f"👤 Drivers: {len(drivers)}")
        print(f"🚗 Trips: {len(trips)}")
        print(f"🎯 Detections: {len(detections)}")
        print(f"⚠️  Events: {len(events)}")
        print(f"🔔 Alerts: {len(alerts)}")
        print("="*50)
        print("✅ Demo data seeded successfully!")
        print("\nGiờ có thể test API với Postman:")
        print("  GET http://localhost:52000/api/analytics/dashboard")
        print("  GET http://localhost:52000/api/detections/stats")
        print("  GET http://localhost:52000/api/detections/recent?limit=20")
        
    except Exception as e:
        print(f"❌ Error seeding data: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
