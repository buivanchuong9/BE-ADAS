#!/usr/bin/env python3
"""
ADAS Quick Test Script
Kiểm tra nhanh các module ADAS với test video/image
"""

import cv2
import numpy as np
import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

from ultralytics import YOLO
from adas import ADASController
from adas.config import MODELS_DIR


def test_image(image_path: str, speed: float = 60.0):
    """Test ADAS với một ảnh"""
    print(f"🖼️  Testing with image: {image_path}")
    
    # Load image
    img = cv2.imread(image_path)
    if img is None:
        print(f"❌ Cannot read image: {image_path}")
        return
    
    # Load YOLO
    model_path = MODELS_DIR / "yolo11n.pt"
    if not model_path.exists():
        model_path = "yolo11n.pt"
    
    print(f"📦 Loading YOLO: {model_path}")
    model = YOLO(str(model_path))
    
    # Initialize ADAS
    print("🚀 Initializing ADAS...")
    adas = ADASController(
        yolo_model=model,
        enable_tsr=True,
        enable_fcw=True,
        enable_ldw=True,
        enable_audio=False,  # No audio for image test
        vehicle_speed=speed,
    )
    
    # Process
    print("⚙️  Processing...")
    output, data = adas.process_frame(img)
    
    # Display results
    print("\n" + "=" * 60)
    print("📊 ADAS Results")
    print("=" * 60)
    print(f"Vehicle Speed: {data['vehicle_speed']} km/h")
    
    if 'speed_limit' in data and data['speed_limit']:
        print(f"Speed Limit: {data['speed_limit']} km/h")
    
    if 'tsr_detections' in data:
        print(f"Traffic Signs Detected: {data['tsr_detections']}")
    
    if 'fcw_detections' in data:
        print(f"Vehicles Detected: {data['fcw_detections']}")
        if data.get('closest_vehicle'):
            v = data['closest_vehicle']
            print(f"  Closest: {v['class_name']} at {v['distance']:.1f}m (Alert: {v['alert_level']})")
    
    if 'ldw_data' in data:
        ldw = data['ldw_data']
        print(f"Lane Detection: Alert={ldw['alert_level']}")
    
    if data.get('alerts'):
        print(f"\n⚠️  Alerts ({len(data['alerts'])}):")
        for alert in data['alerts']:
            print(f"  - [{alert['type']}] {alert['message']}")
    
    print("=" * 60)
    
    # Show image
    cv2.imshow("ADAS Test - Press Q to quit", output)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    # Cleanup
    adas.cleanup()
    print("✅ Test complete")


def test_modules():
    """Test từng module riêng lẻ"""
    print("🧪 Testing individual modules...")
    
    # Create dummy frame
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    
    # Draw some test patterns
    # Road
    cv2.rectangle(frame, (0, 400), (1280, 720), (50, 50, 50), -1)
    
    # Lane lines
    cv2.line(frame, (400, 720), (500, 400), (255, 255, 255), 5)
    cv2.line(frame, (880, 720), (780, 400), (255, 255, 255), 5)
    
    # "Car" ahead
    cv2.rectangle(frame, (550, 450), (730, 600), (0, 0, 255), -1)
    cv2.putText(frame, "CAR", (600, 520), cv2.FONT_HERSHEY_DUPLEX, 1, (255, 255, 255), 2)
    
    # "Speed limit" sign
    cv2.circle(frame, (200, 200), 50, (0, 0, 255), -1)
    cv2.circle(frame, (200, 200), 45, (255, 255, 255), -1)
    cv2.putText(frame, "50", (175, 215), cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 0, 0), 3)
    
    print("\n📦 Loading YOLO...")
    model_path = MODELS_DIR / "yolo11n.pt"
    if not model_path.exists():
        model_path = "yolo11n.pt"
    model = YOLO(str(model_path))
    
    print("🚀 Testing ADAS Controller...")
    adas = ADASController(
        yolo_model=model,
        enable_tsr=True,
        enable_fcw=True,
        enable_ldw=True,
        enable_audio=False,
        vehicle_speed=60.0,
    )
    
    # Process dummy frame
    output, data = adas.process_frame(frame)
    
    print("\n" + "=" * 60)
    print("📊 Module Test Results")
    print("=" * 60)
    
    # Show statistics
    stats = adas.get_stats()
    for module, module_stats in stats.items():
        if isinstance(module_stats, dict):
            print(f"\n{module.upper()}:")
            for key, value in module_stats.items():
                print(f"  {key}: {value}")
        else:
            print(f"{module}: {module_stats}")
    
    print("=" * 60)
    
    # Display
    cv2.imshow("Module Test - Press Q to quit", output)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    adas.cleanup()
    print("✅ Module test complete")


def main():
    """Main test function"""
    print("=" * 60)
    print("🧪 ADAS Quick Test")
    print("=" * 60)
    print("")
    print("Options:")
    print("1) Test with image file")
    print("2) Test with dummy/synthetic image")
    print("")
    
    choice = input("Enter choice [1-2] (default: 2): ").strip() or "2"
    
    if choice == "1":
        image_path = input("Enter image path: ").strip()
        if not image_path:
            print("❌ No image path provided")
            return 1
        
        speed = input("Enter vehicle speed (km/h, default: 60): ").strip()
        speed = float(speed) if speed else 60.0
        
        test_image(image_path, speed)
    
    elif choice == "2":
        test_modules()
    
    else:
        print("❌ Invalid choice")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
