"""
RISK ENGINE V4 — Ego Danger Zone + TTC-based Collision Warning
==============================================================
Production risk assessment for ADAS V4.

Key features:
  1. Ego Danger Zone Polygon — trapezoidal zone projected ahead of vehicle.
     Any tracked object whose bbox bottom-center enters this zone triggers
     FCW assessment regardless of TTC (spatial proximity check).

  2. TTC-based Risk Levels (spec-mandated):
        SAFE      : TTC > 5 s  (or object not approaching)
        WARNING   : TTC ≤ 4 s
        DANGER    : TTC ≤ 2 s  (same as CRITICAL in spec)
        CRITICAL  : TTC ≤ 1 s  (additional sub-level for overlay flash)

  3. Lane Departure Warning — uses LaneDetectorV4's lane_offset [-1, +1].

  4. Alert deduplication with per-type cooldowns.

  5. Returns structured RiskResultV4 with Vietnamese messages ready to
     pass directly to VietnameseOverlayRenderer.

Author  : Senior ADAS Engineer — V4 Architecture
Version : 4.0.0
Date    : 2026-02-25
"""

import numpy as np
import cv2
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque
import time

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class RiskResultV4:
    """Single-frame risk assessment result from RiskEngineV4."""

    # Overall scene risk level
    scene_risk : str = 'SAFE'       # 'SAFE' | 'WARNING' | 'DANGER' | 'CRITICAL'
    scene_score: float = 0.0        # 0.0 – 1.0

    # Per-alert flags (prioritised list, highest severity first)
    alerts: List[Dict] = field(default_factory=list)

    # Danger zone
    danger_zone_pts: Optional[np.ndarray] = None   # Polygon in image space (N,2)
    objects_in_zone: List[Dict] = field(default_factory=list)

    # Closest threat
    closest_vehicle : Optional[Dict] = None
    closest_distance: float = float('inf')
    closest_ttc     : Optional[float] = None

    # Lane departure
    lane_offset      : float = 0.0          # from LaneDetectorV4
    lane_offset_level: str   = 'SAFE'       # SAFE | WARNING | CRITICAL
    ldw_active       : bool  = False

    # Vietnamese warning text (for VietnameseOverlayRenderer)
    primary_warning_vi  : Optional[str] = None
    secondary_warning_vi: Optional[str] = None
    warning_color       : tuple = (255, 255, 255)   # BGR


# ---------------------------------------------------------------------------
# Ego Danger Zone
# ---------------------------------------------------------------------------

class EgoDangerZone:
    """
    Trapezoid danger zone projected ahead of the ego vehicle.

    Defined in image-space as a polygon relative to frame dimensions.
    The zone shape resembles the road ahead:
      - Wide at the bottom (close to camera)
      - Narrow at the top (horizon / far distance)

    Shape is parameterised by ratios of frame W/H so it scales automatically.
    """

    # Ratio-based default trapezoid (tuned for standard dashcam 1280×720)
    # Points: bottom-left, top-left, top-right, bottom-right
    DEFAULT_ZONE = np.float32([
        [0.10, 0.98],   # bottom-left
        [0.36, 0.60],   # top-left  (near horizon)
        [0.64, 0.60],   # top-right
        [0.90, 0.98],   # bottom-right
    ])

    def __init__(
        self,
        frame_w: int = 1280,
        frame_h: int = 720,
        zone_ratios: Optional[np.ndarray] = None,
    ):
        self.frame_w = frame_w
        self.frame_h = frame_h
        self._ratios = zone_ratios if zone_ratios is not None else self.DEFAULT_ZONE
        self._pts    = self._build_pts()

    def _build_pts(self) -> np.ndarray:
        pts = (self._ratios * [self.frame_w, self.frame_h]).astype(np.int32)
        return pts

    def update_resolution(self, w: int, h: int) -> None:
        if w != self.frame_w or h != self.frame_h:
            self.frame_w = w
            self.frame_h = h
            self._pts = self._build_pts()

    @property
    def polygon(self) -> np.ndarray:
        """Returns (N, 2) integer polygon for cv2.fillPoly / pointPolygonTest."""
        return self._pts

    def contains_point(self, px: float, py: float) -> bool:
        """Check whether (px, py) is inside the danger zone polygon."""
        result = cv2.pointPolygonTest(
            self._pts.astype(np.float32),
            (float(px), float(py)),
            measureDist=False
        )
        return result >= 0

    def object_in_zone(self, bbox: List[int]) -> bool:
        """
        Check if an object's bottom-center point lies inside the danger zone.

        Bottom-center is the most ground-level point of a bounding box,
        which corresponds to where the vehicle touches the road.
        """
        x1, y1, x2, y2 = bbox
        bottom_cx = (x1 + x2) / 2.0
        bottom_cy = float(y2)
        return self.contains_point(bottom_cx, bottom_cy)

    def draw(self, frame: np.ndarray, active: bool = False) -> np.ndarray:
        """
        Draw the danger zone on a frame.

        active=True  → fill red (threat detected)
        active=False → outline only (cyan), semi-transparent
        """
        overlay = frame.copy()
        if active:
            cv2.fillPoly(overlay, [self._pts], (0, 0, 80))
            cv2.addWeighted(frame, 0.65, overlay, 0.35, 0, frame)
            cv2.polylines(frame, [self._pts], isClosed=True, color=(0, 0, 220), thickness=2)
        else:
            cv2.polylines(frame, [self._pts], isClosed=True, color=(200, 200, 0), thickness=1)
        return frame


# ---------------------------------------------------------------------------
# TTC smoothing helper
# ---------------------------------------------------------------------------

class TTCSmoother:
    """
    Per-track EMA smoother for TTC to prevent spurious flips.
    """
    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self._state: Dict[int, float] = {}

    def update(self, track_id: int, ttc: Optional[float]) -> Optional[float]:
        if ttc is None:
            return self._state.get(track_id)   # hold last
        if track_id not in self._state:
            self._state[track_id] = ttc
            return ttc
        smoothed = self.alpha * ttc + (1.0 - self.alpha) * self._state[track_id]
        self._state[track_id] = smoothed
        return smoothed

    def purge_stale(self, active_ids: set) -> None:
        stale = [tid for tid in self._state if tid not in active_ids]
        for tid in stale:
            del self._state[tid]


# ---------------------------------------------------------------------------
# Risk Engine V4
# ---------------------------------------------------------------------------

class RiskEngineV4:
    """
    V4 multi-factor risk assessment engine.

    Usage::

        engine = RiskEngineV4(frame_w=1280, frame_h=720)

        result: RiskResultV4 = engine.assess(
            tracked_objects = [...],    # from ByteTracker + DistanceEstimator
            lane_offset      = 0.4,     # from LaneDetectorV4
            lane_offset_level= 'WARNING',
            frame            = frame,   # needed to draw danger zone
            frame_idx        = idx,
        )
    """

    # ── TTC thresholds (spec) ─────────────────────────────────────
    TTC_SAFE     = 5.0   # > 5s  → SAFE
    TTC_WARNING  = 4.0   # ≤ 4s  → WARNING
    TTC_DANGER   = 2.0   # ≤ 2s  → DANGER
    TTC_CRITICAL = 1.0   # ≤ 1s  → CRITICAL (sub-level, flash overlay)

    # ── Distance thresholds (backup when TTC unavailable) ────────
    DIST_SAFE     = 30.0
    DIST_WARNING  = 15.0
    DIST_DANGER   =  7.0
    DIST_CRITICAL =  3.0

    # ── Alert cooldowns (seconds) ─────────────────────────────────
    COOLDOWN = {
        'FCW' : 2.5,
        'LDW' : 4.0,
        'PCW' : 2.0,
        'HMW' : 5.0,
    }

    def __init__(
        self,
        frame_w    : int  = 1280,
        frame_h    : int  = 720,
        fps        : float = 30.0,
        zone_ratios: Optional[np.ndarray] = None,
    ):
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.fps     = fps

        self.danger_zone = EgoDangerZone(frame_w, frame_h, zone_ratios)
        self.ttc_smoother = TTCSmoother(alpha=0.30)

        # Cooldown tracking: alert_type → last trigger wall-clock time
        self._last_triggers: Dict[str, float] = {}

        # Rolling history for voting anti-jitter (last 10 frames)
        self._fcw_votes: deque = deque(maxlen=10)
        self._ldw_votes: deque = deque(maxlen=10)

        logger.info(f"[RiskV4] Initialized — {frame_w}×{frame_h}  fps={fps}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(
        self,
        tracked_objects    : List[Dict],
        lane_offset        : float = 0.0,
        lane_offset_level  : str = 'SAFE',
        frame_w            : int  = 0,
        frame_h            : int  = 0,
        frame_idx          : int  = 0,
    ) -> RiskResultV4:
        """
        Run full risk assessment for one frame.

        Parameters
        ----------
        tracked_objects : list of dicts from ByteTracker + DistanceEstimator
            Expected keys: id, class_name, bbox [x1,y1,x2,y2],
                           distance (m), ttc (s|None), is_approaching,
                           relative_velocity (m/s)
        lane_offset      : float from LaneDetectorV4 (−1..+1)
        lane_offset_level: 'SAFE' | 'WARNING' | 'CRITICAL'
        frame_w/h        : can pass live resolution; 0 = use constructor value

        Returns
        -------
        RiskResultV4 dataclass
        """
        # Update resolution if changed
        fw = frame_w  if frame_w  > 0 else self.frame_w
        fh = frame_h  if frame_h  > 0 else self.frame_h
        self.danger_zone.update_resolution(fw, fh)

        result = RiskResultV4()
        result.danger_zone_pts = self.danger_zone.polygon
        result.lane_offset      = lane_offset
        result.lane_offset_level = lane_offset_level

        # ── 1. Classify each tracked object ──────────────────────────
        classified = []
        active_ids = set()

        for obj in tracked_objects:
            tid  = obj.get('id', -1)
            dist = obj.get('distance', float('inf'))
            raw_ttc = obj.get('ttc')

            active_ids.add(tid)

            # Smooth TTC per track
            smooth_ttc = self.ttc_smoother.update(tid, raw_ttc)
            obj = {**obj, 'ttc_smooth': smooth_ttc}

            # Risk level from smoothed TTC + distance
            risk_level = self._classify_risk(dist, smooth_ttc, obj.get('is_approaching', False))
            obj = {**obj, 'risk_level': risk_level}

            # Zone check
            bbox = obj.get('bbox', [0, 0, 0, 0])
            in_zone = self.danger_zone.object_in_zone(bbox)
            obj = {**obj, 'in_danger_zone': in_zone}
            if in_zone:
                result.objects_in_zone.append(obj)

            classified.append(obj)

        # Purge stale TTC history
        self.ttc_smoother.purge_stale(active_ids)

        # ── 2. Find closest threatening vehicle ───────────────────────
        threats = [o for o in classified if o.get('is_approaching') or o.get('in_danger_zone')]
        if threats:
            closest = min(threats, key=lambda o: o.get('distance', 9999))
        elif classified:
            closest = min(classified, key=lambda o: o.get('distance', 9999))
        else:
            closest = None

        if closest:
            result.closest_vehicle  = closest
            result.closest_distance = closest.get('distance', float('inf'))
            result.closest_ttc      = closest.get('ttc_smooth')

        # ── 3. FCW — Forward Collision Warning ────────────────────────
        fcw_alert = self._assess_fcw(classified, result.objects_in_zone)
        if fcw_alert:
            result.alerts.append(fcw_alert)

        # ── 4. LDW — Lane Departure Warning ───────────────────────────
        ldw_alert = self._assess_ldw(lane_offset, lane_offset_level)
        if ldw_alert:
            result.alerts.append(ldw_alert)
            result.ldw_active = True

        # ── 5. PCW — Pedestrian Collision Warning ─────────────────────
        pcw_alert = self._assess_pcw(classified)
        if pcw_alert:
            result.alerts.append(pcw_alert)

        # ── 6. HMW — Headway Monitoring Warning ───────────────────────
        hmw_alert = self._assess_hmw(classified)
        if hmw_alert:
            result.alerts.append(hmw_alert)

        # ── 7. Aggregate scene risk ────────────────────────────────────
        result.scene_risk, result.scene_score = self._aggregate_scene_risk(result.alerts, classified)

        # ── 8. Build Vietnamese text for overlay ───────────────────────
        self._attach_vietnamese(result)

        return result

    # ------------------------------------------------------------------
    # Individual alert assessors
    # ------------------------------------------------------------------

    def _assess_fcw(
        self,
        objects   : List[Dict],
        in_zone   : List[Dict],
    ) -> Optional[Dict]:
        """Forward Collision Warning (FCW)."""
        vehicles = [o for o in objects if o.get('class_name') in
                    {'car', 'truck', 'bus', 'motorcycle', 'xe tải', 'ô tô', 'xe máy'}]

        if not vehicles:
            return None

        # Prioritise objects in danger zone first; else closest approaching
        candidates = in_zone if in_zone else [o for o in vehicles if o.get('is_approaching')]
        if not candidates:
            candidates = vehicles

        best = min(candidates, key=lambda o: o.get('distance', 9999))
        ttc  = best.get('ttc_smooth')
        dist = best.get('distance', float('inf'))
        risk = best.get('risk_level', 'SAFE')

        if risk in ('SAFE',) and not best.get('in_danger_zone'):
            return None

        # Anti-jitter voting (need 4 / 10 frames)
        vote = 1 if risk in ('WARNING', 'DANGER', 'CRITICAL') or best.get('in_danger_zone') else 0
        self._fcw_votes.append(vote)
        if sum(self._fcw_votes) < 4:
            return None

        if not self._can_trigger('FCW'):
            return None

        ttc_str  = f"{ttc:.1f}s" if ttc is not None else "N/A"
        cls_vn   = self._vn_class(best.get('class_name', ''))

        return {
            'type'     : 'FCW',
            'severity' : risk,
            'message_vi': (
                f"CẢNH BÁO VA CHẠM: {cls_vn} cách {dist:.1f}m  TTC={ttc_str}"
            ),
            'distance' : dist,
            'ttc'      : ttc,
            'object'   : best,
            'color_bgr': self._risk_color(risk),
        }

    def _assess_ldw(self, offset: float, level: str) -> Optional[Dict]:
        """Lane Departure Warning (LDW)."""
        vote = 1 if level in ('WARNING', 'CRITICAL') else 0
        self._ldw_votes.append(vote)
        if sum(self._ldw_votes) < 4:
            return None

        if level == 'SAFE':
            return None

        if not self._can_trigger('LDW'):
            return None

        direction = 'PHẢI' if offset > 0 else 'TRÁI'
        text = f"LỆCH LÀN ĐƯỜNG — ĐANG LỆCH SANG {direction} ({abs(offset):.0%})"

        return {
            'type'      : 'LDW',
            'severity'  : level,
            'message_vi': text,
            'offset'    : offset,
            'direction' : direction,
            'color_bgr' : (0, 200, 255) if level == 'WARNING' else (0, 100, 255),
        }

    def _assess_pcw(self, objects: List[Dict]) -> Optional[Dict]:
        """Pedestrian Collision Warning (PCW)."""
        peds = [o for o in objects
                if o.get('class_name') in {'person', 'người', 'bicycle', 'xe đạp'}
                and o.get('distance', 999) < self.DIST_WARNING]

        if not peds:
            return None

        closest = min(peds, key=lambda o: o.get('distance', 999))
        dist = closest.get('distance', 0)
        risk = closest.get('risk_level', 'SAFE')

        if risk == 'SAFE':
            return None

        if not self._can_trigger('PCW'):
            return None

        return {
            'type'      : 'PCW',
            'severity'  : risk,
            'message_vi': f"NGUY HIỂM! NGƯỜI ĐI BỘ CÁCH {dist:.1f}m",
            'distance'  : dist,
            'object'    : closest,
            'color_bgr' : (0, 50, 255),
        }

    def _assess_hmw(self, objects: List[Dict]) -> Optional[Dict]:
        """Headway Monitoring Warning (HMW) — maintain safe following distance."""
        vehicles = [o for o in objects
                    if o.get('class_name') in
                    {'car', 'truck', 'bus', 'ô tô', 'xe tải', 'xe buýt'}
                    and self.DIST_DANGER < o.get('distance', 999) <= self.DIST_WARNING]

        if not vehicles:
            return None

        if not self._can_trigger('HMW'):
            return None

        closest = min(vehicles, key=lambda o: o.get('distance', 999))
        dist = closest.get('distance', 0)

        return {
            'type'      : 'HMW',
            'severity'  : 'WARNING',
            'message_vi': f"GIỮ KHOẢNG CÁCH AN TOÀN — {dist:.1f}m",
            'distance'  : dist,
            'color_bgr' : (0, 180, 255),   # Orange
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _classify_risk(
        self,
        dist          : float,
        ttc           : Optional[float],
        is_approaching: bool,
    ) -> str:
        """Map distance + TTC to risk level string (spec-mandated thresholds)."""
        # TTC-based (higher priority)
        if ttc is not None and is_approaching:
            if ttc <= self.TTC_CRITICAL:  return 'CRITICAL'
            if ttc <= self.TTC_DANGER:    return 'DANGER'
            if ttc <= self.TTC_WARNING:   return 'WARNING'

        # Distance-based (fallback)
        if dist <= self.DIST_CRITICAL:  return 'CRITICAL'
        if dist <= self.DIST_DANGER:    return 'DANGER'
        if dist <= self.DIST_WARNING:   return 'WARNING'
        return 'SAFE'

    def _aggregate_scene_risk(
        self, alerts: List[Dict], objects: List[Dict]
    ) -> tuple:
        """Combine all alerts into single scene risk level + score."""
        if not alerts and not objects:
            return 'SAFE', 0.0

        ORDER = {'CRITICAL': 4, 'DANGER': 3, 'WARNING': 2, 'SAFE': 1}

        if alerts:
            worst_sev = max(alerts, key=lambda a: ORDER.get(a.get('severity', 'SAFE'), 1))
            level = worst_sev.get('severity', 'SAFE')
        else:
            level = 'SAFE'

        # Score: 0–1 based on closest vehicle distance
        if objects:
            min_dist = min(o.get('distance', 999) for o in objects)
            score = max(0.0, 1.0 - min_dist / self.DIST_SAFE)
        else:
            score = 0.0

        return level, float(score)

    def _attach_vietnamese(self, result: RiskResultV4) -> None:
        """Populate .primary_warning_vi / .secondary_warning_vi / .warning_color."""
        if not result.alerts:
            return

        # Priority order: FCW > PCW > LDW > HMW
        ORDER = {'FCW': 0, 'PCW': 1, 'LDW': 2, 'HMW': 3}
        sorted_alerts = sorted(result.alerts,
                               key=lambda a: ORDER.get(a.get('type', 'HMW'), 99))

        primary = sorted_alerts[0]
        result.primary_warning_vi = primary.get('message_vi', '')
        result.warning_color      = primary.get('color_bgr', (255, 255, 255))

        if len(sorted_alerts) > 1:
            result.secondary_warning_vi = sorted_alerts[1].get('message_vi', '')

    def _can_trigger(self, alert_type: str) -> bool:
        """Cooldown gate — True if enough time has passed since last trigger."""
        cooldown = self.COOLDOWN.get(alert_type, 3.0)
        last = self._last_triggers.get(alert_type, 0.0)
        now  = time.monotonic()
        if now - last >= cooldown:
            self._last_triggers[alert_type] = now
            return True
        return False

    @staticmethod
    def _risk_color(risk_level: str) -> tuple:
        """BGR colour for risk level."""
        return {
            'CRITICAL': (0,   0,  255),    # Red
            'DANGER'  : (0,  80,  255),    # Red-orange
            'WARNING' : (0, 165,  255),    # Orange
            'CAUTION' : (0, 220,  255),    # Yellow-orange
            'SAFE'    : (0, 220,    0),    # Green
        }.get(risk_level, (220, 220, 220))

    @staticmethod
    def _vn_class(class_name: str) -> str:
        return {
            'car'       : 'Ô TÔ',
            'truck'     : 'XE TẢI',
            'bus'       : 'XE BUÝT',
            'motorcycle': 'XE MÁY',
            'bicycle'   : 'XE ĐẠP',
            'person'    : 'NGƯỜI',
        }.get(class_name.lower(), class_name.upper())


# ---------------------------------------------------------------------------
# Standalone smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = RiskEngineV4()

    dummy_objects = [
        {
            'id': 1, 'class_name': 'car',
            'bbox': [500, 400, 750, 600],
            'distance': 6.0, 'ttc': 1.8,
            'is_approaching': True, 'relative_velocity': -3.3,
        },
        {
            'id': 2, 'class_name': 'person',
            'bbox': [600, 420, 660, 600],
            'distance': 4.0, 'ttc': None,
            'is_approaching': False, 'relative_velocity': 0.0,
        },
    ]

    result = engine.assess(dummy_objects, lane_offset=0.45, lane_offset_level='WARNING')

    print(f"Scene risk  : {result.scene_risk}  ({result.scene_score:.2f})")
    print(f"Primary warn: {result.primary_warning_vi}")
    print(f"Secondary   : {result.secondary_warning_vi}")
    print(f"LDW active  : {result.ldw_active}")
    for a in result.alerts:
        print(f"  Alert [{a['type']}] {a['severity']}: {a['message_vi']}")
