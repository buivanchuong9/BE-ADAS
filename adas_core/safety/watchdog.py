"""
System Watchdog - Monitors all ADAS components for failures
ISO 26262 requirement: Runtime monitoring and fault detection

Purpose:
- Monitor critical components (sensors, perception, planning, control)
- Detect failures, freezes, and degraded performance
- Trigger fail-safe actions when needed
- Log all safety events for post-analysis

Design:
- Independent watchdog thread
- Heartbeat mechanism for each component
- Timeout detection (component frozen/crashed)
- Health score calculation
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
import logging


class ComponentStatus(Enum):
    """Component operational status"""
    HEALTHY = "healthy"      # All checks passing
    DEGRADED = "degraded"    # Partial functionality
    FAILED = "failed"        # Complete failure
    TIMEOUT = "timeout"      # Watchdog timeout (frozen)
    UNKNOWN = "unknown"      # Not initialized


@dataclass
class ComponentHealth:
    """Health information for one component"""
    component_name: str
    status: ComponentStatus
    last_heartbeat: datetime
    timeout_threshold_ms: float
    error_count: int = 0
    health_score: float = 1.0  # [0.0-1.0]
    metadata: Dict[str, any] = field(default_factory=dict)
    
    def is_alive(self) -> bool:
        """Check if component is responding"""
        elapsed_ms = (datetime.now() - self.last_heartbeat).total_seconds() * 1000
        return elapsed_ms < self.timeout_threshold_ms
    
    def update_health_score(self) -> None:
        """
        Calculate health score based on status and error count
        
        Score factors:
        - Status: healthy=1.0, degraded=0.6, failed=0.0
        - Errors: Decrement by 0.1 per error (capped at 0.0)
        """
        # Base score from status
        status_scores = {
            ComponentStatus.HEALTHY: 1.0,
            ComponentStatus.DEGRADED: 0.6,
            ComponentStatus.FAILED: 0.0,
            ComponentStatus.TIMEOUT: 0.0,
            ComponentStatus.UNKNOWN: 0.5,
        }
        base_score = status_scores.get(self.status, 0.5)
        
        # Penalty for errors
        error_penalty = min(0.5, self.error_count * 0.1)
        
        self.health_score = max(0.0, base_score - error_penalty)


class SystemWatchdog:
    """
    System-level watchdog timer
    
    Monitors all ADAS components and triggers fail-safe if critical failures detected
    
    Features:
    - Per-component timeout monitoring
    - Heartbeat mechanism
    - Automatic failure detection
    - Health score aggregation
    - Safety event logging
    
    Usage:
        watchdog = SystemWatchdog(check_interval_ms=100)
        watchdog.register_component("camera", timeout_ms=500)
        watchdog.register_component("perception", timeout_ms=200)
        watchdog.start()
        
        # Components send heartbeats
        watchdog.heartbeat("camera", status=ComponentStatus.HEALTHY)
    """
    
    def __init__(
        self,
        check_interval_ms: float = 100,
        failure_callback: Optional[Callable] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize system watchdog
        
        Args:
            check_interval_ms: How often to check components (default: 100ms)
            failure_callback: Function called when critical failure detected
            logger: Custom logger (creates default if None)
        """
        self.check_interval = check_interval_ms / 1000.0  # Convert to seconds
        self.failure_callback = failure_callback
        self.logger = logger or self._create_logger()
        
        # Component registry
        self._components: Dict[str, ComponentHealth] = {}
        self._lock = threading.Lock()
        
        # Watchdog thread
        self._running = False
        self._watchdog_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._check_count = 0
        self._failure_count = 0
        self._last_check_time = None
    
    def register_component(
        self,
        name: str,
        timeout_ms: float,
        critical: bool = False
    ) -> None:
        """
        Register a component for monitoring
        
        Args:
            name: Component identifier
            timeout_ms: Max time between heartbeats before timeout
            critical: If True, timeout triggers fail-safe
        """
        with self._lock:
            self._components[name] = ComponentHealth(
                component_name=name,
                status=ComponentStatus.UNKNOWN,
                last_heartbeat=datetime.now(),
                timeout_threshold_ms=timeout_ms,
                metadata={'critical': critical}
            )
            self.logger.info(f"Registered component: {name} (timeout: {timeout_ms}ms, critical: {critical})")
    
    def heartbeat(
        self,
        component_name: str,
        status: ComponentStatus = ComponentStatus.HEALTHY,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Receive heartbeat from component
        
        Args:
            component_name: Component sending heartbeat
            status: Current component status
            metadata: Additional diagnostic data
        """
        with self._lock:
            if component_name not in self._components:
                self.logger.warning(f"Heartbeat from unregistered component: {component_name}")
                return
            
            comp = self._components[component_name]
            comp.last_heartbeat = datetime.now()
            comp.status = status
            
            if metadata:
                comp.metadata.update(metadata)
            
            # Update health score
            comp.update_health_score()
    
    def start(self) -> None:
        """Start watchdog monitoring thread"""
        if self._running:
            self.logger.warning("Watchdog already running")
            return
        
        self._running = True
        self._watchdog_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._watchdog_thread.start()
        self.logger.info("✅ System watchdog started")
    
    def stop(self) -> None:
        """Stop watchdog monitoring"""
        if not self._running:
            return
        
        self._running = False
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=1.0)
        self.logger.info("System watchdog stopped")
    
    def get_system_health(self) -> float:
        """
        Calculate overall system health score
        
        Returns:
            Aggregate health score [0.0-1.0]
            
        Algorithm: Weighted average (critical components have 2x weight)
        """
        with self._lock:
            if not self._components:
                return 0.0
            
            total_weight = 0
            weighted_sum = 0
            
            for comp in self._components.values():
                weight = 2.0 if comp.metadata.get('critical', False) else 1.0
                weighted_sum += comp.health_score * weight
                total_weight += weight
            
            return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def get_component_status(self, component_name: str) -> Optional[ComponentStatus]:
        """Get status of specific component"""
        with self._lock:
            comp = self._components.get(component_name)
            return comp.status if comp else None
    
    def get_diagnostics(self) -> Dict[str, any]:
        """
        Get comprehensive diagnostic report
        
        Returns:
            Dictionary containing:
            - system_health: Overall health score
            - components: Per-component health
            - statistics: Watchdog statistics
        """
        with self._lock:
            return {
                'system_health': self.get_system_health(),
                'components': {
                    name: {
                        'status': comp.status.value,
                        'health_score': comp.health_score,
                        'last_heartbeat': comp.last_heartbeat.isoformat(),
                        'is_alive': comp.is_alive(),
                        'error_count': comp.error_count,
                    }
                    for name, comp in self._components.items()
                },
                'statistics': {
                    'check_count': self._check_count,
                    'failure_count': self._failure_count,
                    'uptime_seconds': (datetime.now() - self._last_check_time).total_seconds()
                    if self._last_check_time else 0,
                }
            }
    
    # === Private methods ===
    
    def _monitoring_loop(self) -> None:
        """
        Main watchdog monitoring loop
        Runs in separate thread
        """
        self._last_check_time = datetime.now()
        
        while self._running:
            try:
                self._check_all_components()
                self._check_count += 1
                
                # Sleep until next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Watchdog error: {e}")
    
    def _check_all_components(self) -> None:
        """Check all registered components for timeouts"""
        with self._lock:
            critical_failure = False
            
            for name, comp in self._components.items():
                # Check if component timed out
                if not comp.is_alive() and comp.status != ComponentStatus.TIMEOUT:
                    # Component timeout detected
                    self.logger.error(f"⚠️ TIMEOUT: Component '{name}' not responding")
                    comp.status = ComponentStatus.TIMEOUT
                    comp.error_count += 1
                    comp.update_health_score()
                    self._failure_count += 1
                    
                    # Check if critical component failed
                    if comp.metadata.get('critical', False):
                        critical_failure = True
            
            # Trigger fail-safe if critical component failed
            if critical_failure and self.failure_callback:
                self.logger.critical("🚨 CRITICAL FAILURE - Triggering fail-safe")
                self.failure_callback(self.get_diagnostics())
    
    def _create_logger(self) -> logging.Logger:
        """Create default logger"""
        logger = logging.getLogger("SystemWatchdog")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
