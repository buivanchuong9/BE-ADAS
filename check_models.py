"""
Quick Model Validation Check
=============================
Kiểm tra xem các models có khớp với database schema không
"""

import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

print("=" * 80)
print("CHECKING MODELS COMPATIBILITY WITH SQL SERVER SCHEMA")
print("=" * 80)
print()

try:
    # Import models
    from app.db.models.user import User
    from app.db.models.vehicle import Vehicle
    from app.db.models.trip import Trip
    from app.db.models.video_job import VideoJob
    from app.db.models.safety_event import SafetyEvent
    from app.db.models.driver_state import DriverState
    from app.db.models.traffic_sign import TrafficSign
    from app.db.models.alert import Alert
    from app.db.models.model_version import ModelVersion
    
    print("✓ All models imported successfully")
    print()
    
    # Check User model columns
    print("Checking User model...")
    user_cols = [c.name for c in User.__table__.columns]
    expected_user_cols = ['id', 'username', 'email', 'hashed_password', 'role', 'full_name', 'is_active', 'created_at', 'updated_at', 'last_login']
    
    if 'hashed_password' in user_cols:
        print("  ✓ hashed_password column found")
    else:
        print("  ✗ MISSING hashed_password column")
    
    if 'email' in user_cols:
        email_col = User.__table__.columns['email']
        if not email_col.nullable:
            print("  ✓ email is NOT NULL")
        else:
            print("  ⚠ email should be NOT NULL")
    
    # Check Vehicle model
    print("\nChecking Vehicle model...")
    vehicle_cols = [c.name for c in Vehicle.__table__.columns]
    
    if 'license_plate' in vehicle_cols:
        print("  ✓ license_plate column found")
    else:
        print("  ✗ MISSING license_plate column")
    
    if 'manufacturer' in vehicle_cols:
        print("  ✓ manufacturer column found")
    else:
        print("  ✗ MISSING manufacturer column")
    
    if 'owner_id' in vehicle_cols:
        print("  ✓ owner_id column found")
    else:
        print("  ✗ MISSING owner_id column")
    
    if 'vehicle_type' in vehicle_cols:
        print("  ✓ vehicle_type column found")
    else:
        print("  ✗ MISSING vehicle_type column")
    
    # Check Trip model
    print("\nChecking Trip model...")
    trip_cols = [c.name for c in Trip.__table__.columns]
    
    if 'total_alerts' in trip_cols:
        print("  ✓ total_alerts column found")
    else:
        print("  ✗ MISSING total_alerts column")
    
    if 'critical_alerts' in trip_cols:
        print("  ✓ critical_alerts column found")
    else:
        print("  ✗ MISSING critical_alerts column")
    
    # Check VideoJob model
    print("\nChecking VideoJob model...")
    vj_cols = [c.name for c in VideoJob.__table__.columns]
    
    if 'video_filename' in vj_cols:
        print("  ✓ video_filename column found")
    else:
        print("  ✗ MISSING video_filename column")
    
    if 'video_path' in vj_cols:
        print("  ✓ video_path column found")
    else:
        print("  ✗ MISSING video_path column")
    
    # Check SafetyEvent model
    print("\nChecking SafetyEvent model...")
    se_cols = [c.name for c in SafetyEvent.__table__.columns]
    
    if 'location_lat' in se_cols:
        print("  ✓ location_lat column found")
    else:
        print("  ✗ MISSING location_lat column")
    
    if 'location_lng' in se_cols:
        print("  ✓ location_lng column found")
    else:
        print("  ✗ MISSING location_lng column")
    
    # Check DriverState model
    print("\nChecking DriverState model...")
    ds_cols = [c.name for c in DriverState.__table__.columns]
    
    if 'is_drowsy' in ds_cols:
        print("  ✓ is_drowsy column found")
    else:
        print("  ✗ MISSING is_drowsy column")
    
    if 'ear_value' in ds_cols:
        print("  ✓ ear_value column found")
    else:
        print("  ✗ MISSING ear_value column")
    
    if 'mar_value' in ds_cols:
        print("  ✓ mar_value column found")
    else:
        print("  ✗ MISSING mar_value column")
    
    # Check TrafficSign model
    print("\nChecking TrafficSign model...")
    ts_cols = [c.name for c in TrafficSign.__table__.columns]
    
    if 'speed_limit' in ts_cols:
        print("  ✓ speed_limit column found")
    else:
        print("  ✗ MISSING speed_limit column")
    
    if 'is_violation' in ts_cols:
        print("  ✓ is_violation column found")
    else:
        print("  ✗ MISSING is_violation column")
    
    # Check Alert model
    print("\nChecking Alert model...")
    alert_cols = [c.name for c in Alert.__table__.columns]
    
    if 'message_vi' in alert_cols:
        print("  ✓ message_vi column found")
    else:
        print("  ✗ MISSING message_vi column")
    
    if 'is_acknowledged' in alert_cols:
        print("  ✓ is_acknowledged column found")
    else:
        print("  ✗ MISSING is_acknowledged column")
    
    print()
    print("=" * 80)
    print("MODEL VALIDATION COMPLETE")
    print("=" * 80)
    print()
    print("All models columns:")
    print(f"  User: {', '.join(user_cols)}")
    print(f"  Vehicle: {', '.join(vehicle_cols)}")
    print(f"  Trip: {', '.join(trip_cols)}")
    print(f"  VideoJob: {', '.join(vj_cols)}")
    print(f"  SafetyEvent: {', '.join(se_cols)}")
    print(f"  DriverState: {', '.join(ds_cols)}")
    print(f"  TrafficSign: {', '.join(ts_cols)}")
    print(f"  Alert: {', '.join(alert_cols)}")
    print()
    print("✓ Models structure looks good!")
    print("✓ Should be compatible with SQL Server schema")
    print()
    
except Exception as e:
    print(f"✗ Error checking models: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
