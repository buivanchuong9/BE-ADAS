"""
Database Models
===============
All SQLAlchemy models for the application.

IMPORTANT: Import order matters for relationships!
- Base models first (User, Vehicle, Trip)
- Video model (referenced by JobQueue)
- JobQueue model (references Video)
- Other models
"""

from .user import User
from .vehicle import Vehicle
from .trip import Trip
from .video import Video  # Must come before JobQueue
from .job_queue import JobQueue, JobStatus  # References Video
from .safety_event import SafetyEvent, EventType, EventSeverity
from .driver_state import DriverState
from .traffic_sign import TrafficSign
from .alert import Alert
from .model_version import ModelVersion

# Legacy model (kept for compatibility)
from .video_job import VideoJob

__all__ = [
    "User",
    "Vehicle", 
    "Trip",
    "Video",
    "JobQueue",
    "JobStatus",
    "SafetyEvent",
    "EventType",
    "EventSeverity",
    "DriverState",
    "TrafficSign",
    "Alert",
    "ModelVersion",
    "VideoJob",  # Legacy
]
