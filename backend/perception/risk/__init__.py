"""Risk assessment module for ADAS system — V4 TTC-based engine."""

from .risk_engine_v4 import RiskEngineV4, RiskResultV4, EgoDangerZone

# Legacy alias
RiskAssessor = RiskEngineV4

__all__ = ["RiskEngineV4", "RiskResultV4", "EgoDangerZone", "RiskAssessor"]
