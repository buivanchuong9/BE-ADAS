"""
Fail-Safe Manager - ISO 26262 Safe State management
Handles critical failures and transitions system to safe states

Safety states (in order of severity):
1. NORMAL - All systems operational
2. DEGRADED - Some sensors/modules failed, reduced functionality
3. MINIMAL_RISK - Critical failure, minimal operation mode
4. EMERGENCY_STOP - Immediate safe stop required

Fail-safe actions:
- Sensor redundancy switchover
- Reduce speed limits
- Disable advanced features
- Alert driver
- Emergency braking (if control enabled)
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime
import logging


class SafeState(Enum):
    """ISO 26262 safe states for ADAS system"""
    NORMAL = "normal"              # Full functionality
    DEGRADED = "degraded"          # Partial functionality, warnings active
    MINIMAL_RISK = "minimal_risk"  # Minimal operation, prepare for stop
    EMERGENCY_STOP = "emergency_stop"  # Immediate safe stop


class FailSafeAction(Enum):
    """Actions to take when entering safe states"""
    # DEGRADED state actions
    SWITCH_TO_BACKUP_SENSOR = "switch_backup_sensor"
    REDUCE_SPEED_LIMIT = "reduce_speed_limit"
    DISABLE_LANE_KEEPING = "disable_lane_keeping"
    DISABLE_ACC = "disable_acc"
    ALERT_DRIVER_WARNING = "alert_driver_warning"
    
    # MINIMAL_RISK state actions
    REDUCE_TO_MIN_SPEED = "reduce_min_speed"
    DISABLE_ALL_ADAS = "disable_all_adas"
    ALERT_DRIVER_CRITICAL = "alert_driver_critical"
    ACTIVATE_HAZARD_LIGHTS = "activate_hazard_lights"
    
    # EMERGENCY_STOP actions
    EMERGENCY_BRAKE = "emergency_brake"
    ALERT_DRIVER_EMERGENCY = "alert_driver_emergency"
    LOG_BLACK_BOX = "log_black_box"


@dataclass
class FailSafeEvent:
    """Record of a fail-safe event"""
    timestamp: datetime
    trigger: str  # What triggered fail-safe
    from_state: SafeState
    to_state: SafeState
    actions_taken: List[FailSafeAction]
    diagnostics: Dict[str, Any]


class FailSafeManager:
    """
    Manages safe state transitions and fail-safe actions
    
    Responsibilities:
    - Monitor system health
    - Determine appropriate safe state
    - Execute fail-safe actions
    - Log safety events
    - Provide driver alerts
    
    Safety requirements:
    - State transitions follow safety hierarchy
    - All actions logged for auditing
    - Driver notified of all state changes
    - Automatic recovery when possible
    """
    
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        action_handlers: Optional[Dict[FailSafeAction, Callable]] = None
    ):
        """
        Initialize fail-safe manager
        
        Args:
            logger: Custom logger
            action_handlers: Dictionary mapping actions to handler functions
        """
        self.logger = logger or self._create_logger()
        self.action_handlers = action_handlers or {}
        
        # Current safe state
        self._current_state = SafeState.NORMAL
        
        # Event history
        self._event_history: List[FailSafeEvent] = []
        
        # Safety thresholds (configurable)
        self.config = {
            'health_threshold_degraded': 0.7,    # Enter DEGRADED if health < 0.7
            'health_threshold_minimal': 0.4,      # Enter MINIMAL_RISK if health < 0.4
            'critical_sensor_required': True,     # Require at least 1 critical sensor
            'max_degraded_time_sec': 300,         # Max time in DEGRADED before escalating
        }
    
    def evaluate_system_health(self, health_score: float, diagnostics: Dict[str, Any]) -> None:
        """
        Evaluate system health and transition to appropriate safe state
        
        Args:
            health_score: Overall system health [0.0-1.0]
            diagnostics: Detailed diagnostic data from watchdog
            
        State transition logic:
        - health >= 0.7: NORMAL
        - 0.4 <= health < 0.7: DEGRADED
        - 0.2 <= health < 0.4: MINIMAL_RISK
        - health < 0.2: EMERGENCY_STOP
        """
        # Determine target state based on health
        target_state = self._determine_safe_state(health_score, diagnostics)
        
        # Transition if needed
        if target_state != self._current_state:
            self._transition_to_state(target_state, diagnostics)
    
    def trigger_emergency_stop(self, reason: str, diagnostics: Dict[str, Any]) -> None:
        """
        Force immediate emergency stop
        
        Args:
            reason: Description of emergency condition
            diagnostics: Current system diagnostics
        """
        self.logger.critical(f"🚨 EMERGENCY STOP TRIGGERED: {reason}")
        self._transition_to_state(SafeState.EMERGENCY_STOP, diagnostics, trigger=reason)
    
    def request_recovery(self) -> bool:
        """
        Attempt to recover to higher safe state
        
        Returns:
            True if recovery successful
        """
        if self._current_state == SafeState.NORMAL:
            return True  # Already in best state
        
        # Check if conditions improved
        # In real system, re-evaluate health here
        
        # For now, don't auto-recover (require manual intervention)
        self.logger.info("Recovery requested - manual intervention required")
        return False
    
    def get_current_state(self) -> SafeState:
        """Get current safe state"""
        return self._current_state
    
    def get_event_history(self) -> List[FailSafeEvent]:
        """Get history of fail-safe events"""
        return self._event_history.copy()
    
    def get_allowed_features(self) -> Dict[str, bool]:
        """
        Get which ADAS features are allowed in current state
        
        Returns:
            Dictionary of feature_name -> enabled (bool)
        """
        # Define features allowed in each state
        feature_matrix = {
            SafeState.NORMAL: {
                'adaptive_cruise_control': True,
                'lane_keeping_assist': True,
                'collision_warning': True,
                'automatic_braking': True,
                'traffic_sign_recognition': True,
            },
            SafeState.DEGRADED: {
                'adaptive_cruise_control': False,  # Disabled
                'lane_keeping_assist': False,      # Disabled
                'collision_warning': True,         # Keep warnings
                'automatic_braking': True,         # Keep safety feature
                'traffic_sign_recognition': True,
            },
            SafeState.MINIMAL_RISK: {
                'adaptive_cruise_control': False,
                'lane_keeping_assist': False,
                'collision_warning': True,
                'automatic_braking': True,  # Only critical safety
                'traffic_sign_recognition': False,
            },
            SafeState.EMERGENCY_STOP: {
                'adaptive_cruise_control': False,
                'lane_keeping_assist': False,
                'collision_warning': False,
                'automatic_braking': True,  # Emergency brake only
                'traffic_sign_recognition': False,
            },
        }
        
        return feature_matrix.get(self._current_state, {})
    
    # === Private methods ===
    
    def _determine_safe_state(self, health_score: float, diagnostics: Dict[str, Any]) -> SafeState:
        """
        Determine appropriate safe state based on health
        
        Args:
            health_score: System health [0.0-1.0]
            diagnostics: System diagnostics
            
        Returns:
            Recommended safe state
        """
        # Check for critical sensor failures
        has_critical_sensor = self._has_critical_sensor(diagnostics)
        
        # Emergency stop conditions
        if health_score < 0.2 or not has_critical_sensor:
            return SafeState.EMERGENCY_STOP
        
        # Minimal risk conditions
        if health_score < self.config['health_threshold_minimal']:
            return SafeState.MINIMAL_RISK
        
        # Degraded conditions
        if health_score < self.config['health_threshold_degraded']:
            return SafeState.DEGRADED
        
        # Normal operation
        return SafeState.NORMAL
    
    def _transition_to_state(
        self,
        target_state: SafeState,
        diagnostics: Dict[str, Any],
        trigger: str = "health_evaluation"
    ) -> None:
        """
        Transition to new safe state and execute required actions
        
        Args:
            target_state: Target safe state
            diagnostics: Current diagnostics
            trigger: What triggered the transition
        """
        old_state = self._current_state
        
        self.logger.warning(
            f"⚠️ SAFE STATE TRANSITION: {old_state.value} → {target_state.value} (trigger: {trigger})"
        )
        
        # Determine actions to take
        actions = self._get_actions_for_state(target_state)
        
        # Execute actions
        for action in actions:
            self._execute_action(action, diagnostics)
        
        # Update state
        self._current_state = target_state
        
        # Log event
        event = FailSafeEvent(
            timestamp=datetime.now(),
            trigger=trigger,
            from_state=old_state,
            to_state=target_state,
            actions_taken=actions,
            diagnostics=diagnostics
        )
        self._event_history.append(event)
        
        self.logger.info(f"✅ Transitioned to {target_state.value} - {len(actions)} actions executed")
    
    def _get_actions_for_state(self, state: SafeState) -> List[FailSafeAction]:
        """Get list of actions to execute for a safe state"""
        action_map = {
            SafeState.DEGRADED: [
                FailSafeAction.REDUCE_SPEED_LIMIT,
                FailSafeAction.ALERT_DRIVER_WARNING,
            ],
            SafeState.MINIMAL_RISK: [
                FailSafeAction.REDUCE_TO_MIN_SPEED,
                FailSafeAction.DISABLE_ALL_ADAS,
                FailSafeAction.ALERT_DRIVER_CRITICAL,
                FailSafeAction.ACTIVATE_HAZARD_LIGHTS,
            ],
            SafeState.EMERGENCY_STOP: [
                FailSafeAction.EMERGENCY_BRAKE,
                FailSafeAction.ALERT_DRIVER_EMERGENCY,
                FailSafeAction.LOG_BLACK_BOX,
            ],
        }
        
        return action_map.get(state, [])
    
    def _execute_action(self, action: FailSafeAction, context: Dict[str, Any]) -> None:
        """
        Execute a fail-safe action
        
        Args:
            action: Action to execute
            context: Diagnostic context
        """
        self.logger.info(f"  Executing action: {action.value}")
        
        # Call registered handler if available
        if action in self.action_handlers:
            try:
                self.action_handlers[action](context)
            except Exception as e:
                self.logger.error(f"  Action handler failed: {e}")
        else:
            # Default handlers (logging only)
            self._default_action_handler(action, context)
    
    def _default_action_handler(self, action: FailSafeAction, context: Dict[str, Any]) -> None:
        """Default action handler (logs only)"""
        action_messages = {
            FailSafeAction.ALERT_DRIVER_WARNING: "⚠️ WARNING: System degraded, reduced functionality",
            FailSafeAction.ALERT_DRIVER_CRITICAL: "🚨 CRITICAL: System failure, take manual control immediately",
            FailSafeAction.ALERT_DRIVER_EMERGENCY: "🆘 EMERGENCY: System shutdown, stopping vehicle",
            FailSafeAction.REDUCE_SPEED_LIMIT: "Reducing speed limit to 40 km/h",
            FailSafeAction.REDUCE_TO_MIN_SPEED: "Reducing speed to minimal (20 km/h)",
            FailSafeAction.DISABLE_ALL_ADAS: "Disabling all ADAS features",
            FailSafeAction.EMERGENCY_BRAKE: "⚠️ EMERGENCY BRAKING ACTIVATED",
            FailSafeAction.LOG_BLACK_BOX: "Logging black box data for analysis",
        }
        
        message = action_messages.get(action, f"Executing {action.value}")
        self.logger.warning(f"  → {message}")
    
    def _has_critical_sensor(self, diagnostics: Dict[str, Any]) -> bool:
        """
        Check if at least one critical sensor is healthy
        
        Args:
            diagnostics: System diagnostics from watchdog
            
        Returns:
            True if at least one critical sensor available
        """
        components = diagnostics.get('components', {})
        
        for comp_name, comp_data in components.items():
            if comp_data.get('metadata', {}).get('critical', False):
                if comp_data.get('is_alive', False):
                    return True
        
        return False
    
    def _create_logger(self) -> logging.Logger:
        """Create default logger"""
        logger = logging.getLogger("FailSafeManager")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
