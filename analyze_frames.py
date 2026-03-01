#!/usr/bin/env python3
"""
Phân tích tất cả frames từ video driver-action-recognition.
Debug xem YOLO detect được gì.
"""

import cv2
import os
from pathlib import Path
from ultralytics import YOLO
import numpy as np

def main():
    print("=" * 70)
    print("🔍 PHÂN TÍCH FRAMES - DEBUG YOLO DETECTION")
    print("=" * 70)
    
    # Load models
    print("\n📦 Loading models...")
    obj_model = YOLO('backend/models/yolo11x.pt')
    obj_model.overrides['conf'] = 0.25  # Lower threshold để detect nhiều hơn
    
    pose_model = YOLO('backend/models/yolo11x-pose.pt')
    pose_model.overrides['conf'] = 0.3
    
    # Danh sách class cần quan tâm
    important_classes = {
        67: 'cell phone',
        41: 'cup',
        39: 'bottle',
        0: 'person',
    }
    
    # Process từng frame
    frames_dir = Path('test_frames')
    frames = sorted(frames_dir.glob('*.jpg'))
    
    print(f"\n📊 Phân tích {len(frames)} frames...\n")
    
    results_summary = []
    
    for i, frame_path in enumerate(frames):
        frame = cv2.imread(str(frame_path))
        h, w = frame.shape[:2]
        time_sec = i * 5  # Mỗi frame cách nhau 5 giây
        
        print(f"{'='*70}")
        print(f"📷 Frame {i+1}: {frame_path.name} (t={time_sec}s)")
        print(f"{'='*70}")
        
        # Object detection
        obj_results = obj_model(frame, verbose=False)
        
        detections = []
        phone_detected = False
        cup_detected = False
        person_detected = False
        
        print("\n🎯 OBJECT DETECTION:")
        for result in obj_results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                name = obj_model.names[cls_id]
                
                # Highlight important classes
                if cls_id in important_classes:
                    marker = "⚠️ " if cls_id == 67 else "  "
                    print(f"   {marker}[{cls_id}] {name}: {conf:.1%}")
                    
                    if cls_id == 67:  # cell phone
                        phone_detected = True
                    elif cls_id in [41, 39]:  # cup/bottle
                        cup_detected = True
                    elif cls_id == 0:  # person
                        person_detected = True
                    
                    detections.append({
                        'class': name,
                        'conf': conf,
                        'bbox': box.xyxy[0].cpu().numpy().tolist()
                    })
        
        if not detections:
            print("   (Không phát hiện object quan trọng)")
        
        # Pose detection
        pose_results = pose_model(frame, verbose=False)
        pose_detected = False
        
        print("\n🧍 POSE DETECTION:")
        for result in pose_results:
            if result.keypoints is not None and len(result.keypoints.data) > 0:
                pose_detected = True
                kpts = result.keypoints.data[0].cpu().numpy()
                
                # Check các keypoint quan trọng
                nose = kpts[0]
                left_wrist = kpts[9]
                right_wrist = kpts[10]
                
                print(f"   Nose: ({nose[0]:.0f}, {nose[1]:.0f}) conf={nose[2]:.2f}")
                print(f"   L.Wrist: ({left_wrist[0]:.0f}, {left_wrist[1]:.0f}) conf={left_wrist[2]:.2f}")
                print(f"   R.Wrist: ({right_wrist[0]:.0f}, {right_wrist[1]:.0f}) conf={right_wrist[2]:.2f}")
                
                # Kiểm tra tay gần mặt (có thể đang dùng điện thoại)
                if nose[2] > 0.3 and (left_wrist[2] > 0.3 or right_wrist[2] > 0.3):
                    dist_left = np.sqrt((left_wrist[0]-nose[0])**2 + (left_wrist[1]-nose[1])**2)
                    dist_right = np.sqrt((right_wrist[0]-nose[0])**2 + (right_wrist[1]-nose[1])**2)
                    min_dist = min(dist_left, dist_right)
                    
                    if min_dist < 300:
                        print(f"   ⚠️ TAY GẦN MẶT! dist={min_dist:.0f}px")
        
        if not pose_detected:
            print("   (Không phát hiện pose)")
        
        # Summary
        print("\n📋 SUMMARY:")
        warnings = []
        if phone_detected:
            warnings.append("📱 ĐIỆN THOẠI")
        if cup_detected:
            warnings.append("🥤 CỐC/CHAI")
        
        if warnings:
            print(f"   ⚠️ PHÁT HIỆN: {', '.join(warnings)}")
        else:
            print("   ✅ Không có hành vi nguy hiểm")
        
        results_summary.append({
            'frame': i+1,
            'time': time_sec,
            'phone': phone_detected,
            'cup': cup_detected,
            'pose': pose_detected,
        })
        
        print()
    
    # Final summary
    print("\n" + "=" * 70)
    print("📊 TỔNG KẾT")
    print("=" * 70)
    
    phone_frames = [r for r in results_summary if r['phone']]
    cup_frames = [r for r in results_summary if r['cup']]
    
    print(f"\n📱 Frames phát hiện ĐIỆN THOẠI: {len(phone_frames)}/{len(results_summary)}")
    for r in phone_frames:
        print(f"   - Frame {r['frame']} (t={r['time']}s)")
    
    print(f"\n🥤 Frames phát hiện CỐC/CHAI: {len(cup_frames)}/{len(results_summary)}")
    for r in cup_frames:
        print(f"   - Frame {r['frame']} (t={r['time']}s)")
    
    if not phone_frames and not cup_frames:
        print("\n⚠️ KHÔNG PHÁT HIỆN ĐƯỢC ĐỐI TƯỢNG NGUY HIỂM!")
        print("   Có thể do:")
        print("   1. Confidence threshold quá cao")
        print("   2. Model không được train với phone/cup trong context lái xe")
        print("   3. Object bị che khuất hoặc góc camera")


if __name__ == "__main__":
    main()
