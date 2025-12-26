"""
RISK ASSESSMENT ENGINE
======================
Phase 5: Multi-factor risk scoring and alert generation for ADAS system.

PURPOSE:
Combines perception outputs and temporal context to generate intelligent,
actionable alerts with proper prioritization and deduplication.

RESPONSIBILITIES:
1. Multi-factor risk scoring (TTC, distance, lane offset, driver state)
2. Alert generation with severity levels (INFO, WARNING, CRITICAL)
3. Alert deduplication and cooldown management
4. Explainable risk assessments for NCKH defense

PRODUCTION FEATURES:
- Physics-based risk calculation
- Temporal consistency requirements
- Smart alert throttling (prevent spam)
- Vietnamese road condition adaptation

DESIGN PHILOSOPHY:
This is the "decision-making brain" of the ADAS system. It takes all perception
and context inputs and decides:
- WHEN to alert the driver
- HOW urgent the alert is
- WHAT specific action to recommend

The engine is conservative (safety-first) but intelligent (avoids false alarms).

Author: Senior ADAS Engineer
Date: 2025-12-26 (Phase 5)
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertType(str, Enum):
    """Alert types supported by the system."""
    FORWARD_COLLISION_WARNING = "FCW"
    LANE_DEPARTURE_WARNING = "LDW"
    DRIVER_DROWSINESS_WARNING = "DDW"
    HEADWAY_MONITORING_WARNING = "HMW"
    PEDESTRIAN_COLLISION_WARNING = "PCW"
    TRAFFIC_SIGN_VIOLATION = "TSV"


class RiskAlert:
    """Container for risk alert information."""
    
    def __init__(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        risk_score: float,
        message: str,
        message_vi: str,
        metadata: Dict[str, Any],
        frame_number: int
    ):
        self.alert_type = alert_type
        self.severity = severity
        self.risk_score = risk_score
        self.message = message
        self.message_vi = message_vi
        self.metadata = metadata
        self.frame_number = frame_number
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            'alert_type': self.alert_type.value,
            'severity': self.severity.value,
            'risk_score': self.risk_score,
            'message': self.message,
            'message_vi': self.message_vi,
            'metadata': self.metadata,
            'frame_number': self.frame_number,
            'timestamp': self.timestamp.isoformat()
        }


class RiskEngine:
    """
    Multi-factor risk assessment engine with intelligent alert generation.
    """
    
    # Risk thresholds
    TTC_CRITICAL = 0.5    # seconds
    TTC_WARNING = 1.5
    TTC_INFO = 3.0
    
    DISTANCE_CRITICAL = 3.0   # meters
    DISTANCE_WARNING = 7.0
    DISTANCE_INFO = 15.0
    
    LANE_OFFSET_CRITICAL = 0.8  # fraction of lane width
    LANE_OFFSET_WARNING = 0.5
    
    # Alert cooldown periods (seconds)
    COOLDOWN_CONFIG = {
        AlertType.FORWARD_COLLISION_WARNING: 3.0,
        AlertType.LANE_DEPARTURE_WARNING: 5.0,
        AlertType.DRIVER_DROWSINESS_WARNING: 10.0,
        AlertType.HEADWAY_MONITORING_WARNING: 5.0,
        AlertType.PEDESTRIAN_COLLISION_WARNING: 3.0,
        AlertType.TRAFFIC_SIGN_VIOLATION: 10.0
    }
    
    def __init__(
        self,
        frame_rate: int = 30,
        enable_deduplication: bool = True,
        vietnamese_mode: bool = True
    ):
        """
        Initialize risk assessment engine.
        
        Args:
            frame_rate: Video frame rate (fps)
            enable_deduplication: Enable alert deduplication
            vietnamese_mode: Use Vietnamese road conditions
        """
        self.frame_rate = frame_rate
        self.enable_deduplication = enable_deduplication
        self.vietnamese_mode = vietnamese_mode
        
        # Alert cooldown tracking
        self.last_alert_times = defaultdict(lambda: datetime.min)
        
        # Alert history for analysis
        self.alert_history = []
        
        # Frame counter
        self.frame_number = 0
        
        logger.info(f"RiskEngine initialized: fps={frame_rate}, dedup={enable_deduplication}, vi_mode={vietnamese_mode}")
    
    def assess_forward_collision_risk(
        self,
        tracked_objects: List[Dict[str, Any]],
        context_state: Dict[str, Any]
    ) -> Optional[RiskAlert]:
        """
        Assess forward collision risk (FCW).
        
        Args:
            tracked_objects: List of tracked objects with distance/TTC
            context_state: Current context state from ContextEngine
            
        Returns:
            RiskAlert if collision risk detected, None otherwise
        """
        if not tracked_objects:
            return None
        
        # Filter for vehicles ahead
        vehicles_ahead = [
            obj for obj in tracked_objects
            if obj.get('class_name') in {'car', 'truck', 'bus', 'motorcycle'}
            and obj.get('is_approaching', False)
        ]
        
        if not vehicles_ahead:
            return None
        
        # Find most critical vehicle
        critical_vehicle = min(
            vehicles_ahead,
            key=lambda x: x.get('ttc', float('inf'))
        )
        
        ttc = critical_vehicle.get('ttc')
        distance = critical_vehicle.get('distance')
        
        if ttc is None or distance is None:
            return None
        
        # Determine severity
        severity = None
        risk_score = 0.0
        
        if ttc <= self.TTC_CRITICAL:
            severity = AlertSeverity.CRITICAL
            risk_score = 1.0
        elif ttc <= self.TTC_WARNING:
            severity = AlertSeverity.WARNING
            risk_score = 0.7 - (ttc / self.TTC_WARNING) * 0.3
        elif ttc <= self.TTC_INFO:
            severity = AlertSeverity.INFO
            risk_score = 0.4 - (ttc / self.TTC_INFO) * 0.2
        
        if severity is None:
            return None
        
        # Check deduplication
        if self.enable_deduplication:
            if not self._should_alert(AlertType.FORWARD_COLLISION_WARNING):
                return None
        
        # Create alert
        message = f"Forward Collision Warning! Vehicle ahead in {ttc:.1f}s ({distance:.1f}m)"
        message_vi = f"Cảnh báo va chạm phía trước! Xe phía trước trong {ttc:.1f}s ({distance:.1f}m)"
        
        alert = RiskAlert(
            alert_type=AlertType.FORWARD_COLLISION_WARNING,
            severity=severity,
            risk_score=risk_score,
            message=message,
            message_vi=message_vi,
            metadata={
                'ttc': ttc,
                'distance': distance,
                'closing_speed': critical_vehicle.get('closing_speed', 0.0),
                'vehicle_class': critical_vehicle.get('class_name'),
                'risk_level': critical_vehicle.get('risk_level')
            },
            frame_number=self.frame_number
        )
        
        self._register_alert(alert)
        return alert
    
    def assess_lane_departure_risk(
        self,
        lane_output: Dict[str, Any],
        context_state: Dict[str, Any]
    ) -> Optional[RiskAlert]:
        """
        Assess lane departure risk (LDW).
        
        Args:
            lane_output: Lane detection output
            context_state: Current context state
            
        Returns:
            RiskAlert if lane departure detected, None otherwise
        """
        # Check sustained departure from context
        sustained_departure = context_state.get('sustained_lane_departure', False)
        
        if not sustained_departure:
            return None
        
        lane_stability = context_state.get('lane_stability_score', 0.0)
        offset = abs(lane_output.get('offset', 0.0))
        
        # Determine severity based on offset and stability
        severity = None
        risk_score = 0.0
        
        if offset > self.LANE_OFFSET_CRITICAL or lane_stability < 0.3:
            severity = AlertSeverity.CRITICAL
            risk_score = min(offset / self.LANE_OFFSET_CRITICAL, 1.0)
        elif offset > self.LANE_OFFSET_WARNING or lane_stability < 0.5:
            severity = AlertSeverity.WARNING
            risk_score = 0.6
        else:
            severity = AlertSeverity.INFO
            risk_score = 0.3
        
        # Check deduplication
        if self.enable_deduplication:
            if not self._should_alert(AlertType.LANE_DEPARTURE_WARNING):
                return None
        
        # Create alert
        direction = lane_output.get('direction', 'UNKNOWN')
        message = f"Lane Departure Warning! Vehicle drifting {direction} (offset: {offset:.2f})"
        message_vi = f"Cảnh báo chệch làn đường! Xe đang lệch {direction} (độ lệch: {offset:.2f})"
        
        alert = RiskAlert(
            alert_type=AlertType.LANE_DEPARTURE_WARNING,
            severity=severity,
            risk_score=risk_score,
            message=message,
            message_vi=message_vi,
            metadata={
                'offset': offset,
                'direction': direction,
                'lane_stability': lane_stability,
                'left_confidence': lane_output.get('left_confidence', 0.0),
                'right_confidence': lane_output.get('right_confidence', 0.0)
            },
            frame_number=self.frame_number
        )
        
        self._register_alert(alert)
        return alert
    
    def assess_driver_drowsiness_risk(
        self,
        driver_output: Dict[str, Any],
        context_state: Dict[str, Any]
    ) -> Optional[RiskAlert]:
        """
        Assess driver drowsiness risk (DDW).
        
        Args:
            driver_output: Driver monitoring output
            context_state: Current context state
            
        Returns:
            RiskAlert if drowsiness detected, None otherwise
        """
        # Check sustained drowsiness
        should_alert = driver_output.get('should_alert', False)
        
        if not should_alert:
            return None
        
        alertness_score = context_state.get('driver_alertness_score', 1.0)
        drowsy_confidence = driver_output.get('drowsy_confidence', 0.0)
        drowsy_reason = driver_output.get('drowsy_reason', 'UNKNOWN')
        
        # Determine severity
        severity = None
        risk_score = 0.0
        
        if alertness_score < 0.3 or drowsy_confidence > 0.9:
            severity = AlertSeverity.CRITICAL
            risk_score = 1.0 - alertness_score
        elif alertness_score < 0.6 or drowsy_confidence > 0.7:
            severity = AlertSeverity.WARNING
            risk_score = 0.7
        else:
            severity = AlertSeverity.INFO
            risk_score = 0.4
        
        # Check deduplication
        if self.enable_deduplication:
            if not self._should_alert(AlertType.DRIVER_DROWSINESS_WARNING):
                return None
        
        # Create alert
        message = f"Driver Drowsiness Warning! {drowsy_reason} detected"
        message_vi = f"Cảnh báo tài xế buồn ngủ! Phát hiện {drowsy_reason}"
        
        alert = RiskAlert(
            alert_type=AlertType.DRIVER_DROWSINESS_WARNING,
            severity=severity,
            risk_score=risk_score,
            message=message,
            message_vi=message_vi,
            metadata={
                'alertness_score': alertness_score,
                'drowsy_confidence': drowsy_confidence,
                'drowsy_reason': drowsy_reason,
                'ear': driver_output.get('smoothed_ear', 0.0),
                'mar': driver_output.get('smoothed_mar', 0.0)
            },
            frame_number=self.frame_number
        )
        
        self._register_alert(alert)
        return alert
    
    def assess_pedestrian_collision_risk(
        self,
        tracked_objects: List[Dict[str, Any]],
        context_state: Dict[str, Any]
    ) -> Optional[RiskAlert]:
        """
        Assess pedestrian collision risk (PCW).
        
        Args:
            tracked_objects: List of tracked objects
            context_state: Current context state
            
        Returns:
            RiskAlert if pedestrian collision risk detected, None otherwise
        """
        # Filter for pedestrians/bicycles
        pedestrians = [
            obj for obj in tracked_objects
            if obj.get('class_name') in {'person', 'bicycle'}
            and obj.get('distance', float('inf')) < self.DISTANCE_WARNING
        ]
        
        if not pedestrians:
            return None
        
        # Find closest pedestrian
        closest = min(pedestrians, key=lambda x: x.get('distance', float('inf')))
        
        distance = closest.get('distance')
        ttc = closest.get('ttc')
        
        if distance is None:
            return None
        
        # Determine severity (pedestrians get stricter thresholds)
        severity = None
        risk_score = 0.0
        
        if distance < 5.0 or (ttc and ttc < 1.0):
            severity = AlertSeverity.CRITICAL
            risk_score = 1.0 - (distance / 5.0)
        elif distance < 10.0 or (ttc and ttc < 2.0):
            severity = AlertSeverity.WARNING
            risk_score = 0.7
        else:
            severity = AlertSeverity.INFO
            risk_score = 0.4
        
        # Check deduplication
        if self.enable_deduplication:
            if not self._should_alert(AlertType.PEDESTRIAN_COLLISION_WARNING):
                return None
        
        # Create alert
        message = f"Pedestrian Warning! {closest.get('class_name')} at {distance:.1f}m"
        message_vi = f"Cảnh báo người đi bộ! {closest.get('class_name')} cách {distance:.1f}m"
        
        alert = RiskAlert(
            alert_type=AlertType.PEDESTRIAN_COLLISION_WARNING,
            severity=severity,
            risk_score=risk_score,
            message=message,
            message_vi=message_vi,
            metadata={
                'distance': distance,
                'ttc': ttc,
                'object_class': closest.get('class_name'),
                'risk_level': closest.get('risk_level')
            },
            frame_number=self.frame_number
        )
        
        self._register_alert(alert)
        return alert
    
    def assess_all_risks(
        self,
        lane_output: Dict[str, Any],
        tracked_objects: List[Dict[str, Any]],
        driver_output: Dict[str, Any],
        context_state: Dict[str, Any]
    ) -> List[RiskAlert]:
        """
        Comprehensive risk assessment across all categories.
        
        Args:
            lane_output: Lane detection output
            tracked_objects: List of tracked objects
            driver_output: Driver monitoring output
            context_state: Current context state
            
        Returns:
            List of RiskAlerts (sorted by severity)
        """
        self.frame_number += 1
        
        alerts = []
        
        # Assess each risk category
        fcw = self.assess_forward_collision_risk(tracked_objects, context_state)
        if fcw:
            alerts.append(fcw)
        
        ldw = self.assess_lane_departure_risk(lane_output, context_state)
        if ldw:
            alerts.append(ldw)
        
        ddw = self.assess_driver_drowsiness_risk(driver_output, context_state)
        if ddw:
            alerts.append(ddw)
        
        pcw = self.assess_pedestrian_collision_risk(tracked_objects, context_state)
        if pcw:
            alerts.append(pcw)
        
        # Sort by severity and risk score
        severity_order = {AlertSeverity.CRITICAL: 0, AlertSeverity.WARNING: 1, AlertSeverity.INFO: 2}
        alerts.sort(key=lambda a: (severity_order[a.severity], -a.risk_score))
        
        return alerts
    
    def _should_alert(self, alert_type: AlertType) -> bool:
        """
        Check if alert should be triggered (respecting cooldown).
        
        Args:
            alert_type: Type of alert
            
        Returns:
            True if alert should be triggered
        """
        now = datetime.utcnow()
        last_time = self.last_alert_times[alert_type]
        cooldown = timedelta(seconds=self.COOLDOWN_CONFIG[alert_type])
        
        if now - last_time >= cooldown:
            self.last_alert_times[alert_type] = now
            return True
        
        return False
    
    def _register_alert(self, alert: RiskAlert) -> None:
        """Register alert in history."""
        self.alert_history.append(alert)
        
        # Keep only last 1000 alerts
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about generated alerts.
        
        Returns:
            Dict with alert statistics
        """
        if not self.alert_history:
            return {
                'total_alerts': 0,
                'by_type': {},
                'by_severity': {}
            }
        
        by_type = defaultdict(int)
        by_severity = defaultdict(int)
        
        for alert in self.alert_history:
            by_type[alert.alert_type.value] += 1
            by_severity[alert.severity.value] += 1
        
        return {
            'total_alerts': len(self.alert_history),
            'by_type': dict(by_type),
            'by_severity': dict(by_severity),
            'last_alert_time': self.alert_history[-1].timestamp.isoformat()
        }
    
    def reset(self) -> None:
        """Reset engine state."""
        self.last_alert_times.clear()
        self.alert_history.clear()
        self.frame_number = 0
        logger.info("RiskEngine reset")


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    
    engine = RiskEngine(frame_rate=30, enable_deduplication=True, vietnamese_mode=True)
    print("Risk Engine initialized successfully")
    
    # Simulate risk assessment
    lane_output = {'offset': 0.6, 'direction': 'LEFT', 'left_confidence': 0.8, 'right_confidence': 0.85}
    tracked_objects = [
        {'class_name': 'car', 'distance': 5.0, 'ttc': 0.8, 'is_approaching': True, 'closing_speed': 6.0, 'risk_level': 'CRITICAL'}
    ]
    driver_output = {'should_alert': True, 'drowsy_confidence': 0.8, 'drowsy_reason': 'EYES_CLOSED', 'smoothed_ear': 0.2, 'smoothed_mar': 0.4}
    context_state = {
        'sustained_lane_departure': True,
        'lane_stability_score': 0.6,
        'driver_alertness_score': 0.4
    }
    
    alerts = engine.assess_all_risks(lane_output, tracked_objects, driver_output, context_state)
    
    print(f"\nGenerated {len(alerts)} alerts:")
    for alert in alerts:
        print(f"  [{alert.severity.value}] {alert.alert_type.value}: {alert.message_vi}")
        print(f"      Risk Score: {alert.risk_score:.2f}")
    
    stats = engine.get_alert_statistics()
    print(f"\nAlert Statistics: {stats}")
