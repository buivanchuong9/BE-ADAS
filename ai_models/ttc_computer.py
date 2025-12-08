"""
TTC (Time-to-Collision) Computer
Tính toán thời gian va chạm dựa trên distance và relative speed
"""
import numpy as np
from typing import Dict, Any, List, Optional


class TTCComputer:
    """
    Time-to-Collision Computer
    
    TTC = distance / relative_speed
    
    Severity levels:
    - critical: TTC < 1s
    - high: 1s <= TTC < 3s
    - medium: 3s <= TTC < 6s
    - low: TTC >= 6s
    """
    
    def __init__(self):
        self.severity_thresholds = {
            'critical': 1.0,  # < 1s
            'high': 3.0,      # 1-3s
            'medium': 6.0,    # 3-6s
            'low': float('inf')  # >= 6s
        }
    
    def compute_ttc(
        self,
        distance: float,
        relative_speed: float,
        previous_distance: Optional[float] = None,
        time_delta: float = 0.1
    ) -> Dict[str, Any]:
        """
        Compute TTC and severity
        
        Args:
            distance: Distance to object (meters)
            relative_speed: Relative speed (m/s, positive = approaching)
            previous_distance: Previous distance for speed estimation
            time_delta: Time between measurements (seconds)
        
        Returns:
            {
                "ttc": float,
                "severity": str,
                "distance": float,
                "relative_speed": float,
                "warning": str
            }
        """
        
        # Estimate relative speed from distance change if not provided
        if relative_speed is None or relative_speed == 0:
            if previous_distance is not None and time_delta > 0:
                # Speed = distance change / time
                distance_change = previous_distance - distance
                relative_speed = distance_change / time_delta
            else:
                relative_speed = 0
        
        # Compute TTC
        if relative_speed > 0:  # Approaching
            ttc = distance / relative_speed
        else:
            ttc = float('inf')  # Not approaching or moving away
        
        # Determine severity
        severity = self._get_severity(ttc)
        
        # Generate warning message
        warning = self._generate_warning(ttc, severity, distance)
        
        return {
            "ttc": round(ttc, 2) if ttc != float('inf') else None,
            "severity": severity,
            "distance": round(distance, 2),
            "relative_speed": round(relative_speed, 2),
            "warning": warning,
            "safe": severity in ['low', 'medium']
        }
    
    def _get_severity(self, ttc: float) -> str:
        """
        Get severity level based on TTC
        """
        if ttc < self.severity_thresholds['critical']:
            return 'critical'
        elif ttc < self.severity_thresholds['high']:
            return 'high'
        elif ttc < self.severity_thresholds['medium']:
            return 'medium'
        else:
            return 'low'
    
    def _generate_warning(self, ttc: float, severity: str, distance: float) -> str:
        """
        Generate warning message
        """
        if severity == 'critical':
            return f"⚠️ NGUY HIỂM! Xe phía trước cực gần! Khoảng cách {distance:.1f}m, va chạm sau {ttc:.1f}s!"
        elif severity == 'high':
            return f"⚠️ Cảnh báo! Xe phía trước đang tiến gần. Khoảng cách {distance:.1f}m, {ttc:.1f}s."
        elif severity == 'medium':
            return f"⚡ Chú ý! Xe phía trước. Khoảng cách {distance:.1f}m."
        else:
            return f"✓ An toàn. Khoảng cách {distance:.1f}m."
    
    def compute_batch_ttc(
        self,
        vehicles: List[Dict[str, Any]],
        tracking_history: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Compute TTC for multiple vehicles
        
        Args:
            vehicles: List of vehicle detections with distance
            tracking_history: Previous frame tracking data
        
        Returns:
            List of vehicles with TTC info
        """
        results = []
        
        for vehicle in vehicles:
            distance = vehicle.get('distance', 0)
            vehicle_id = vehicle.get('id', None)
            
            # Get previous distance from tracking
            previous_distance = None
            if tracking_history and vehicle_id:
                prev_data = tracking_history.get(vehicle_id, {})
                previous_distance = prev_data.get('distance')
            
            # Compute TTC
            ttc_info = self.compute_ttc(
                distance=distance,
                relative_speed=vehicle.get('relative_speed', 0),
                previous_distance=previous_distance,
                time_delta=0.1  # Assume 10 FPS
            )
            
            # Add TTC info to vehicle
            vehicle_with_ttc = {**vehicle, **ttc_info}
            results.append(vehicle_with_ttc)
        
        return results
    
    def get_most_critical(
        self,
        vehicles_with_ttc: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most critical vehicle (lowest TTC)
        """
        if not vehicles_with_ttc:
            return None
        
        # Filter vehicles with valid TTC
        valid_vehicles = [
            v for v in vehicles_with_ttc 
            if v.get('ttc') is not None and v['ttc'] < float('inf')
        ]
        
        if not valid_vehicles:
            return None
        
        # Find minimum TTC
        return min(valid_vehicles, key=lambda v: v['ttc'])
