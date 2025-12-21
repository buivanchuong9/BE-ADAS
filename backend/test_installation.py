"""
Test script to validate ADAS backend installation.
Run this to check if all modules can be imported correctly.
"""

import sys
from pathlib import Path

print("=" * 80)
print("ADAS Backend Installation Test")
print("=" * 80)
print()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Test imports
tests = []

# 1. Test FastAPI
try:
    from fastapi import FastAPI
    from uvicorn import run as uvicorn_run
    tests.append(("✅", "FastAPI", "OK"))
except ImportError as e:
    tests.append(("❌", "FastAPI", f"FAILED: {e}"))

# 2. Test OpenCV
try:
    import cv2
    tests.append(("✅", "OpenCV", f"OK (version {cv2.__version__})"))
except ImportError as e:
    tests.append(("❌", "OpenCV", f"FAILED: {e}"))

# 3. Test NumPy
try:
    import numpy as np
    tests.append(("✅", "NumPy", f"OK (version {np.__version__})"))
except ImportError as e:
    tests.append(("❌", "NumPy", f"FAILED: {e}"))

# 4. Test Ultralytics (YOLO)
try:
    from ultralytics import YOLO
    tests.append(("✅", "Ultralytics (YOLO)", "OK"))
except ImportError as e:
    tests.append(("❌", "Ultralytics (YOLO)", f"FAILED: {e}"))

# 5. Test MediaPipe
try:
    import mediapipe as mp
    tests.append(("✅", "MediaPipe", "OK"))
except ImportError as e:
    tests.append(("❌", "MediaPipe", f"FAILED: {e}"))

# 6. Test Perception Modules
try:
    from perception.lane.lane_detector_v11 import LaneDetectorV11
    tests.append(("✅", "Lane Detector", "OK"))
except Exception as e:
    tests.append(("❌", "Lane Detector", f"FAILED: {e}"))

try:
    from perception.object.object_detector_v11 import ObjectDetectorV11
    tests.append(("✅", "Object Detector", "OK"))
except Exception as e:
    tests.append(("❌", "Object Detector", f"FAILED: {e}"))

try:
    from perception.distance.distance_estimator import DistanceEstimator
    tests.append(("✅", "Distance Estimator", "OK"))
except Exception as e:
    tests.append(("❌", "Distance Estimator", f"FAILED: {e}"))

try:
    from perception.driver.driver_monitor_v11 import DriverMonitorV11
    tests.append(("✅", "Driver Monitor", "OK"))
except Exception as e:
    tests.append(("❌", "Driver Monitor", f"FAILED: {e}"))

try:
    from perception.traffic.traffic_sign_v11 import TrafficSignV11
    tests.append(("✅", "Traffic Sign Detector", "OK"))
except Exception as e:
    tests.append(("❌", "Traffic Sign Detector", f"FAILED: {e}"))

try:
    from perception.pipeline.video_pipeline_v11 import VideoPipelineV11, process_video
    tests.append(("✅", "Video Pipeline", "OK"))
except Exception as e:
    tests.append(("❌", "Video Pipeline", f"FAILED: {e}"))

# 7. Test Backend Modules
try:
    from app.services.analysis_service import AnalysisService, get_analysis_service
    tests.append(("✅", "Analysis Service", "OK"))
except Exception as e:
    tests.append(("❌", "Analysis Service", f"FAILED: {e}"))

try:
    from app.api.video import router
    tests.append(("✅", "Video API", "OK"))
except Exception as e:
    tests.append(("❌", "Video API", f"FAILED: {e}"))

try:
    from app.main import app
    tests.append(("✅", "Main Application", "OK"))
except Exception as e:
    tests.append(("❌", "Main Application", f"FAILED: {e}"))

# Print results
print("Test Results:")
print("-" * 80)

failed = []
for icon, name, status in tests:
    print(f"{icon} {name:<25} {status}")
    if icon == "❌":
        failed.append(name)

print("-" * 80)
print()

# Summary
if not failed:
    print("🎉 SUCCESS! All modules imported correctly.")
    print()
    print("Next steps:")
    print("1. Run: ./start_backend.sh")
    print("2. Open: http://localhost:8000/docs")
    print("3. Test upload endpoint")
else:
    print(f"⚠️  {len(failed)} module(s) failed to import:")
    for name in failed:
        print(f"   - {name}")
    print()
    print("Fix:")
    print("   pip install -r requirements.txt")

print()
print("=" * 80)
