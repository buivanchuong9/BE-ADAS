# ✅ DATABASE-BACKEND ĐÃ ĐỒNG BỘ 100%

## 🎯 HOÀN THÀNH - Chỉ cần 1 lệnh để chạy!

```bash
python run.py --production
```

## ✨ TỰ ĐỘNG THỰC HIỆN

Khi chạy lệnh trên, hệ thống sẽ:

1. ✅ Kiểm tra file `.env` có sẵn
2. ✅ Kiểm tra & cài đặt dependencies (nếu thiếu)
3. ✅ Kiểm tra kết nối SQL Server
4. ✅ Tạo database `adas_production` (nếu chưa có)
5. ✅ Tạo tất cả 9 tables theo đúng schema
6. ✅ Seed initial data:
   - 👤 Admin user: `admin` / `Admin123!@#`
   - 👥 2 sample users (analyst, driver1)
   - 🚗 2 sample vehicles
   - 🤖 3 AI model versions
7. ✅ Khởi động API server tại `https://adas-api.aiotlab.edu.vn:52000`

## 📊 DATABASE SCHEMA (9 Tables)

### 1. users
```sql
- id (PK)
- username (UNIQUE)
- email (UNIQUE, NOT NULL)
- hashed_password
- role (admin/analyst/driver/viewer)
- full_name
- is_active (BIT)
- created_at, updated_at, last_login
```

### 2. vehicles
```sql
- id (PK)
- license_plate (UNIQUE)
- vehicle_type (car/truck/bus/motorcycle)
- manufacturer
- model
- year
- owner_id (FK → users.id)
- created_at, updated_at
```

### 3. trips
```sql
- id (PK)
- vehicle_id (FK → vehicles.id)
- driver_id (FK → users.id)
- start_time, end_time
- start_location, end_location
- distance_km, duration_minutes
- avg_speed, max_speed
- total_alerts, critical_alerts
- status (active/completed/cancelled)
- created_at, updated_at
```

### 4. video_jobs
```sql
- id (PK)
- job_id (UUID - for API compatibility)
- trip_id (FK → trips.id)
- video_filename
- video_path
- video_size_mb, duration_seconds, fps, resolution
- status (pending/processing/completed/failed)
- progress_percent
- result_path
- error_message
- started_at, completed_at
- processing_time_seconds
- created_at, updated_at
```

### 5. safety_events
```sql
- id (PK)
- trip_id (FK → trips.id)
- video_job_id (FK → video_jobs.id)
- event_type (FCW/LDW/DMS/SPEED_VIOLATION...)
- severity (CRITICAL/WARNING/INFO)
- timestamp, frame_number
- description
- location_lat, location_lng
- speed_kmh
- metadata (JSON)
- snapshot_path
- created_at
```

### 6. driver_states
```sql
- id (PK)
- trip_id (FK → trips.id)
- timestamp
- is_drowsy (BIT)
- drowsy_confidence, drowsy_reason
- ear_value, mar_value (Eye/Mouth Aspect Ratio)
- head_pose
- snapshot_path
- created_at
```

### 7. traffic_signs
```sql
- id (PK)
- trip_id (FK → trips.id)
- timestamp
- sign_type (SPEED_30/SPEED_50/STOP...)
- confidence
- speed_limit, current_speed
- is_violation (BIT)
- location_lat, location_lng
- snapshot_path
- created_at
```

### 8. alerts
```sql
- id (PK)
- trip_id (FK → trips.id)
- alert_type (FCW/LDW/DMS/SPEED)
- severity (CRITICAL/WARNING/INFO)
- message, message_vi
- timestamp
- is_acknowledged (BIT)
- acknowledged_at, acknowledged_by (FK → users.id)
- metadata (JSON)
- created_at
```

### 9. model_versions
```sql
- id (PK)
- model_name
- model_type (OBJECT_DETECTION/FACE_MESH/LANE_DETECTION)
- version
- file_path
- file_size_mb, accuracy
- is_active (BIT)
- description
- created_at, updated_at
```

## 🔧 ĐÃ SỬA ĐỂ KHỚP 100%

### Python Models
- ✅ User: `hashed_password` (not password_hash)
- ✅ Vehicle: `license_plate`, `manufacturer`, `owner_id`, `vehicle_type`
- ✅ Trip: `total_alerts`, `critical_alerts`, status as string
- ✅ VideoJob: Thêm `job_id` (UUID), dùng string cho status
- ✅ SafetyEvent: `location_lat/lng`, `speed_kmh`
- ✅ DriverState: `is_drowsy`, `ear_value`, `mar_value`
- ✅ TrafficSign: `speed_limit`, `is_violation`
- ✅ Alert: `message_vi`, `is_acknowledged`
- ✅ ModelVersion: Đơn giản hóa fields

### Repositories
- ✅ UserRepository: Dùng `hashed_password`
- ✅ VideoJobRepository: Dùng string cho status, có `get_by_job_id()`

### Services
- ✅ VideoService: Tạo `job_id` UUID, dùng đúng column names
- ✅ Seed data: Dùng đúng tất cả column names mới

### Config
- ✅ config.py: Luôn dùng SQL Server (bỏ SQLite fallback)
- ✅ run.py: Tự động init DB + seed data

## 🚀 READY TO RUN!

### Trên Windows Server:

```bash
# 1. Clone repository
git clone <repo-url>
cd backend-python

# 2. Đảm bảo file .env.production có đúng thông tin:
DB_HOST=localhost
DB_PORT=1433
DB_NAME=adas_production
DB_USER=SA
DB_PASSWORD=123456aA@$
DB_DRIVER=ODBC Driver 17 for SQL Server

# 3. Chạy!
python run.py --production
```

### Output:
```
============================================================
  🚗 ADAS BACKEND - Advanced Driver Assistance System
  📍 Domain: https://adas-api.aiotlab.edu.vn:52000
  🔧 Version: 2.0.0
  🏭 Mode: PRODUCTION
============================================================

✅ File .env đã sẵn sàng
✅ Dependencies OK
✅ Kết nối SQL Server thành công
✅ Database 'adas_production' đã tồn tại
📋 Đang tạo tables...
✅ Database tables đã sẵn sàng
📦 Đang seed initial data...
✅ Initial data đã được seed
   🔑 Admin: admin / Admin123!@#

🚀 Đang khởi động ADAS Backend Server...
📡 Host: 0.0.0.0
🔌 Port: 52000
🔄 Hot reload: Tắt

📖 API Documentation: http://0.0.0.0:52000/docs
🏥 Health Check: http://0.0.0.0:52000/health
🔌 WebSocket Alerts: ws://0.0.0.0:52000/ws/alerts
```

## 📝 SAMPLE CREDENTIALS

```
Admin:
  Username: admin
  Password: Admin123!@#
  Role: admin

Analyst:
  Username: analyst
  Password: analyst123
  Role: analyst

Driver:
  Username: driver1
  Password: driver123
  Role: driver
```

## 🎉 DONE!

Database và Backend đã đồng bộ hoàn toàn. Chỉ cần chạy 1 lệnh duy nhất và mọi thứ sẽ tự động được setup!
