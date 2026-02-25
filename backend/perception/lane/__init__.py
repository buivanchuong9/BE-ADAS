"""Lane detection module for ADAS system — V4 BEV classical pipeline."""

from .lane_detector_v4 import LaneDetectorV4

# Legacy alias so any code that still does `from ...lane import LaneDetectorV11`
# gets the V4 class transparently and doesn't crash during transition.
LaneDetectorV11 = LaneDetectorV4

__all__ = ["LaneDetectorV4", "LaneDetectorV11"]
