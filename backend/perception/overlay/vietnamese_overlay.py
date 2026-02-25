"""
VIETNAMESE OVERLAY RENDERER V4
================================
PIL-based renderer for Vietnamese warning text, Tesla-style HUD, and
bounding-box annotations with distance/TTC labels.

All Vietnamese text rendered with Pillow (not OpenCV) so diacritics are
correct.  Frame is converted cv2 BGR → PIL RGB → draw → back to BGR.

Designed to receive RiskResultV4 from RiskEngineV4 and tracked objects
(with distance/TTC) from DistanceEstimator.

Author  : Senior ADAS Engineer — V4 Architecture
Version : 4.0.0
Date    : 2026-02-25
"""

import cv2
import numpy as np
import os
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Font manager (singleton-ish)
# ---------------------------------------------------------------------------

class FontManager:
    """Load TTF fonts once and cache by (path, size)."""

    _cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
    _fallback: Optional[ImageFont.ImageFont] = None

    # Search paths, first match wins
    FONT_PATHS = [
        Path(__file__).parent.parent.parent / "assets" / "fonts" / "Roboto-Bold.ttf",
        Path("/usr/share/fonts/truetype/roboto/Roboto-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]

    @classmethod
    def load(cls, size: int = 28, bold: bool = True) -> ImageFont.FreeTypeFont:
        key = (str(bold), size)
        if key in cls._cache:
            return cls._cache[key]

        for p in cls.FONT_PATHS:
            if p.exists():
                font = ImageFont.truetype(str(p), size)
                cls._cache[key] = font
                return font

        logger.warning("[Overlay] TTF font not found — using PIL default")
        fb = cls._fallback or ImageFont.load_default()
        cls._fallback = fb
        return fb  # type: ignore


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

class Palette:
    """Colour constants (RGBA)."""
    CRITICAL  = (255,  40,  40, 220)   # Red
    DANGER    = (255,  80,   0, 220)   # Orange-red
    WARNING   = (255, 200,   0, 220)   # Yellow
    SAFE      = ( 40, 200,  40, 200)   # Green
    LANE_WARN = (  0, 220, 255, 220)   # Cyan-yellow
    PED_WARN  = (255,  40, 100, 220)   # Pink-red
    SHADOW    = (  0,   0,   0, 140)   # Text shadow
    HUD_BG    = (  0,   0,   0, 160)   # Semi-transparent black
    WHITE     = (255, 255, 255, 255)
    GREY      = (180, 180, 180, 200)

    @classmethod
    def from_risk(cls, risk_level: str) -> tuple:
        return {
            'CRITICAL': cls.CRITICAL,
            'DANGER'  : cls.DANGER,
            'WARNING' : cls.WARNING,
            'SAFE'    : cls.SAFE,
        }.get(risk_level, cls.GREY)

    @classmethod
    def bbox_from_class(cls, class_name: str, risk_level: str) -> tuple:
        """Returns RGBA for bounding box."""
        if class_name in ('person', 'người'):
            return cls.PED_WARN
        return cls.from_risk(risk_level)


# ---------------------------------------------------------------------------
# Core renderer
# ---------------------------------------------------------------------------

class VietnameseOverlayRenderer:
    """
    Single-responsibility class: adds ADAS safety overlays onto a BGR frame.

    Call order per frame::

        renderer = VietnameseOverlayRenderer()

        frame = renderer.draw_danger_zone(frame, result.danger_zone_pts)
        frame = renderer.draw_bboxes(frame, tracked_objects_with_dist)
        frame = renderer.draw_lane_hud(frame, lane_result)
        frame = renderer.draw_warnings(frame, result.alerts)
        frame = renderer.draw_speedometer_hud(frame, scene_speed, scene_risk)
    """

    def __init__(self):
        self._warmup_fonts()
        self._flash_state        = False
        self._flash_last_toggle  = 0.0
        self._flash_interval     = 0.4   # seconds

    def _warmup_fonts(self):
        """Pre-load all font sizes on first use."""
        for sz in (20, 24, 28, 34, 42, 52):
            FontManager.load(sz)
        logger.info("[Overlay] Fonts warmed up")

    # -----------------------------------------------------------------------
    # Public draw methods
    # -----------------------------------------------------------------------

    def draw_danger_zone(
        self,
        frame     : np.ndarray,
        zone_pts  : np.ndarray,
        active    : bool = False,
    ) -> np.ndarray:
        """
        Draw ego danger zone polygon.
        active=True  → faint red fill (threat present)
        active=False → dashed cyan outline
        """
        if zone_pts is None or len(zone_pts) < 3:
            return frame

        overlay = frame.copy()
        col = (0, 0, 60) if active else (0, 0, 0)
        if active:
            cv2.fillPoly(overlay, [zone_pts], col)
            cv2.addWeighted(frame, 0.75, overlay, 0.25, 0, frame)

        border_col = (0, 80, 255) if active else (0, 200, 200)
        cv2.polylines(frame, [zone_pts], isClosed=True, color=border_col, thickness=1)
        return frame

    def draw_bboxes(
        self,
        frame  : np.ndarray,
        objects: List[Dict],
    ) -> np.ndarray:
        """
        Draw YOLO/ByteTracker bounding boxes with:
          • Colour-coded border (risk level)
          • Track ID
          • Class name (Vietnamese)
          • Distance (m) + TTC label
        """
        if not objects:
            return frame

        pil_img = self._bgr2pil(frame)
        draw    = ImageDraw.Draw(pil_img, 'RGBA')

        font_label = FontManager.load(20)
        font_small = FontManager.load(16)

        for obj in objects:
            bbox  = obj.get('bbox', [0, 0, 0, 0])
            dist  = obj.get('distance', None)
            ttc   = obj.get('ttc_smooth', obj.get('ttc'))
            tid   = obj.get('id', -1)
            cname = obj.get('class_name', '?')
            risk  = obj.get('risk_level', 'SAFE')
            in_zn = obj.get('in_danger_zone', False)

            x1, y1, x2, y2 = [int(v) for v in bbox]
            color = Palette.bbox_from_class(cname, risk)
            # Thicker border if in danger zone
            lw = 3 if in_zn else 2

            # Rounded rect (draw 4 lines for simplicity)
            draw.rectangle([x1, y1, x2, y2], outline=color, width=lw)

            # Label background
            label_text  = f"{self._vn_class(cname)} #{tid}"
            dist_text   = ""
            if dist is not None:
                dist_text = f"{dist:.1f}m"
                if ttc is not None:
                    dist_text += f"  TTC:{ttc:.1f}s"

            # Draw label chip
            self._draw_label_chip(draw, x1, y1, label_text, dist_text,
                                   font_label, font_small, color)

        frame = self._pil2bgr(pil_img)
        return frame

    def draw_lane_hud(
        self,
        frame      : np.ndarray,
        lane_result: Dict,
    ) -> np.ndarray:
        """
        Draw lane offset bar at the bottom of the frame.
        Horizontal bar: green center → orange/red edges.
        Indicator position shows current lateral drift.
        """
        fh, fw = frame.shape[:2]

        bar_w   = int(fw * 0.40)
        bar_h   = 14
        bar_x   = (fw - bar_w) // 2
        bar_y   = fh - 40

        offset   = lane_result.get('lane_offset', 0.0)
        level    = lane_result.get('offset_level', 'SAFE')
        has_lane = lane_result.get('has_lane', False)

        # Gradient bar
        bar_img = np.zeros((bar_h, bar_w, 3), dtype=np.uint8)
        for x in range(bar_w):
            t = x / (bar_w - 1)          # 0 → left, 1 → right
            center_dist = abs(t - 0.5) * 2.0   # 0=center, 1=edge
            g = int(200 * (1.0 - center_dist))
            r = int(200 * center_dist)
            bar_img[:, x] = (0, g, r)          # BGR

        if has_lane:
            frame[bar_y:bar_y + bar_h, bar_x:bar_x + bar_w] = bar_img

            # Indicator marker (clamp to bar)
            ind_x = int(bar_x + (offset * 0.5 + 0.5) * bar_w)
            ind_x = max(bar_x + 2, min(bar_x + bar_w - 3, ind_x))
            ind_col = (0, 80, 255) if level == 'CRITICAL' else \
                      (0, 200, 255) if level == 'WARNING'  else (255, 255, 255)
            cv2.rectangle(frame,
                          (ind_x - 2, bar_y - 2),
                          (ind_x + 2, bar_y + bar_h + 2),
                          ind_col, -1)

        # Tiny label
        pil_img = self._bgr2pil(frame)
        draw    = ImageDraw.Draw(pil_img, 'RGBA')
        font    = FontManager.load(16)
        col_txt = (80, 255, 80, 220) if (has_lane and level == 'SAFE') else \
                  (255, 200, 0, 220) if level == 'WARNING' else \
                  (255, 80, 80, 220)
        draw.text((bar_x - 80, bar_y - 1), "LẶN ĐỀU:", font=font, fill=col_txt)
        frame = self._pil2bgr(pil_img)
        return frame

    def draw_warnings(
        self,
        frame  : np.ndarray,
        alerts : List[Dict],
    ) -> np.ndarray:
        """
        Draw Vietnamese warning banners.
        Critical/Danger → flashing full-width top banner.
        Warning/Info → smaller floating chip below banner.
        """
        if not alerts:
            return frame

        pil_img = self._bgr2pil(frame)
        draw    = ImageDraw.Draw(pil_img, 'RGBA')

        fh, fw = frame.shape[:2]

        PRIORITY = {'CRITICAL': 0, 'DANGER': 1, 'WARNING': 2, 'SAFE': 99}
        sorted_alerts = sorted(alerts,
                               key=lambda a: PRIORITY.get(a.get('severity', 'SAFE'), 99))

        # Primary warning — big banner
        primary = sorted_alerts[0]
        sev     = primary.get('severity', 'SAFE')
        msg     = primary.get('message_vi', '')
        color   = Palette.from_risk(sev)

        # Flash logic for CRITICAL/DANGER
        show = True
        if sev in ('CRITICAL', 'DANGER'):
            now = time.monotonic()
            if now - self._flash_last_toggle > self._flash_interval:
                self._flash_state       = not self._flash_state
                self._flash_last_toggle = now
            show = self._flash_state

        if show:
            self._draw_banner(draw, fw, msg, color,
                              y_top=20, font_size=42 if sev == 'CRITICAL' else 34)

        # Secondary alerts — stacked chips
        for i, alt in enumerate(sorted_alerts[1:3]):   # max 2 secondary
            chip_y = 90 + i * 44
            chip_color = Palette.from_risk(alt.get('severity', 'SAFE'))
            self._draw_chip(draw, fw, alt.get('message_vi', ''),
                            chip_color, y_top=chip_y)

        frame = self._pil2bgr(pil_img)
        return frame

    def draw_top_hud(
        self,
        frame        : np.ndarray,
        scene_risk   : str,
        scene_score  : float,
        fps          : float = 0.0,
        frame_idx    : int   = 0,
        extra_info   : Optional[Dict] = None,
    ) -> np.ndarray:
        """
        Tesla-style top HUD bar:
          [RISK: SAFE] [Score: 0.12]  FPS:28  Frame:1234
          + optional extra_info items on the right
        """
        fh, fw = frame.shape[:2]

        pil_img = self._bgr2pil(frame)
        draw    = ImageDraw.Draw(pil_img, 'RGBA')

        # Semi-transparent HUD bg strip
        draw.rectangle([0, 0, fw, 36], fill=Palette.HUD_BG)

        font = FontManager.load(20)
        risk_col = Palette.from_risk(scene_risk)

        draw.text((10, 8),  f"RỦI RO: {scene_risk}", font=font, fill=risk_col)
        draw.text((200, 8), f"Score: {scene_score:.2f}", font=font, fill=Palette.GREY)

        if fps > 0:
            draw.text((360, 8), f"FPS: {fps:.0f}", font=font, fill=Palette.GREY)
        draw.text((460, 8), f"F: {frame_idx}", font=font, fill=Palette.GREY)

        if extra_info:
            x_right = fw - 10
            for label, val in list(extra_info.items())[:3]:
                txt = f"{label}: {val}"
                bbox_ = draw.textbbox((0, 0), txt, font=font)
                tw = bbox_[2] - bbox_[0]
                draw.text((x_right - tw, 8), txt, font=font, fill=Palette.GREY)
                x_right -= tw + 20

        frame = self._pil2bgr(pil_img)
        return frame

    # -----------------------------------------------------------------------
    # Internal draw helpers
    # -----------------------------------------------------------------------

    def _draw_banner(
        self,
        draw      : ImageDraw.ImageDraw,
        fw        : int,
        text      : str,
        color     : tuple,
        y_top     : int  = 20,
        font_size : int  = 40,
    ) -> None:
        """Full-width warning banner with semi-transparent background."""
        font   = FontManager.load(font_size)
        bbox_  = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox_[2] - bbox_[0], bbox_[3] - bbox_[1]

        pad_x, pad_y = 20, 10
        bx1 = (fw - tw) // 2 - pad_x
        bx2 = (fw + tw) // 2 + pad_x
        by1 = y_top - pad_y
        by2 = y_top + th + pad_y

        # Background with same hue, more transparent
        bg = (color[0], color[1], color[2], 120)
        draw.rectangle([bx1, by1, bx2, by2], fill=bg)
        draw.rectangle([bx1, by1, bx2, by2], outline=color, width=2)

        # Shadow text
        draw.text(((fw - tw) // 2 + 2, y_top + 2), text,
                  font=font, fill=Palette.SHADOW)
        # Main text
        draw.text(((fw - tw) // 2, y_top), text,
                  font=font, fill=(255, 255, 255, 255))

    def _draw_chip(
        self,
        draw  : ImageDraw.ImageDraw,
        fw    : int,
        text  : str,
        color : tuple,
        y_top : int = 90,
    ) -> None:
        """Smaller chip (secondary warning)."""
        font   = FontManager.load(24)
        bbox_  = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox_[2] - bbox_[0], bbox_[3] - bbox_[1]

        pad_x, pad_y = 16, 6
        bx1 = (fw - tw) // 2 - pad_x
        bx2 = (fw + tw) // 2 + pad_x
        by1 = y_top - pad_y
        by2 = y_top + th + pad_y

        bg = (color[0], color[1], color[2], 100)
        draw.rectangle([bx1, by1, bx2, by2], fill=bg)
        draw.rectangle([bx1, by1, bx2, by2], outline=color, width=1)
        draw.text(((fw - tw) // 2 + 1, y_top + 1), text,
                  font=font, fill=Palette.SHADOW)
        draw.text(((fw - tw) // 2,     y_top),     text,
                  font=font, fill=(255, 255, 255, 255))

    def _draw_label_chip(
        self,
        draw      : ImageDraw.ImageDraw,
        x1        : int,
        y1        : int,
        main_txt  : str,
        sub_txt   : str,
        font_main : ImageFont.FreeTypeFont,
        font_sub  : ImageFont.FreeTypeFont,
        color     : tuple,
    ) -> None:
        """Draw a label chip just above bounding box top-left."""
        mb = draw.textbbox((0, 0), main_txt, font=font_main)
        mw, mh = mb[2] - mb[0], mb[3] - mb[1]

        sb = draw.textbbox((0, 0), sub_txt, font=font_sub)
        sw = sb[2] - sb[0]

        chip_w  = max(mw, sw) + 12
        chip_h  = mh + (sb[3] - sb[1] + 4 if sub_txt else 0) + 8

        cx1 = x1
        cy1 = max(0, y1 - chip_h - 2)
        cx2 = cx1 + chip_w
        cy2 = cy1 + chip_h

        bg = (color[0], color[1], color[2], 150)
        draw.rectangle([cx1, cy1, cx2, cy2], fill=bg)
        draw.text((cx1 + 6, cy1 + 4),        main_txt, font=font_main,
                  fill=(255, 255, 255, 240))
        if sub_txt:
            draw.text((cx1 + 6, cy1 + 4 + mh + 2), sub_txt, font=font_sub,
                      fill=(220, 220, 220, 220))

    # -----------------------------------------------------------------------
    # Colour space helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _bgr2pil(frame: np.ndarray) -> Image.Image:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb).convert('RGBA')

    @staticmethod
    def _pil2bgr(pil_img: Image.Image) -> np.ndarray:
        rgb = np.array(pil_img.convert('RGB'))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    # -----------------------------------------------------------------------
    # Vietnamese class name
    # -----------------------------------------------------------------------

    @staticmethod
    def _vn_class(c: str) -> str:
        return {
            'car'       : 'Ô tô',
            'truck'     : 'Xe tải',
            'bus'       : 'Xe buýt',
            'motorcycle': 'Xe máy',
            'bicycle'   : 'Xe đạp',
            'person'    : 'Người',
        }.get(c.lower(), c.title())


# ---------------------------------------------------------------------------
# Convenience wrapper — all-in-one render
# ---------------------------------------------------------------------------

def render_full_frame(
    base_frame       : np.ndarray,
    lane_result      : Dict,
    tracked_objects  : List[Dict],
    risk_result      : any,       # RiskResultV4
    fps              : float = 0.0,
    frame_idx        : int   = 0,
    renderer         : Optional[VietnameseOverlayRenderer] = None,
) -> np.ndarray:
    """
    One-call renderer for a complete ADAS overlay.

    Pipeline:
      1. Start with lane_result['annotated_frame'] (has green corridor)
      2. Draw danger zone polygon
      3. Draw bboxes + distance labels
      4. Draw lane offset bar
      5. Draw warning banners
      6. Draw top HUD strip
    """
    rnd = renderer or VietnameseOverlayRenderer()

    # Start from lane-annotated frame (corridor already painted)
    frame = lane_result.get('annotated_frame', base_frame)
    if frame is None:
        frame = base_frame.copy()

    # Danger zone
    zone_active = len(risk_result.objects_in_zone) > 0
    frame = rnd.draw_danger_zone(
        frame, risk_result.danger_zone_pts, active=zone_active
    )

    # Object boxes + distance
    frame = rnd.draw_bboxes(frame, tracked_objects)

    # Lane bar
    frame = rnd.draw_lane_hud(frame, lane_result)

    # Warning banners
    frame = rnd.draw_warnings(frame, risk_result.alerts)

    # Top HUD
    frame = rnd.draw_top_hud(
        frame,
        scene_risk  = risk_result.scene_risk,
        scene_score = risk_result.scene_score,
        fps         = fps,
        frame_idx   = frame_idx,
    )

    return frame


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    renderer = VietnameseOverlayRenderer()
    frame    = np.zeros((720, 1280, 3), dtype=np.uint8)

    mock_alerts = [
        {
            'type': 'FCW', 'severity': 'DANGER',
            'message_vi': 'CẢNH BÁO VA CHẠM: Ô TÔ cách 5.2m  TTC=1.8s',
            'color_bgr': (0, 80, 255),
        },
        {
            'type': 'LDW', 'severity': 'WARNING',
            'message_vi': 'LỆCH LÀN ĐƯỜNG — ĐANG LỆCH SANG PHẢI (45%)',
            'color_bgr': (0, 200, 255),
        },
    ]

    frame = renderer.draw_warnings(frame, mock_alerts)
    lane_result = {
        'annotated_frame': frame,
        'lane_offset': 0.42,
        'offset_level': 'WARNING',
        'has_lane': True,
    }
    frame = renderer.draw_lane_hud(frame, lane_result)

    try:
        cv2.imwrite("/tmp/adas_overlay_test.jpg", frame)
        print("Saved /tmp/adas_overlay_test.jpg — check visually")
    except Exception as e:
        print(f"Could not save: {e}")
    print("Smoke test complete")
