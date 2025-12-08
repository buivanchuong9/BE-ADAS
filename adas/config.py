"""
ADAS Configuration & Constants
Cấu hình và hằng số cho hệ thống ADAS
"""

import numpy as np
from pathlib import Path

# =====================================================
# TRAFFIC SIGN RECOGNITION (TSR) CONFIG
# =====================================================

# Traffic sign classes (Vietnam traffic signs)
TRAFFIC_SIGN_CLASSES = {
    # Speed limit signs
    0: "speed_limit_5",
    1: "speed_limit_10",
    2: "speed_limit_20",
    3: "speed_limit_30",
    4: "speed_limit_40",
    5: "speed_limit_50",
    6: "speed_limit_60",
    7: "speed_limit_70",
    8: "speed_limit_80",
    9: "speed_limit_90",
    10: "speed_limit_100",
    11: "speed_limit_110",
    12: "speed_limit_120",
    
    # Warning signs
    20: "danger",
    21: "curve_left",
    22: "curve_right",
    23: "bumpy_road",
    24: "slippery_road",
    25: "narrow_road",
    26: "road_work",
    27: "traffic_signal",
    28: "pedestrian_crossing",
    29: "children_crossing",
    30: "bicycle_crossing",
    
    # Prohibitory signs
    40: "no_entry",
    41: "no_stopping",
    42: "no_parking",
    43: "no_overtaking",
    44: "no_left_turn",
    45: "no_right_turn",
    46: "no_u_turn",
    
    # Mandatory signs
    60: "turn_left",
    61: "turn_right",
    62: "straight_only",
    63: "roundabout",
    
    # Information signs
    80: "parking",
    81: "hospital",
    82: "gas_station",
}

# Speed limit mapping (km/h)
SPEED_LIMITS = {
    "speed_limit_5": 5,
    "speed_limit_10": 10,
    "speed_limit_20": 20,
    "speed_limit_30": 30,
    "speed_limit_40": 40,
    "speed_limit_50": 50,
    "speed_limit_60": 60,
    "speed_limit_70": 70,
    "speed_limit_80": 80,
    "speed_limit_90": 90,
    "speed_limit_100": 100,
    "speed_limit_110": 110,
    "speed_limit_120": 120,
}

# TSR Detection thresholds
TSR_CONF_THRESHOLD = 0.45  # Confidence threshold for traffic signs
TSR_IOU_THRESHOLD = 0.4    # IoU threshold for NMS
TSR_MIN_SIZE = 20          # Minimum bounding box size (pixels)
TSR_MEMORY_FRAMES = 30     # Remember detected sign for N frames

# =====================================================
# FORWARD COLLISION WARNING (FCW) CONFIG
# =====================================================

# Vehicle detection classes (COCO dataset)
VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# FCW thresholds
FCW_CONF_THRESHOLD = 0.4          # Confidence threshold for vehicle detection
FCW_IOU_THRESHOLD = 0.45          # IoU threshold for NMS
FCW_DANGER_DISTANCE = 15.0        # Critical distance (meters)
FCW_WARNING_DISTANCE = 30.0       # Warning distance (meters)
FCW_MIN_TTC = 2.0                 # Minimum Time-To-Collision (seconds)

# Distance estimation parameters (monocular)
# Based on camera calibration and average vehicle sizes
FOCAL_LENGTH = 700.0              # Camera focal length (pixels)
AVERAGE_CAR_WIDTH = 1.8           # Average car width (meters)
AVERAGE_CAR_HEIGHT = 1.5          # Average car height (meters)
AVERAGE_TRUCK_WIDTH = 2.5         # Average truck width (meters)
AVERAGE_BUS_WIDTH = 2.6           # Average bus width (meters)

# Vehicle size database (width, height in meters)
VEHICLE_SIZES = {
    "car": (1.8, 1.5),
    "motorcycle": (0.8, 1.2),
    "bus": (2.6, 3.2),
    "truck": (2.5, 3.0),
}

# =====================================================
# LANE DEPARTURE WARNING (LDW) CONFIG
# =====================================================

# Lane detection ROI (Region of Interest)
LDW_ROI_TOP = 0.55        # Top of ROI (ratio of image height)
LDW_ROI_BOTTOM = 0.95     # Bottom of ROI (ratio of image height)

# Hough Transform parameters
HOUGH_RHO = 2             # Distance resolution (pixels)
HOUGH_THETA = np.pi/180   # Angle resolution (radians)
HOUGH_THRESHOLD = 50      # Minimum votes for line
HOUGH_MIN_LINE_LEN = 40   # Minimum line length
HOUGH_MAX_LINE_GAP = 100  # Maximum gap between line segments

# Lane filtering parameters
LANE_MIN_SLOPE = 0.3      # Minimum absolute slope for valid lane
LANE_MAX_SLOPE = 3.0      # Maximum absolute slope for valid lane
LANE_WIDTH_MIN = 200      # Minimum lane width (pixels)
LANE_WIDTH_MAX = 800      # Maximum lane width (pixels)

# Departure detection
DEPARTURE_THRESHOLD = 0.15  # Departure threshold (ratio of image width)
DEPARTURE_MEMORY = 10       # Consecutive frames to trigger warning

# =====================================================
# GENERAL ADAS CONFIG
# =====================================================

# Display settings
DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 720
DISPLAY_FPS = 30

# Colors (BGR format for OpenCV)
COLOR_GREEN = (0, 255, 0)
COLOR_YELLOW = (0, 255, 255)
COLOR_RED = (0, 0, 255)
COLOR_BLUE = (255, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_CYAN = (255, 255, 0)
COLOR_MAGENTA = (255, 0, 255)

# Alert levels
ALERT_NONE = 0
ALERT_INFO = 1
ALERT_WARNING = 2
ALERT_DANGER = 3

# Audio alerts
ENABLE_AUDIO = True
AUDIO_VOLUME = 0.8

# Model paths
MODELS_DIR = Path(__file__).parent.parent / "ai_models" / "weights"
TSR_MODEL_PATH = MODELS_DIR / "traffic_sign_yolo11n.pt"  # Traffic sign model
YOLO11_MODEL_PATH = MODELS_DIR / "yolo11n.pt"            # General YOLO11

# Performance
ENABLE_GPU = True
HALF_PRECISION = False  # FP16 for faster inference (if GPU supports)

# Debug mode
DEBUG_MODE = False
SHOW_FPS = True
SHOW_DETECTIONS = True
SAVE_DEBUG_FRAMES = False

# =====================================================
# CAMERA CALIBRATION (Optional - for better accuracy)
# =====================================================

# Camera intrinsic parameters (will be loaded from calibration file if available)
CAMERA_MATRIX = None
DIST_COEFFS = None
CALIBRATION_FILE = Path(__file__).parent / "camera_calibration.json"
