-- ================================================
-- ADAS v3.0 - PostgreSQL Schema
-- Optimized for: Job Queue, Video Deduplication, JSONB metadata
-- ================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ================================================
-- TABLE 1: Users
-- ================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- ================================================
-- TABLE 2: Vehicles
-- ================================================
CREATE TABLE IF NOT EXISTS vehicles (
    id SERIAL PRIMARY KEY,
    license_plate VARCHAR(20) NOT NULL UNIQUE,
    vehicle_type VARCHAR(50),
    manufacturer VARCHAR(100),
    model VARCHAR(100),
    year INT,
    owner_id INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vehicles_owner ON vehicles(owner_id);

-- ================================================
-- TABLE 3: Videos (with SHA256 deduplication)
-- ================================================
CREATE TABLE IF NOT EXISTS videos (
    id SERIAL PRIMARY KEY,
    sha256_hash VARCHAR(64) UNIQUE NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(500) NOT NULL,
    size_bytes BIGINT NOT NULL,
    duration_seconds REAL,
    fps REAL,
    resolution VARCHAR(20),
    upload_count INT DEFAULT 1,
    uploader_id INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_videos_hash ON videos(sha256_hash);
CREATE INDEX IF NOT EXISTS idx_videos_uploader ON videos(uploader_id);

-- ================================================
-- TABLE 4: Trips
-- ================================================
CREATE TABLE IF NOT EXISTS trips (
    id SERIAL PRIMARY KEY,
    vehicle_id INT NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    driver_id INT REFERENCES users(id) ON DELETE SET NULL,
    start_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time TIMESTAMPTZ,
    start_location VARCHAR(255),
    end_location VARCHAR(255),
    distance_km REAL,
    duration_minutes INT,
    avg_speed REAL,
    max_speed REAL,
    total_alerts INT DEFAULT 0,
    critical_alerts INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trips_vehicle ON trips(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_trips_driver ON trips(driver_id);
CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status);

-- ================================================
-- TABLE 5: Job Queue (PostgreSQL-backed queue)
-- ================================================
CREATE TABLE IF NOT EXISTS job_queue (
    id SERIAL PRIMARY KEY,
    job_id UUID UNIQUE DEFAULT gen_random_uuid(),
    video_id INT REFERENCES videos(id) ON DELETE CASCADE,
    trip_id INT REFERENCES trips(id) ON DELETE SET NULL,
    video_type VARCHAR(20) DEFAULT 'dashcam',
    device VARCHAR(10) DEFAULT 'cuda',
    
    -- Job status
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    priority INT DEFAULT 0,
    progress_percent INT DEFAULT 0,
    
    -- Worker tracking
    worker_id VARCHAR(50),
    worker_heartbeat TIMESTAMPTZ,
    
    -- Retry logic
    attempts INT DEFAULT 0,
    max_attempts INT DEFAULT 3,
    
    -- Results
    result_path VARCHAR(500),
    error_message TEXT,
    processing_time_seconds INT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Critical index for job queue polling
CREATE INDEX IF NOT EXISTS idx_jobs_queue_poll 
    ON job_queue(status, priority DESC, created_at ASC) 
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_jobs_status ON job_queue(status);
CREATE INDEX IF NOT EXISTS idx_jobs_worker ON job_queue(worker_id);
CREATE INDEX IF NOT EXISTS idx_jobs_video ON job_queue(video_id);

-- ================================================
-- TABLE 6: Safety Events (with JSONB metadata)
-- ================================================
CREATE TABLE IF NOT EXISTS safety_events (
    id SERIAL PRIMARY KEY,
    job_id INT REFERENCES job_queue(id) ON DELETE CASCADE,
    trip_id INT REFERENCES trips(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    timestamp_sec REAL NOT NULL,
    frame_number INT,
    description TEXT,
    location_lat REAL,
    location_lng REAL,
    speed_kmh REAL,
    meta_data JSONB,
    snapshot_path VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_job ON safety_events(job_id);
CREATE INDEX IF NOT EXISTS idx_events_trip ON safety_events(trip_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON safety_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_severity ON safety_events(severity);
-- GIN index for JSONB queries
CREATE INDEX IF NOT EXISTS idx_events_meta ON safety_events USING GIN(meta_data);

-- ================================================
-- TABLE 7: Driver States
-- ================================================
CREATE TABLE IF NOT EXISTS driver_states (
    id SERIAL PRIMARY KEY,
    trip_id INT REFERENCES trips(id) ON DELETE CASCADE,
    timestamp_sec REAL NOT NULL,
    is_drowsy BOOLEAN NOT NULL DEFAULT FALSE,
    drowsy_confidence REAL,
    drowsy_reason VARCHAR(50),
    ear_value REAL,
    mar_value REAL,
    head_pose VARCHAR(100),
    snapshot_path VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_driver_states_trip ON driver_states(trip_id);

-- ================================================
-- TABLE 8: Traffic Signs
-- ================================================
CREATE TABLE IF NOT EXISTS traffic_signs (
    id SERIAL PRIMARY KEY,
    trip_id INT REFERENCES trips(id) ON DELETE CASCADE,
    timestamp_sec REAL NOT NULL,
    sign_type VARCHAR(50) NOT NULL,
    confidence REAL NOT NULL,
    speed_limit INT,
    current_speed REAL,
    is_violation BOOLEAN DEFAULT FALSE,
    location_lat REAL,
    location_lng REAL,
    snapshot_path VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traffic_signs_trip ON traffic_signs(trip_id);

-- ================================================
-- TABLE 9: Alerts
-- ================================================
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    trip_id INT REFERENCES trips(id) ON DELETE CASCADE,
    job_id INT REFERENCES job_queue(id) ON DELETE SET NULL,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message VARCHAR(255) NOT NULL,
    message_vi VARCHAR(255),
    timestamp_sec REAL NOT NULL,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    is_played BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by INT REFERENCES users(id) ON DELETE SET NULL,
    meta_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_trip ON alerts(trip_id);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);

-- ================================================
-- TABLE 10: Model Versions
-- ================================================
CREATE TABLE IF NOT EXISTS model_versions (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_type VARCHAR(50) NOT NULL,
    version VARCHAR(50) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size_mb REAL,
    accuracy REAL,
    is_active BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(model_name, version)
);

-- ================================================
-- Sample Data
-- ================================================
INSERT INTO users (username, email, hashed_password, full_name, role, is_active)
VALUES ('admin', 'admin@adas.vn', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5sPNw/OkTw1D6', 'Administrator', 'admin', TRUE)
ON CONFLICT (username) DO NOTHING;

INSERT INTO vehicles (license_plate, vehicle_type, manufacturer, model, year, owner_id)
VALUES ('29A-12345', 'car', 'Toyota', 'Camry', 2023, 1)
ON CONFLICT (license_plate) DO NOTHING;

INSERT INTO model_versions (model_name, model_type, version, file_path, is_active, description)
VALUES 
    ('YOLOv11', 'OBJECT_DETECTION', 'v11.0', 'models/yolov11n.pt', TRUE, 'YOLOv11 nano for object detection'),
    ('MediaPipe', 'FACE_MESH', 'v0.10.14', 'models/mediapipe', TRUE, 'MediaPipe for driver monitoring'),
    ('LaneNet', 'LANE_DETECTION', 'v1.0', 'models/lanenet', TRUE, 'Custom lane detection model')
ON CONFLICT (model_name, version) DO NOTHING;

-- ================================================
-- Migration helper: Copy data from video_jobs to new schema
-- (Run manually if migrating from SQL Server)
-- ================================================
-- INSERT INTO videos (sha256_hash, original_filename, storage_path, size_bytes)
-- SELECT 
--     md5(video_path || video_filename),
--     video_filename,
--     video_path,
--     COALESCE(video_size_mb * 1024 * 1024, 0)::BIGINT
-- FROM video_jobs_old
-- ON CONFLICT (sha256_hash) DO NOTHING;
