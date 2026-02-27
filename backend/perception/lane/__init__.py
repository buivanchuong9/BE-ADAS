"""Lane detection module for ADAS system.

Detectors:
  - LaneDetectorV4:    Classical BEV + sliding window (no ML model)
  - UFLDLaneDetector:  Ultra Fast Lane Detection v2 (deep learning, ~300 FPS)
  - LaneDetectorV11:   YOLOv11x-seg segmentation (legacy)
"""

from .lane_detector_v4 import LaneDetectorV4
from .lane_detector_ufld import UFLDLaneDetector

# Legacy alias
LaneDetectorV11 = LaneDetectorV4

__all__ = ["LaneDetectorV4", "UFLDLaneDetector", "LaneDetectorV11"]
