-- ================================================
-- ADAS BACKEND - SQL SERVER SCHEMA
-- Chạy script này để tạo database hoàn chỉnh
-- ================================================

USE master;
GO

-- Tạo database
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'adas_production')
BEGIN
    CREATE DATABASE adas_production;
    PRINT 'Database adas_production created successfully';
END
ELSE
BEGIN
    PRINT 'Database adas_production already exists';
END
GO

USE adas_production;
GO

-- ================================================
-- TABLE 1: Users (Người dùng)
-- ================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'users')
BEGIN
    CREATE TABLE users (
        id INT IDENTITY(1,1) PRIMARY KEY,
        username NVARCHAR(50) NOT NULL UNIQUE,
        email NVARCHAR(255) NOT NULL UNIQUE,
        hashed_password NVARCHAR(255) NOT NULL,
        full_name NVARCHAR(255),
        role NVARCHAR(20) NOT NULL DEFAULT 'viewer', -- admin, operator, viewer, driver
        is_active BIT NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL DEFAULT GETDATE(),
        updated_at DATETIME NOT NULL DEFAULT GETDATE(),
        last_login DATETIME
    );
    PRINT 'Table users created';
END
GO

-- ================================================
-- TABLE 2: Vehicles (Xe)
-- ================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'vehicles')
BEGIN
    CREATE TABLE vehicles (
        id INT IDENTITY(1,1) PRIMARY KEY,
        license_plate NVARCHAR(20) NOT NULL UNIQUE,
        vehicle_type NVARCHAR(50), -- car, truck, bus, motorcycle
        manufacturer NVARCHAR(100),
        model NVARCHAR(100),
        year INT,
        owner_id INT FOREIGN KEY REFERENCES users(id) ON DELETE SET NULL,
        created_at DATETIME NOT NULL DEFAULT GETDATE(),
        updated_at DATETIME NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table vehicles created';
END
GO

-- ================================================
-- TABLE 3: Trips (Chuyến đi)
-- ================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'trips')
BEGIN
    CREATE TABLE trips (
        id INT IDENTITY(1,1) PRIMARY KEY,
        vehicle_id INT NOT NULL FOREIGN KEY REFERENCES vehicles(id) ON DELETE CASCADE,
        driver_id INT FOREIGN KEY REFERENCES users(id) ON DELETE SET NULL,
        start_time DATETIME NOT NULL DEFAULT GETDATE(),
        end_time DATETIME,
        start_location NVARCHAR(255),
        end_location NVARCHAR(255),
        distance_km FLOAT,
        duration_minutes INT,
        avg_speed FLOAT,
        max_speed FLOAT,
        total_alerts INT DEFAULT 0,
        critical_alerts INT DEFAULT 0,
        status NVARCHAR(20) DEFAULT 'active', -- active, completed, cancelled
        created_at DATETIME NOT NULL DEFAULT GETDATE(),
        updated_at DATETIME NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table trips created';
END
GO

-- ================================================
-- TABLE 4: Video Jobs (Jobs xử lý video)
-- ================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'video_jobs')
BEGIN
    CREATE TABLE video_jobs (
        id INT IDENTITY(1,1) PRIMARY KEY,
        job_id NVARCHAR(36) UNIQUE NULL,  -- UUID for API compatibility
        trip_id INT FOREIGN KEY REFERENCES trips(id) ON DELETE SET NULL,
        video_filename NVARCHAR(255) NOT NULL,
        video_path NVARCHAR(500) NOT NULL,
        video_size_mb FLOAT,
        duration_seconds INT,
        fps FLOAT,
        resolution NVARCHAR(50), -- e.g., 1920x1080
        status NVARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, processing, completed, failed
        progress_percent INT DEFAULT 0,
        result_path NVARCHAR(500),
        error_message NVARCHAR(MAX),
        started_at DATETIME,
        completed_at DATETIME,
        processing_time_seconds INT,
        created_at DATETIME NOT NULL DEFAULT GETDATE(),
        updated_at DATETIME NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table video_jobs created';
END
GO

-- ================================================
-- TABLE 5: Safety Events (Sự kiện an toàn)
-- ================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'safety_events')
BEGIN
    CREATE TABLE safety_events (
        id INT IDENTITY(1,1) PRIMARY KEY,
        trip_id INT FOREIGN KEY REFERENCES trips(id) ON DELETE CASCADE,
        video_job_id INT FOREIGN KEY REFERENCES video_jobs(id) ON DELETE SET NULL,
        event_type NVARCHAR(50) NOT NULL, -- FCW, LDW, DMS, SPEED_VIOLATION, etc.
        severity NVARCHAR(20) NOT NULL, -- CRITICAL, WARNING, INFO
        timestamp DATETIME NOT NULL,
        frame_number INT,
        description NVARCHAR(MAX),
        location_lat FLOAT,
        location_lng FLOAT,
        speed_kmh FLOAT,
        meta_data NVARCHAR(MAX), -- JSON data
        snapshot_path NVARCHAR(500),
        created_at DATETIME NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table safety_events created';
END
GO

-- ================================================
-- TABLE 6: Driver States (Trạng thái tài xế)
-- ================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'driver_states')
BEGIN
    CREATE TABLE driver_states (
        id INT IDENTITY(1,1) PRIMARY KEY,
        trip_id INT FOREIGN KEY REFERENCES trips(id) ON DELETE CASCADE,
        timestamp DATETIME NOT NULL,
        is_drowsy BIT NOT NULL DEFAULT 0,
        drowsy_confidence FLOAT,
        drowsy_reason NVARCHAR(50), -- EYE_CLOSED, YAWNING, HEAD_TILT
        ear_value FLOAT, -- Eye Aspect Ratio
        mar_value FLOAT, -- Mouth Aspect Ratio
        head_pose NVARCHAR(100),
        snapshot_path NVARCHAR(500),
        created_at DATETIME NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table driver_states created';
END
GO

-- ================================================
-- TABLE 7: Traffic Signs (Biển báo giao thông)
-- ================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'traffic_signs')
BEGIN
    CREATE TABLE traffic_signs (
        id INT IDENTITY(1,1) PRIMARY KEY,
        trip_id INT FOREIGN KEY REFERENCES trips(id) ON DELETE CASCADE,
        timestamp DATETIME NOT NULL,
        sign_type NVARCHAR(50) NOT NULL, -- SPEED_30, SPEED_50, STOP, etc.
        confidence FLOAT NOT NULL,
        speed_limit INT, -- For speed limit signs
        current_speed FLOAT,
        is_violation BIT DEFAULT 0,
        location_lat FLOAT,
        location_lng FLOAT,
        snapshot_path NVARCHAR(500),
        created_at DATETIME NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table traffic_signs created';
END
GO

-- ================================================
-- TABLE 8: Alerts (Cảnh báo)
-- ================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'alerts')
BEGIN
    CREATE TABLE alerts (
        id INT IDENTITY(1,1) PRIMARY KEY,
        trip_id INT FOREIGN KEY REFERENCES trips(id) ON DELETE CASCADE,
        alert_type NVARCHAR(50) NOT NULL, -- FCW, LDW, DMS, SPEED
        severity NVARCHAR(20) NOT NULL, -- CRITICAL, WARNING, INFO
        message NVARCHAR(255) NOT NULL,
        message_vi NVARCHAR(255), -- Vietnamese message
        timestamp DATETIME NOT NULL,
        is_acknowledged BIT DEFAULT 0,
        acknowledged_at DATETIME,
        acknowledged_by INT FOREIGN KEY REFERENCES users(id) ON DELETE SET NULL,
        meta_data NVARCHAR(MAX), -- JSON data
        created_at DATETIME NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table alerts created';
END
GO

-- ================================================
-- TABLE 9: Model Versions (Phiên bản model AI)
-- ================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'model_versions')
BEGIN
    CREATE TABLE model_versions (
        id INT IDENTITY(1,1) PRIMARY KEY,
        model_name NVARCHAR(100) NOT NULL,
        model_type NVARCHAR(50) NOT NULL, -- YOLO, MEDIAPIPE, LANE, etc.
        version NVARCHAR(50) NOT NULL,
        file_path NVARCHAR(500) NOT NULL,
        file_size_mb FLOAT,
        accuracy FLOAT,
        is_active BIT DEFAULT 1,
        description NVARCHAR(MAX),
        created_at DATETIME NOT NULL DEFAULT GETDATE(),
        updated_at DATETIME NOT NULL DEFAULT GETDATE(),
        UNIQUE(model_name, version)
    );
    PRINT 'Table model_versions created';
END
GO

-- ================================================
-- INDEXES (Tăng tốc query)
-- ================================================
PRINT 'Creating indexes...';

-- Users
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- Vehicles
CREATE INDEX idx_vehicles_license_plate ON vehicles(license_plate);
CREATE INDEX idx_vehicles_owner_id ON vehicles(owner_id);

-- Trips
CREATE INDEX idx_trips_vehicle_id ON trips(vehicle_id);
CREATE INDEX idx_trips_driver_id ON trips(driver_id);
CREATE INDEX idx_trips_start_time ON trips(start_time);
CREATE INDEX idx_trips_status ON trips(status);

-- Video Jobs
CREATE INDEX idx_video_jobs_job_id ON video_jobs(job_id);
CREATE INDEX idx_video_jobs_trip_id ON video_jobs(trip_id);
CREATE INDEX idx_video_jobs_status ON video_jobs(status);
CREATE INDEX idx_video_jobs_created_at ON video_jobs(created_at);

-- Safety Events
CREATE INDEX idx_safety_events_trip_id ON safety_events(trip_id);
CREATE INDEX idx_safety_events_event_type ON safety_events(event_type);
CREATE INDEX idx_safety_events_severity ON safety_events(severity);
CREATE INDEX idx_safety_events_timestamp ON safety_events(timestamp);

-- Alerts
CREATE INDEX idx_alerts_trip_id ON alerts(trip_id);
CREATE INDEX idx_alerts_alert_type ON alerts(alert_type);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_timestamp ON alerts(timestamp);

PRINT 'Indexes created successfully';

-- ================================================
-- SAMPLE DATA (Dữ liệu mẫu)
-- ================================================
PRINT 'Inserting sample data...';

-- Admin user (password: Admin123!@#)
IF NOT EXISTS (SELECT * FROM users WHERE username = 'admin')
BEGIN
    INSERT INTO users (username, email, hashed_password, full_name, role, is_active)
    VALUES ('admin', 'admin@adas.vn', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5sPNw/OkTw1D6', 'Administrator', 'admin', 1);
    PRINT 'Admin user created';
END

-- Sample vehicle
IF NOT EXISTS (SELECT * FROM vehicles WHERE license_plate = '29A-12345')
BEGIN
    INSERT INTO vehicles (license_plate, vehicle_type, manufacturer, model, year, owner_id)
    VALUES ('29A-12345', 'car', 'Toyota', 'Camry', 2023, 1);
    PRINT 'Sample vehicle created';
END

-- Sample model versions
IF NOT EXISTS (SELECT * FROM model_versions WHERE model_name = 'YOLOv11')
BEGIN
    INSERT INTO model_versions (model_name, model_type, version, file_path, is_active, description)
    VALUES 
    ('YOLOv11', 'OBJECT_DETECTION', 'v11.0', 'models/yolov11n.pt', 1, 'YOLOv11 nano for object detection'),
    ('MediaPipe', 'FACE_MESH', 'v0.10.14', 'models/mediapipe', 1, 'MediaPipe for driver monitoring'),
    ('LaneNet', 'LANE_DETECTION', 'v1.0', 'models/lanenet', 1, 'Custom lane detection model');
    PRINT 'Sample models created';
END

PRINT 'Sample data inserted successfully';

-- ================================================
-- COMPLETION
-- ================================================
PRINT '';
PRINT '========================================';
PRINT '✅ Database schema created successfully!';
PRINT '========================================';
PRINT 'Database: adas_production';
PRINT 'Tables created: 9';
PRINT 'Sample admin user: admin / Admin123!@#';
PRINT '';
PRINT 'Next steps:';
PRINT '1. Update .env file with database credentials';
PRINT '2. Run: python run.py --production';
PRINT '========================================';
GO
