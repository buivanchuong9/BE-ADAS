# Database Models for ADAS System
# SQLAlchemy models mapped to SQL Server PascalCase columns

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Camera(Base):
    __tablename__ = "Cameras"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    name = Column("Name", String(100), nullable=False)
    type = Column("Type", String(50), nullable=False)
    url = Column("Url", String(500))
    status = Column("Status", String(50), default="disconnected")
    resolution = Column("Resolution", String(100))
    frame_rate = Column("FrameRate", Integer)
    instructions = Column("Instructions", Text)
    created_at = Column("CreatedAt", DateTime, default=datetime.utcnow)
    last_active_at = Column("LastActiveAt", DateTime)
    
    # Relationships
    detections = relationship("Detection", back_populates="camera")
    events = relationship("Event", back_populates="camera")
    trips = relationship("Trip", back_populates="camera")

class Driver(Base):
    __tablename__ = "Drivers"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    name = Column("Name", String(100), nullable=False)
    license_number = Column("LicenseNumber", String(50))
    email = Column("Email", String(100))
    phone = Column("Phone", String(20))
    date_of_birth = Column("DateOfBirth", DateTime)
    address = Column("Address", String(200))
    total_trips = Column("TotalTrips", Integer, default=0)
    total_distance_km = Column("TotalDistanceKm", Float, default=0.0)
    safety_score = Column("SafetyScore", Integer, default=100)
    status = Column("Status", String(50), default="active")
    created_at = Column("CreatedAt", DateTime, default=datetime.utcnow)
    last_active_at = Column("LastActiveAt", DateTime)
    
    # Relationships
    trips = relationship("Trip", back_populates="driver")
    events = relationship("Event", back_populates="driver")
    driver_statuses = relationship("DriverStatus", back_populates="driver")

class Trip(Base):
    __tablename__ = "Trips"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    start_time = Column("StartTime", DateTime, nullable=False, default=datetime.utcnow)
    end_time = Column("EndTime", DateTime)
    distance_km = Column("DistanceKm", Float)
    duration_minutes = Column("DurationMinutes", Float)
    start_location = Column("StartLocation", String(200))
    end_location = Column("EndLocation", String(200))
    average_speed = Column("AverageSpeed", Integer)
    max_speed = Column("MaxSpeed", Integer)
    status = Column("Status", String(50), default="active")
    total_events = Column("TotalEvents", Integer, default=0)
    critical_events = Column("CriticalEvents", Integer, default=0)
    route_data = Column("RouteData", Text)
    
    driver_id = Column("DriverId", Integer, ForeignKey("Drivers.Id"))
    camera_id = Column("CameraId", Integer, ForeignKey("Cameras.Id"))
    
    # Relationships
    driver = relationship("Driver", back_populates="trips")
    camera = relationship("Camera", back_populates="trips")
    detections = relationship("Detection", back_populates="trip")
    events = relationship("Event", back_populates="trip")
    analytics = relationship("Analytics", back_populates="trip")

class Event(Base):
    __tablename__ = "Events"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    event_type = Column("EventType", String(100), nullable=False, index=True)
    description = Column("Description", String(500))
    timestamp = Column("Timestamp", DateTime, nullable=False, default=datetime.utcnow, index=True)
    severity = Column("Severity", String(50))
    location = Column("Location", String(200))
    event_metadata = Column("Metadata", Text)
    
    trip_id = Column("TripId", Integer, ForeignKey("Trips.Id"))
    camera_id = Column("CameraId", Integer, ForeignKey("Cameras.Id"))
    driver_id = Column("DriverId", Integer, ForeignKey("Drivers.Id"))
    
    # Relationships
    trip = relationship("Trip", back_populates="events")
    camera = relationship("Camera", back_populates="events")
    driver = relationship("Driver", back_populates="events")

class Detection(Base):
    __tablename__ = "Detections"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    class_name = Column("ClassName", String(100), nullable=False, index=True)
    confidence = Column("Confidence", Float, nullable=False)
    bounding_box = Column("BoundingBox", Text, nullable=False)
    distance_meters = Column("DistanceMeters", Float)
    relative_speed = Column("RelativeSpeed", Float)
    timestamp = Column("Timestamp", DateTime, nullable=False, default=datetime.utcnow, index=True)
    frame_number = Column("FrameNumber", Integer)
    
    trip_id = Column("TripId", Integer, ForeignKey("Trips.Id"))
    camera_id = Column("CameraId", Integer, ForeignKey("Cameras.Id"))
    
    # Relationships
    trip = relationship("Trip", back_populates="detections")
    camera = relationship("Camera", back_populates="detections")

class DriverStatus(Base):
    __tablename__ = "DriverStatuses"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    timestamp = Column("Timestamp", DateTime, nullable=False, default=datetime.utcnow, index=True)
    fatigue_level = Column("FatigueLevel", String(50))
    distraction_level = Column("DistractionLevel", String(50))
    eye_closure_duration = Column("EyeClosureDuration", Float)
    head_pose_yaw = Column("HeadPoseYaw", Integer)
    head_pose_pitch = Column("HeadPosePitch", Integer)
    is_yawning = Column("IsYawning", Boolean)
    is_using_phone = Column("IsUsingPhone", Boolean)
    alert_count = Column("AlertCount", Integer, default=0)
    
    driver_id = Column("DriverId", Integer, ForeignKey("Drivers.Id"))
    trip_id = Column("TripId", Integer, ForeignKey("Trips.Id"))
    
    # Relationships
    driver = relationship("Driver", back_populates="driver_statuses")

class Analytics(Base):
    __tablename__ = "Analytics"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    timestamp = Column("Timestamp", DateTime, nullable=False, default=datetime.utcnow, index=True)
    metric_type = Column("MetricType", String(100), nullable=False, index=True)
    value = Column("Value", Float, nullable=False)
    unit = Column("Unit", String(50))
    category = Column("Category", String(100))
    analytics_metadata = Column("Metadata", Text)
    
    trip_id = Column("TripId", Integer, ForeignKey("Trips.Id"))
    driver_id = Column("DriverId", Integer, ForeignKey("Drivers.Id"))
    
    # Relationships
    trip = relationship("Trip", back_populates="analytics")
    driver = relationship("Driver")

class AIModel(Base):
    __tablename__ = "AIModels"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    model_id = Column("ModelId", String(100), unique=True, nullable=False, index=True)
    name = Column("Name", String(200), nullable=False)
    model_type = Column("ModelType", String(50), default="yolo11")  # yolo11, yolop, midas
    size = Column("Size", String(50))
    downloaded = Column("Downloaded", Boolean, default=False)
    accuracy = Column("Accuracy", Float)
    url = Column("Url", String(500))
    file_path = Column("FilePath", String(1000))
    version = Column("Version", String(50))
    description = Column("Description", String(500))
    config = Column("Config", Text)  # JSON config
    created_at = Column("CreatedAt", DateTime, default=datetime.utcnow)
    last_used_at = Column("LastUsedAt", DateTime)
    is_active = Column("IsActive", Boolean, default=False, index=True)


class VideoDataset(Base):
    __tablename__ = "VideoDatasets"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    filename = Column("Filename", String(200), nullable=False)
    original_filename = Column("OriginalFilename", String(200))
    file_path = Column("FilePath", String(1000), nullable=False)
    description = Column("Description", Text)
    fps = Column("Fps", Float)
    total_frames = Column("TotalFrames", Integer)
    labeled_frames = Column("LabeledFrames", Integer, default=0)
    width = Column("Width", Integer)
    height = Column("Height", Integer)
    duration = Column("Duration", Float)
    status = Column("Status", String(50), default="uploaded")  # uploaded, processing, labeled, error
    error_message = Column("ErrorMessage", Text)
    created_at = Column("CreatedAt", DateTime, default=datetime.utcnow)
    processed_at = Column("ProcessedAt", DateTime)
    
    # Relationships
    labels = relationship("Label", back_populates="video")


class Label(Base):
    __tablename__ = "Labels"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    video_id = Column("VideoId", Integer, ForeignKey("VideoDatasets.Id"), nullable=False)
    frame_number = Column("FrameNumber", Integer, nullable=False)
    label_data = Column("LabelData", Text, nullable=False)  # JSON: [{class_id, bbox, confidence, distance}]
    has_vehicle = Column("HasVehicle", Boolean, default=False)
    has_lane = Column("HasLane", Boolean, default=False)
    auto_labeled = Column("AutoLabeled", Boolean, default=False)
    verified = Column("Verified", Boolean, default=False)
    created_at = Column("CreatedAt", DateTime, default=datetime.utcnow)
    
    # Relationships
    video = relationship("VideoDataset", back_populates="labels")


class Alert(Base):
    __tablename__ = "Alerts"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    event_id = Column("EventId", Integer, ForeignKey("Events.Id"))
    ttc = Column("TTC", Float)  # Time to collision (seconds)
    distance = Column("Distance", Float)  # Distance in meters
    relative_speed = Column("RelativeSpeed", Float)  # m/s
    severity = Column("Severity", String(50))  # critical, high, medium, low
    alert_type = Column("AlertType", String(100))  # collision_warning, lane_departure, etc.
    message = Column("Message", Text)
    audio_path = Column("AudioPath", String(1000))  # Path to TTS audio file
    played = Column("Played", Boolean, default=False)
    created_at = Column("CreatedAt", DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    event = relationship("Event", backref="alerts")


# =====================================================
# ADAS Models (New)
# =====================================================

class ADASSession(Base):
    """
    ADAS Session - Tracking real-time ADAS usage
    """
    __tablename__ = "ADASSessions"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    driver_id = Column("DriverId", Integer, ForeignKey("Drivers.Id"), nullable=True)
    camera_id = Column("CameraId", Integer, ForeignKey("Cameras.Id"), nullable=True)
    start_time = Column("StartTime", DateTime, default=datetime.utcnow, index=True)
    end_time = Column("EndTime", DateTime, nullable=True)
    total_frames = Column("TotalFrames", Integer, default=0)
    total_events = Column("TotalEvents", Integer, default=0)
    avg_speed = Column("AvgSpeed", Float, nullable=True)  # km/h
    max_speed = Column("MaxSpeed", Float, nullable=True)  # km/h
    distance_traveled = Column("DistanceTraveled", Float, default=0.0)  # km
    statistics = Column("Statistics", Text, nullable=True)  # JSON stats
    created_at = Column("CreatedAt", DateTime, default=datetime.utcnow)
    
    # Relationships
    events = relationship("ADASEvent", back_populates="session")
    driver = relationship("Driver", backref="adas_sessions")
    camera = relationship("Camera", backref="adas_sessions")


class ADASEvent(Base):
    """
    ADAS Event - Individual alerts/detections during session
    """
    __tablename__ = "ADASEvents"
    
    id = Column("Id", Integer, primary_key=True, index=True)
    session_id = Column("SessionId", Integer, ForeignKey("ADASSessions.Id"), nullable=False)
    event_type = Column("EventType", String(50), nullable=False, index=True)  # speeding, collision_warning, lane_departure, sign_detected
    severity = Column("Severity", String(20), nullable=False)  # info, warning, danger
    message = Column("Message", Text, nullable=False)
    data = Column("Data", Text, nullable=True)  # JSON data (vehicle distance, speed limit, etc.)
    timestamp = Column("Timestamp", DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    session = relationship("ADASSession", back_populates="events")
