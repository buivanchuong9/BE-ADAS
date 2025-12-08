"""
Safety Layer - ISO 26262 ASIL-B compliant safety mechanisms
Includes: Watchdog, Fail-Safe Manager, Diagnostics (DEM), Redundancy
"""

from .watchdog import SystemWatchdog, ComponentHealth
from .fail_safe import FailSafeManager, SafeState, FailSafeAction
from .diagnostics import DiagnosticManager, ErrorCode, ErrorSeverity

__all__ = [
    "SystemWatchdog",
    "ComponentHealth",
    "FailSafeManager",
    "SafeState",
    "FailSafeAction",
    "DiagnosticManager",
    "ErrorCode",
    "ErrorSeverity",
]
