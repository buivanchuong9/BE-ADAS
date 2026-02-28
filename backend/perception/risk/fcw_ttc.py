from dataclasses import dataclass
from typing import Tuple
import math


# FCW States
FCW_SAFE = "SAFE"
FCW_WARNING = "WARNING"  
FCW_COLLISION_RISK = "COLLISION RISK"

# Vietnamese translations
FCW_STATE_VI = {
    FCW_SAFE: "AN TOÀN",
    FCW_WARNING: "CẢNH BÁO",
    FCW_COLLISION_RISK: "NGUY HIỂM",
}

# TTC Thresholds (seconds)
TTC_CRITICAL = 1.0   # < 1.0s → COLLISION RISK
TTC_WARNING = 2.0    # < 2.0s → WARNING
                     # >= 2.0s → SAFE


@dataclass
class FCWResult:
    """Result of FCW computation."""
    ttc: float              # Time-to-collision in seconds
    state: str              # FCW state (SAFE/WARNING/COLLISION RISK)
    state_vi: str           # Vietnamese translation
    distance: float         # Input distance in meters
    ego_speed_kmh: float    # Input ego speed in km/h
    ego_speed_ms: float     # Ego speed in m/s
    reason: str             # Human-readable explanation (Vietnamese)
    reason_en: str          # English explanation


def compute_fcw(distance: float, ego_speed_kmh: float) -> FCWResult:
    """
    Compute Forward Collision Warning based on TTC.
    
    Args:
        distance: Distance to object in meters
        ego_speed_kmh: Ego vehicle speed in km/h
        
    Returns:
        FCWResult with TTC, state, and explanation
    """
    # Convert km/h to m/s
    ego_speed_ms = ego_speed_kmh / 3.6
    
    # Handle edge case: stationary vehicle
    if ego_speed_ms <= 0.1:  # Essentially stopped
        return FCWResult(
            ttc=float('inf'),
            state=FCW_SAFE,
            state_vi=FCW_STATE_VI[FCW_SAFE],
            distance=distance,
            ego_speed_kmh=ego_speed_kmh,
            ego_speed_ms=ego_speed_ms,
            reason="Xe đang dừng, không có nguy cơ va chạm",
            reason_en="Vehicle stopped, no collision risk"
        )
    
    # Compute TTC
    # Assumption: relative_speed ≈ ego_speed (worst case: object is stationary)
    ttc = distance / ego_speed_ms
    
    # Clamp unrealistic values
    ttc = max(0.0, min(ttc, 999.0))
    
    # Determine FCW state
    if ttc < TTC_CRITICAL:
        state = FCW_COLLISION_RISK
        reason = f"TTC={ttc:.2f}s < {TTC_CRITICAL}s, cần phanh ngay lập tức!"
        reason_en = f"TTC={ttc:.2f}s < {TTC_CRITICAL}s, immediate braking required!"
    elif ttc < TTC_WARNING:
        state = FCW_WARNING
        reason = f"TTC={ttc:.2f}s ({TTC_CRITICAL}-{TTC_WARNING}s), chuẩn bị phanh"
        reason_en = f"TTC={ttc:.2f}s ({TTC_CRITICAL}-{TTC_WARNING}s), prepare to brake"
    else:
        state = FCW_SAFE
        reason = f"TTC={ttc:.2f}s >= {TTC_WARNING}s, khoảng cách an toàn"
        reason_en = f"TTC={ttc:.2f}s >= {TTC_WARNING}s, safe distance"
    
    return FCWResult(
        ttc=ttc,
        state=state,
        state_vi=FCW_STATE_VI[state],
        distance=distance,
        ego_speed_kmh=ego_speed_kmh,
        ego_speed_ms=ego_speed_ms,
        reason=reason,
        reason_en=reason_en
    )


def compute_fcw_simple(distance: float, ego_speed_kmh: float) -> Tuple[float, str, str]:
    """
    Simplified FCW computation returning tuple.
    
    Args:
        distance: Distance to object in meters
        ego_speed_kmh: Ego vehicle speed in km/h
        
    Returns:
        Tuple of (ttc, state, reason_vi)
    """
    result = compute_fcw(distance, ego_speed_kmh)
    return result.ttc, result.state, result.reason


def get_fcw_color(state: str) -> Tuple[int, int, int]:
    """Get BGR color for FCW state (for OpenCV visualization)."""
    colors = {
        FCW_SAFE: (0, 255, 0),           # Green
        FCW_WARNING: (0, 165, 255),      # Orange
        FCW_COLLISION_RISK: (0, 0, 255), # Red
    }
    return colors.get(state, (255, 255, 255))


def get_fcw_color_rgba(state: str) -> Tuple[int, int, int, int]:
    """Get RGBA color for FCW state (for PIL visualization)."""
    colors = {
        FCW_SAFE: (0, 255, 0, 255),           # Green
        FCW_WARNING: (255, 165, 0, 255),      # Orange
        FCW_COLLISION_RISK: (255, 0, 0, 255), # Red
    }
    return colors.get(state, (255, 255, 255, 255))


# ============================================================
# SIMULATION TEST
# ============================================================

def test_fcw():
    """
    Test FCW with the required scenarios.
    
    Expected results:
    - distance=19m, speed=30km/h → SAFE (TTC=2.28s)
    - distance=19m, speed=60km/h → WARNING (TTC=1.14s)
    - distance=19m, speed=80km/h → COLLISION RISK (TTC=0.86s)
    """
    print("=" * 60)
    print("FCW (Forward Collision Warning) - TTC-based System Test")
    print("=" * 60)
    
    test_cases = [
        (19.0, 30.0, FCW_SAFE),
        (19.0, 60.0, FCW_WARNING),
        (19.0, 80.0, FCW_COLLISION_RISK),
        (10.0, 50.0, FCW_COLLISION_RISK),   # TTC = 10/(50/3.6) = 0.72s < 1.0s
        (5.0, 60.0, FCW_COLLISION_RISK),    # TTC = 5/(60/3.6) = 0.30s < 1.0s
        (30.0, 40.0, FCW_SAFE),             # TTC = 30/(40/3.6) = 2.70s >= 2.0s
        (15.0, 0.0, FCW_SAFE),              # Edge case: stopped
        (25.0, 50.0, FCW_WARNING),          # TTC = 25/(50/3.6) = 1.80s (1.0-2.0s)
    ]
    
    all_pass = True
    for dist, speed, expected in test_cases:
        result = compute_fcw(dist, speed)
        status = "✓" if result.state == expected else "✗"
        if result.state != expected:
            all_pass = False
        
        print(f"\n{status} Distance={dist:.1f}m, Speed={speed:.1f}km/h")
        print(f"  → TTC={result.ttc:.2f}s")
        print(f"  → State: {result.state} ({result.state_vi})")
        print(f"  → Reason: {result.reason}")
        print(f"  → Expected: {expected}")
    
    print("\n" + "=" * 60)
    print(f"TEST RESULT: {'ALL PASS ✓' if all_pass else 'SOME FAILED ✗'}")
    print("=" * 60)
    
    return all_pass


if __name__ == '__main__':
    test_fcw()
