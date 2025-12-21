"""
RISK ASSESSMENT MODULE
======================
Evaluates overall driving risk based on multiple perception inputs.

Combines:
- Lane departure risk
- Collision risk (distance + TTC)
- Driver drowsiness
- Traffic signs

Outputs unified risk level for system decision-making.

Author: Senior ADAS Engineer
Date: 2025-12-21
"""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class RiskAssessor:
    """
    Unified risk assessment for ADAS system.
    Combines multiple risk factors into overall risk level.
    """
    
    # Risk weights
    WEIGHTS = {
        'collision': 0.4,      # Highest priority
        'lane_departure': 0.25,
        'driver_state': 0.25,
        'traffic_sign': 0.1
    }
    
    def __init__(self):
        """Initialize risk assessor."""
        logger.info("RiskAssessor initialized")
    
    def assess(
        self,
        collision_risk: Optional[str] = None,
        lane_departure: bool = False,
        driver_drowsy: bool = False,
        critical_sign: bool = False
    ) -> Dict:
        """
        Assess overall driving risk.
        
        Args:
            collision_risk: "SAFE", "CAUTION", or "DANGER"
            lane_departure: Boolean lane departure flag
            driver_drowsy: Boolean drowsiness flag
            critical_sign: Boolean critical traffic sign flag
            
        Returns:
            Dict with:
                - overall_risk: "SAFE", "CAUTION", or "DANGER"
                - risk_score: 0.0-1.0
                - factors: List of active risk factors
        """
        risk_score = 0.0
        factors = []
        
        # Collision risk
        if collision_risk == "DANGER":
            risk_score += self.WEIGHTS['collision'] * 1.0
            factors.append("COLLISION_DANGER")
        elif collision_risk == "CAUTION":
            risk_score += self.WEIGHTS['collision'] * 0.5
            factors.append("COLLISION_CAUTION")
        
        # Lane departure
        if lane_departure:
            risk_score += self.WEIGHTS['lane_departure']
            factors.append("LANE_DEPARTURE")
        
        # Driver state
        if driver_drowsy:
            risk_score += self.WEIGHTS['driver_state']
            factors.append("DRIVER_DROWSY")
        
        # Traffic sign
        if critical_sign:
            risk_score += self.WEIGHTS['traffic_sign']
            factors.append("CRITICAL_SIGN")
        
        # Determine overall risk level
        if risk_score >= 0.7:
            overall_risk = "DANGER"
        elif risk_score >= 0.3:
            overall_risk = "CAUTION"
        else:
            overall_risk = "SAFE"
        
        return {
            "overall_risk": overall_risk,
            "risk_score": float(risk_score),
            "factors": factors
        }


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)
    assessor = RiskAssessor()
    
    # Test case: collision danger + lane departure
    result = assessor.assess(
        collision_risk="DANGER",
        lane_departure=True,
        driver_drowsy=False,
        critical_sign=False
    )
    print(f"Test result: {result}")
