"""
Database models module
"""

# Import all models for Alembic auto-discovery
from .user import User
from .vehicle import Vehicle
from .trip import Trip
from .video_job import VideoJob
from .safety_event import SafetyEvent
from .traffic_sign import TrafficSign
from .driver_state import DriverState
from .alert import Alert, AlertHistory
from .model_version import ModelVersion

__all__ = [
    "User",
    "Vehicle",
    "Trip",
    "VideoJob",
    "SafetyEvent",
    "TrafficSign",
    "DriverState",
    "Alert",
    "AlertHistory",
    "ModelVersion",
]
