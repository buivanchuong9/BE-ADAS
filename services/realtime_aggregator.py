"""
ADAS Backend - Real-time Data Aggregator
Aggregates sensor data, detections, and alerts for live dashboard updates
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import deque
import asyncio
import json
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class SensorReading:
    """Real-time sensor reading"""
    timestamp: datetime
    sensor_type: str  # speed, distance, temperature, etc.
    value: float
    unit: str
    camera_id: Optional[int] = None


@dataclass
class LiveMetric:
    """Live system metric"""
    metric_name: str
    current_value: float
    trend: str  # up, down, stable
    change_percent: float
    timestamp: datetime


class RealTimeDataAggregator:
    """
    Aggregates and manages real-time data streams
    Provides latest values and historical data for dashboards
    """
    
    def __init__(self, max_history_size: int = 1000):
        self.max_history_size = max_history_size
        
        # Data buffers (thread-safe deques)
        self.detections_buffer = deque(maxlen=max_history_size)
        self.alerts_buffer = deque(maxlen=max_history_size)
        self.sensor_readings = {}  # sensor_type -> deque
        self.metrics_history = {}  # metric_name -> deque
        
        # Current state
        self.current_state = {
            "detections_per_second": 0.0,
            "alerts_per_minute": 0.0,
            "active_cameras": 0,
            "system_load": 0.0,
            "total_objects_detected": 0,
            "critical_alerts": 0
        }
        
        # Statistics
        self.stats = {
            "total_detections": 0,
            "total_alerts": 0,
            "session_start_time": datetime.utcnow()
        }
        
        logger.info("RealTimeDataAggregator initialized")
    
    # ============ Detection Management ============
    
    def add_detection(self, detection: Dict[str, Any]):
        """Add new detection to buffer"""
        detection["timestamp"] = datetime.utcnow()
        self.detections_buffer.append(detection)
        self.stats["total_detections"] += 1
        self._update_detection_rate()
    
    def get_recent_detections(self, limit: int = 50) -> List[Dict]:
        """Get most recent detections"""
        return list(self.detections_buffer)[-limit:]
    
    def get_detections_by_class(self, hours: int = 1) -> Dict[str, int]:
        """Get detection counts grouped by class"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        counts = {}
        
        for det in self.detections_buffer:
            if det["timestamp"] >= cutoff_time:
                class_name = det.get("class_name", "unknown")
                counts[class_name] = counts.get(class_name, 0) + 1
        
        return counts
    
    def _update_detection_rate(self):
        """Calculate detections per second"""
        recent = self.get_recent_detections(60)  # Last 60 detections
        if len(recent) < 2:
            self.current_state["detections_per_second"] = 0.0
            return
        
        time_span = (recent[-1]["timestamp"] - recent[0]["timestamp"]).total_seconds()
        if time_span > 0:
            self.current_state["detections_per_second"] = len(recent) / time_span
    
    # ============ Alert Management ============
    
    def add_alert(self, alert: Dict[str, Any]):
        """Add new alert to buffer"""
        alert["timestamp"] = datetime.utcnow()
        self.alerts_buffer.append(alert)
        self.stats["total_alerts"] += 1
        
        if alert.get("severity") == "critical":
            self.current_state["critical_alerts"] += 1
        
        self._update_alert_rate()
    
    def get_recent_alerts(self, limit: int = 20) -> List[Dict]:
        """Get most recent alerts"""
        return list(self.alerts_buffer)[-limit:]
    
    def get_unplayed_alerts(self) -> List[Dict]:
        """Get alerts that haven't been played"""
        return [a for a in self.alerts_buffer if not a.get("played", False)]
    
    def mark_alert_played(self, alert_id: int):
        """Mark an alert as played"""
        for alert in self.alerts_buffer:
            if alert.get("id") == alert_id:
                alert["played"] = True
                break
    
    def _update_alert_rate(self):
        """Calculate alerts per minute"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=1)
        recent_count = sum(1 for a in self.alerts_buffer if a["timestamp"] >= cutoff_time)
        self.current_state["alerts_per_minute"] = recent_count
    
    # ============ Sensor Data Management ============
    
    def add_sensor_reading(self, sensor_type: str, value: float, unit: str, camera_id: Optional[int] = None):
        """Add sensor reading"""
        if sensor_type not in self.sensor_readings:
            self.sensor_readings[sensor_type] = deque(maxlen=self.max_history_size)
        
        reading = SensorReading(
            timestamp=datetime.utcnow(),
            sensor_type=sensor_type,
            value=value,
            unit=unit,
            camera_id=camera_id
        )
        
        self.sensor_readings[sensor_type].append(asdict(reading))
    
    def get_sensor_history(self, sensor_type: str, minutes: int = 5) -> List[Dict]:
        """Get sensor reading history"""
        if sensor_type not in self.sensor_readings:
            return []
        
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        return [
            r for r in self.sensor_readings[sensor_type]
            if r["timestamp"] >= cutoff_time
        ]
    
    def get_latest_sensor_value(self, sensor_type: str) -> Optional[float]:
        """Get latest sensor value"""
        if sensor_type not in self.sensor_readings or len(self.sensor_readings[sensor_type]) == 0:
            return None
        return self.sensor_readings[sensor_type][-1]["value"]
    
    # ============ Metrics Management ============
    
    def update_metric(self, metric_name: str, value: float):
        """Update a system metric"""
        if metric_name not in self.metrics_history:
            self.metrics_history[metric_name] = deque(maxlen=100)
        
        # Calculate trend
        trend = "stable"
        change_percent = 0.0
        
        if len(self.metrics_history[metric_name]) > 0:
            prev_value = self.metrics_history[metric_name][-1].current_value
            if prev_value != 0:
                change_percent = ((value - prev_value) / prev_value) * 100
                if change_percent > 1:
                    trend = "up"
                elif change_percent < -1:
                    trend = "down"
        
        metric = LiveMetric(
            metric_name=metric_name,
            current_value=value,
            trend=trend,
            change_percent=change_percent,
            timestamp=datetime.utcnow()
        )
        
        self.metrics_history[metric_name].append(metric)
        self.current_state[metric_name] = value
    
    def get_metric_history(self, metric_name: str, limit: int = 50) -> List[Dict]:
        """Get metric history"""
        if metric_name not in self.metrics_history:
            return []
        return [asdict(m) for m in list(self.metrics_history[metric_name])[-limit:]]
    
    # ============ Dashboard Data ============
    
    def get_dashboard_snapshot(self) -> Dict[str, Any]:
        """Get complete dashboard data snapshot"""
        uptime = (datetime.utcnow() - self.stats["session_start_time"]).total_seconds()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "current_state": self.current_state.copy(),
            "statistics": {
                "total_detections": self.stats["total_detections"],
                "total_alerts": self.stats["total_alerts"],
                "uptime_seconds": uptime,
                "uptime_hours": uptime / 3600
            },
            "recent_data": {
                "detections": self.get_recent_detections(10),
                "alerts": self.get_recent_alerts(5),
                "detections_by_class": self.get_detections_by_class(hours=1)
            }
        }
    
    def get_chart_data(self, data_type: str, minutes: int = 5) -> Dict[str, Any]:
        """Get data formatted for charts"""
        if data_type == "detections_timeline":
            return self._get_detections_timeline(minutes)
        elif data_type == "alerts_timeline":
            return self._get_alerts_timeline(minutes)
        elif data_type.startswith("sensor_"):
            sensor_type = data_type.replace("sensor_", "")
            return self._get_sensor_chart_data(sensor_type, minutes)
        else:
            return {"labels": [], "datasets": []}
    
    def _get_detections_timeline(self, minutes: int) -> Dict[str, Any]:
        """Get detection timeline for chart"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        # Group by minute
        timeline = {}
        for det in self.detections_buffer:
            if det["timestamp"] >= cutoff_time:
                minute_key = det["timestamp"].strftime("%H:%M")
                timeline[minute_key] = timeline.get(minute_key, 0) + 1
        
        # Sort by time
        sorted_timeline = sorted(timeline.items())
        
        return {
            "labels": [t[0] for t in sorted_timeline],
            "datasets": [{
                "label": "Detections",
                "data": [t[1] for t in sorted_timeline],
                "borderColor": "rgb(75, 192, 192)",
                "tension": 0.1
            }]
        }
    
    def _get_alerts_timeline(self, minutes: int) -> Dict[str, Any]:
        """Get alert timeline for chart"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        timeline = {}
        for alert in self.alerts_buffer:
            if alert["timestamp"] >= cutoff_time:
                minute_key = alert["timestamp"].strftime("%H:%M")
                timeline[minute_key] = timeline.get(minute_key, 0) + 1
        
        sorted_timeline = sorted(timeline.items())
        
        return {
            "labels": [t[0] for t in sorted_timeline],
            "datasets": [{
                "label": "Alerts",
                "data": [t[1] for t in sorted_timeline],
                "borderColor": "rgb(255, 99, 132)",
                "tension": 0.1
            }]
        }
    
    def _get_sensor_chart_data(self, sensor_type: str, minutes: int) -> Dict[str, Any]:
        """Get sensor data for chart"""
        history = self.get_sensor_history(sensor_type, minutes)
        
        if not history:
            return {"labels": [], "datasets": []}
        
        return {
            "labels": [h["timestamp"].strftime("%H:%M:%S") for h in history],
            "datasets": [{
                "label": sensor_type.replace("_", " ").title(),
                "data": [h["value"] for h in history],
                "borderColor": "rgb(54, 162, 235)",
                "tension": 0.1
            }]
        }
    
    # ============ Cleanup ============
    
    def clear_old_data(self, hours: int = 24):
        """Clear data older than specified hours"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Clear old detections
        self.detections_buffer = deque(
            [d for d in self.detections_buffer if d["timestamp"] >= cutoff_time],
            maxlen=self.max_history_size
        )
        
        # Clear old alerts
        self.alerts_buffer = deque(
            [a for a in self.alerts_buffer if a["timestamp"] >= cutoff_time],
            maxlen=self.max_history_size
        )
        
        logger.info(f"Cleared data older than {hours} hours")
    
    def reset_statistics(self):
        """Reset all statistics"""
        self.stats = {
            "total_detections": 0,
            "total_alerts": 0,
            "session_start_time": datetime.utcnow()
        }
        self.current_state["critical_alerts"] = 0
        logger.info("Statistics reset")


# Global aggregator instance
_aggregator_instance = None


def get_aggregator() -> RealTimeDataAggregator:
    """Get or create global aggregator instance"""
    global _aggregator_instance
    if _aggregator_instance is None:
        _aggregator_instance = RealTimeDataAggregator()
    return _aggregator_instance


def reset_aggregator():
    """Reset global aggregator instance"""
    global _aggregator_instance
    _aggregator_instance = None
