"""
ADAS Core Framework - Production-Ready Modular Architecture
Version: 4.0.0

ISO 26262 ASIL-B compliant
Clean Architecture with SOLID principles
"""

__version__ = "4.0.0"
__author__ = "ADAS Platform Team"

from .sensors.base import ISensor, SensorData, SensorStatus
from .perception.base import IPerception, PerceptionResult
from .safety.watchdog import SystemWatchdog
from .safety.fail_safe import FailSafeManager

__all__ = [
    "ISensor",
    "SensorData", 
    "SensorStatus",
    "IPerception",
    "PerceptionResult",
    "SystemWatchdog",
    "FailSafeManager",
]
