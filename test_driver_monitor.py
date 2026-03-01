#!/usr/bin/env python3
"""
Test Driver Monitor PRO với 1 frame ảnh.

Usage:
    python test_driver_monitor.py [path_to_image]

Tính năng test:
- Face Mesh (EAR, Blink)
- Pose Detection
- Head Pose
- Seatbelt Detection
- Phone/Drink Detection
- Drowsiness Detection
- Attention Score
"""

import sys
import cv2
import numpy as np
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_driver_monitor(image_path: str = None):
    """Test Driver Monitor PRO với ảnh."""
    
    print("=" * 70)
    print("🚗 DRIVER MONITOR V11 PRO - TEST")
    print("=" * 70)
    
    # Import module
    try:
        from backend.perception.driver.driver_monitor_v11_pro import (
            DriverMonitorV11Pro, MEDIAPIPE_AVAILABLE
        )
        print(f"✅ Import successful!")
        print(f"   MediaPipe: {'✅' if MEDIAPIPE_AVAILABLE else '❌'}")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return
    
    # Tạo hoặc load test image
    if image_path and Path(image_path).exists():
        print(f"\n📷 Loading image: {image_path}")
        frame = cv2.imread(image_path)
    else:
        print("\n📷 Creating test frame (640x480)...")
        # Tạo frame giả để test
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:] = (50, 50, 80)  # Dark gray background
        
        # Vẽ một "driver" giả (chỉ để test không có crash)
        # Circle for head
        cv2.circle(frame, (320, 150), 50, (220, 200, 180), -1)
        # Body
        cv2.rectangle(frame, (270, 200), (370, 350), (100, 100, 150), -1)
        # Shoulders
        cv2.line(frame, (220, 220), (320, 220), (100, 100, 150), 10)
        cv2.line(frame, (320, 220), (420, 220), (100, 100, 150), 10)
        
        print("   (Using synthetic test frame)")
    
    h, w = frame.shape[:2]
    print(f"   Frame size: {w}x{h}")
    
    # Khởi tạo monitor
    print("\n🔧 Initializing Driver Monitor PRO...")
    try:
        monitor = DriverMonitorV11Pro(
            device="cpu",  # Use CPU for testing
            enable_attention_score=True,
            enable_head_pose=True,
            enable_face_mesh=True,
        )
        print("✅ Monitor initialized!")
    except Exception as e:
        print(f"❌ Init failed: {e}")
        # Try without models
        print("⚠️ Trying basic initialization test...")
        monitor = None
    
    if monitor is None:
        print("\n⚠️ Cannot test without models. Please ensure models exist:")
        print("   - backend/models/yolo11x.pt")
        print("   - backend/models/yolo11x-pose.pt")
        return
    
    # Process frame
    print("\n🎯 Processing frame...")
    try:
        # Debug: Check raw object detection
        print("\n🔍 DEBUG - Raw Object Detection:")
        objects = monitor.detect_objects(frame)
        print(f"   Found {len(objects)} object(s)")
        for obj in objects:
            print(f"   - {obj['class_name']}: {obj['confidence']:.1%} at {obj['center']}")
        
        result = monitor.process_frame(frame)
        print("✅ Frame processed!")
    except Exception as e:
        print(f"❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Print results
    print("\n" + "=" * 70)
    print("📊 ANALYSIS RESULTS")
    print("=" * 70)
    
    # Basic info
    print(f"\n🔹 Frame: {result.get('frame_number', 'N/A')}")
    print(f"🔹 FPS: {result.get('fps', 'N/A')}")
    print(f"🔹 Face detected: {'✅' if result.get('face_detected', False) else '❌'}")
    print(f"🔹 Pose detected: {'✅' if result.get('pose_detected', False) else '❌'}")
    
    # Driver state
    print(f"\n📌 DRIVER STATE:")
    print(f"   State: {result.get('state', 'N/A')}")
    print(f"   Confidence: {result.get('confidence', 0):.2%}")
    print(f"   Attention Score: {result.get('attention_score', 'N/A')}%")
    print(f"   Distraction Level: {result.get('distraction_level', 'N/A')}")
    
    # Eyes / Face Mesh
    print(f"\n👁️ EYE TRACKING:")
    print(f"   EAR (Eye Aspect Ratio): {result.get('ear', 'N/A')}")
    print(f"   Eyes Open: {'✅ MỞ' if result.get('eyes_open', True) else '❌ NHẮM'}")
    print(f"   Blinks: {result.get('blinks', 0)}")
    print(f"   PERCLOS: {result.get('perclos', 0):.1%}")
    print(f"   Yawning: {'✅' if result.get('yawning', False) else '❌'}")
    
    # Head pose
    head_pose = result.get('head_pose', {})
    if head_pose.get('is_valid', False):
        print(f"\n🗣️ HEAD POSE:")
        print(f"   Yaw: {head_pose.get('yaw', 0):+.1f}° (trái/phải)")
        print(f"   Pitch: {head_pose.get('pitch', 0):+.1f}° (lên/xuống)")
        print(f"   Roll: {head_pose.get('roll', 0):+.1f}° (nghiêng)")
    else:
        print(f"\n🗣️ HEAD POSE: Not available")
    
    # Behaviors
    behaviors = result.get('behaviors', {})
    print(f"\n⚠️ BEHAVIOR DETECTION:")
    
    # Seatbelt - Updated for realistic detection
    seatbelt = behaviors.get('seatbelt', {})
    seatbelt_status_code = seatbelt.get('status', 'unknown')
    status_display = {
        'wearing': "✅ ĐÃ THẮT",
        'not_wearing': "❌ KHÔNG CÓ",
        'checking': "⏳ ĐANG KIỂM TRA",
        'unknown': "❓ KHÔNG PHÁT HIỆN"
    }
    seatbelt_display = status_display.get(seatbelt_status_code, "❓ KHÔNG RÕ")
    print(f"   🚗 Dây an toàn: {seatbelt_display} (conf: {seatbelt.get('confidence', 0):.2f})")
    
    # Phone
    phone = behaviors.get('phone', {})
    phone_status = "❌ CÓ" if phone.get('detected', False) else "✅ KHÔNG"
    print(f"   📱 Dùng điện thoại: {phone_status}")
    
    # Drinking
    drinking = behaviors.get('drinking', {})
    drinking_status = "❌ CÓ" if drinking.get('detected', False) else "✅ KHÔNG"
    print(f"   🥤 Đang uống: {drinking_status}")
    
    # Smoking
    smoking = behaviors.get('smoking', {})
    smoking_status = "❌ CÓ" if smoking.get('detected', False) else "✅ KHÔNG"
    print(f"   🚬 Hút thuốc: {smoking_status}")
    
    # Drowsiness - Enhanced display
    drowsy = behaviors.get('drowsiness', {})
    drowsy_status = "❌ CÓ" if drowsy.get('detected', False) else "✅ KHÔNG"
    print(f"   😴 Buồn ngủ: {drowsy_status} (severity: {drowsy.get('severity', 'NONE')})")
    
    # Enhanced drowsiness details
    if drowsy.get('microsleep'):
        print(f"      ⚠️ MICROSLEEP: {drowsy.get('microsleep_duration_ms', 0)}ms")
    if drowsy.get('drowsy_eyes'):
        print(f"      😴 MẮT LỜ ĐỜ: {drowsy.get('drowsy_eyes_duration', 0):.1f}s")
    if drowsy.get('yawning'):
        print(f"      😴 ĐANG NGÁP: {drowsy.get('yawn_duration', 0):.1f}s")
    if drowsy.get('long_blink'):
        print(f"      ⚠️ CHỚP MẮT DÀI")
    if drowsy.get('stroke_warning'):
        print(f"      🚨 CẢNH BÁO: Bất đối xứng khuôn mặt!")
    
    # Drowsiness stats
    print(f"      📊 Microsleep count: {drowsy.get('microsleep_count', 0)}")
    print(f"      📊 Long blink count: {drowsy.get('long_blink_count', 0)}")
    
    # Looking away
    away = behaviors.get('looking_away', {})
    away_status = "❌ CÓ" if away.get('detected', False) else "✅ KHÔNG"
    print(f"   👀 Nhìn ngoài: {away_status} ({away.get('duration', 0):.1f}s)")
    
    # Detection Boxes
    detection_boxes = result.get('detection_boxes', {})
    if detection_boxes:
        print(f"\n📦 DETECTED OBJECTS (Bounding Boxes):")
        for class_name, dets in detection_boxes.items():
            for det in dets:
                bbox = det['bbox']
                print(f"   - {class_name}: {det['confidence']*100:.0f}% @ [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]")
    
    # Warnings with Priority
    warnings = result.get('warnings', [])
    priority_warnings = result.get('prioritized_warnings', [])
    highest = result.get('highest_priority')
    
    print(f"\n🚨 WARNINGS ({len(warnings)}):")
    if priority_warnings:
        for pw in priority_warnings:
            level_icon = {'P0_CRITICAL': '🔴', 'P1_HIGH': '🟠', 'P2_MEDIUM': '🟡', 'P3_LOW': '⚪'}.get(pw['level'], '⚠️')
            print(f"   {level_icon} [{pw['level']}] {pw['message']}")
        print(f"\n   🔊 Sound to play: {result.get('warning_sound', 'none')}")
    elif warnings:
        for warn in warnings:
            print(f"   ⚠️ {warn}")
    else:
        print("   ✅ Không có cảnh báo - Tài xế an toàn!")
    
    # Overall safety
    is_safe = result.get('is_safe', True)
    print(f"\n{'=' * 70}")
    if is_safe:
        print("🟢 KẾT LUẬN: TÀI XẾ AN TOÀN")
    else:
        print("🔴 KẾT LUẬN: PHÁT HIỆN HÀNH VI NGUY HIỂM!")
    print("=" * 70)
    
    # Save annotated frame
    annotated = result.get('annotated_frame')
    if annotated is not None:
        output_path = "test_driver_result.jpg"
        cv2.imwrite(output_path, annotated)
        print(f"\n💾 Saved annotated frame to: {output_path}")
    
    return result


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = None
    
    test_driver_monitor(image_path)


if __name__ == "__main__":
    main()
