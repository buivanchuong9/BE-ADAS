"""
Inference API Router
Phân tích video real-time với YOLO + YOLOP + MiDaS + TTC
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import cv2
import numpy as np
import json
from datetime import datetime
import tempfile
import os

from database import get_db

router = APIRouter(prefix="/api/inference", tags=["Inference"])


@router.post("/video")
async def inference_video(
    file: UploadFile = File(...),
    detect_vehicles: bool = True,
    detect_lanes: bool = True,
    estimate_depth: bool = True,
    compute_ttc: bool = True,
    warning_distance: float = 5.0,  # meters
    create_voice_alerts: bool = True,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    🔥 API Inference - Phân tích video real-time với TTC computation
    
    Args:
        file: Video file để phân tích
        detect_vehicles: Bật vehicle detection (YOLO)
        detect_lanes: Bật lane detection (YOLOP)
        estimate_depth: Bật depth estimation (MiDaS)
        compute_ttc: Tính Time-to-Collision
        warning_distance: Khoảng cách cảnh báo (meters)
        create_voice_alerts: Tạo voice alerts cho warnings
    
    Returns:
        {
            "frames": [
                {
                    "frame_number": int,
                    "timestamp": float,
                    "vehicles": [...],
                    "lanes": {...},
                    "warnings": [...],
                    "ttc_info": {...}
                }
            ],
            "summary": {
                "total_frames": int,
                "vehicles_detected": int,
                "warnings_count": int,
                "min_ttc": float,
                "critical_alerts": int
            },
            "alerts": [...]
        }
    """
    
    # Validate video
    if not file.filename.endswith(('.mp4', '.avi', '.mov', '.mkv')):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ video format: mp4, avi, mov, mkv")
    
    # Load models
    try:
        from ai_models.yolo_detector import YOLODetector
        from ai_models.yolop_detector import YOLOPDetector
        from ai_models.depth_estimator import DepthEstimator
        from ai_models.ttc_computer import TTCComputer
        from ai_models.voice_alert import VoiceAlertSystem
        from models import Alert, Event
        
        yolo = YOLODetector() if detect_vehicles else None
        yolop = YOLOPDetector() if detect_lanes else None
        depth_est = DepthEstimator() if estimate_depth else None
        ttc_comp = TTCComputer() if compute_ttc else None
        voice_system = VoiceAlertSystem() if create_voice_alerts else None
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi load models: {str(e)}")
    
    # Lưu video tạm
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_file:
        tmp_file.write(await file.read())
        video_path = tmp_file.name
    
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        results = []
        frame_count = 0
        total_vehicles = 0
        total_warnings = 0
        min_ttc = float('inf')
        critical_alerts = 0
        alerts_created = []
        
        # Tracking history for TTC computation
        tracking_history = {}
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            timestamp = frame_count / fps
            frame_result = {
                "frame_number": frame_count,
                "timestamp": round(timestamp, 2),
                "vehicles": [],
                "lanes": None,
                "warnings": [],
                "ttc_info": None
            }
            
            # 1. Vehicle Detection
            if yolo:
                vehicles = yolo.detect(frame)
                
                # 2. Depth Estimation cho từng vehicle
                if depth_est and vehicles:
                    depth_map = depth_est.estimate(frame)
                    
                    for vehicle in vehicles:
                        # Lấy depth tại center của bounding box
                        center_y = int(vehicle['bbox'][1] * frame.shape[0])
                        center_x = int(vehicle['bbox'][0] * frame.shape[1])
                        
                        if 0 <= center_y < depth_map.shape[0] and 0 <= center_x < depth_map.shape[1]:
                            distance = float(depth_map[center_y, center_x])
                            vehicle['distance'] = round(distance, 2)
                
                # 3. TTC Computation
                if ttc_comp and vehicles:
                    vehicles_with_ttc = ttc_comp.compute_batch_ttc(
                        vehicles,
                        tracking_history
                    )
                    
                    # Update tracking history
                    for v in vehicles_with_ttc:
                        if 'id' in v:
                            tracking_history[v['id']] = {
                                'distance': v.get('distance', 0),
                                'timestamp': timestamp
                            }
                    
                    frame_result["vehicles"] = vehicles_with_ttc
                    total_vehicles += len(vehicles_with_ttc)
                    
                    # Get most critical vehicle
                    critical_vehicle = ttc_comp.get_most_critical(vehicles_with_ttc)
                    
                    if critical_vehicle:
                        ttc_value = critical_vehicle.get('ttc')
                        if ttc_value and ttc_value < min_ttc:
                            min_ttc = ttc_value
                        
                        frame_result["ttc_info"] = {
                            "min_ttc": critical_vehicle.get('ttc'),
                            "distance": critical_vehicle.get('distance'),
                            "severity": critical_vehicle.get('severity'),
                            "relative_speed": critical_vehicle.get('relative_speed')
                        }
                        
                        # 4. Generate Warnings
                        severity = critical_vehicle.get('severity')
                        if severity in ['critical', 'high']:
                            warning = {
                                "type": "collision_warning",
                                "message": critical_vehicle.get('warning'),
                                "ttc": critical_vehicle.get('ttc'),
                                "distance": critical_vehicle.get('distance'),
                                "severity": severity
                            }
                            frame_result["warnings"].append(warning)
                            total_warnings += 1
                            
                            # 5. Create Voice Alert
                            if voice_system and severity == 'critical':
                                audio_path = voice_system.create_collision_alert(
                                    distance=critical_vehicle.get('distance', 0),
                                    ttc=critical_vehicle.get('ttc', 0)
                                )
                                
                                if audio_path:
                                    # Save alert to database
                                    alert = Alert(
                                        ttc=critical_vehicle.get('ttc'),
                                        distance=critical_vehicle.get('distance'),
                                        relative_speed=critical_vehicle.get('relative_speed'),
                                        severity=severity,
                                        alert_type="collision_warning",
                                        message=critical_vehicle.get('warning'),
                                        audio_path=audio_path,
                                        created_at=datetime.now()
                                    )
                                    db.add(alert)
                                    
                                    alerts_created.append({
                                        "ttc": critical_vehicle.get('ttc'),
                                        "severity": severity,
                                        "audio_path": audio_path,
                                        "message": critical_vehicle.get('warning')
                                    })
                                    
                                    critical_alerts += 1
                
                else:
                    frame_result["vehicles"] = vehicles
                    total_vehicles += len(vehicles)
            
            # 6. Lane Detection
            if yolop:
                lane_info = yolop.detect_lane(frame)
                frame_result["lanes"] = lane_info
                
                # Cảnh báo lệch làn
                if lane_info and lane_info.get('lane_departure', False):
                    warning = {
                        "type": "lane_departure",
                        "message": "Cảnh báo: Xe đang lệch làn!",
                        "severity": "medium"
                    }
                    frame_result["warnings"].append(warning)
                    total_warnings += 1
                    
                    # Voice alert for lane departure
                    if voice_system:
                        audio_path = voice_system.create_lane_departure_alert()
                        if audio_path:
                            alert = Alert(
                                alert_type="lane_departure",
                                message="Xe đang lệch làn",
                                severity="medium",
                                audio_path=audio_path,
                                created_at=datetime.now()
                            )
                            db.add(alert)
                            alerts_created.append({
                                "type": "lane_departure",
                                "severity": "medium",
                                "audio_path": audio_path
                            })
            
            # Chỉ lưu frame có detection hoặc warning
            if frame_result["vehicles"] or frame_result["warnings"]:
                results.append(frame_result)
            
            frame_count += 1
        
        cap.release()
        
        # Commit alerts to database
        if alerts_created:
            db.commit()
        
        # Tạo summary
        summary = {
            "total_frames": frame_count,
            "processed_frames": len(results),
            "total_vehicles_detected": total_vehicles,
            "total_warnings": total_warnings,
            "min_ttc": round(min_ttc, 2) if min_ttc != float('inf') else None,
            "critical_alerts": critical_alerts,
            "average_fps": round(fps, 2),
            "duration": round(frame_count / fps, 2) if fps > 0 else 0
        }
        
        return {
            "success": True,
            "frames": results,
            "summary": summary,
            "alerts": alerts_created
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý video: {str(e)}")
    
    finally:
        # Xóa file tạm
        if os.path.exists(video_path):
            os.remove(video_path)
    """
    🔥 API Inference - Phân tích video real-time
    
    Args:
        file: Video file để phân tích
        detect_vehicles: Bật vehicle detection (YOLO)
        detect_lanes: Bật lane detection (YOLOP)
        estimate_depth: Bật depth estimation (MiDaS)
        warning_distance: Khoảng cách cảnh báo (meters)
    
    Returns:
        {
            "frames": [
                {
                    "frame_number": int,
                    "timestamp": float,
                    "vehicles": [...],
                    "lanes": {...},
                    "warnings": [...]
                }
            ],
            "summary": {
                "total_frames": int,
                "vehicles_detected": int,
                "warnings_count": int
            }
        }
    """
    
    # Validate video
    if not file.filename.endswith(('.mp4', '.avi', '.mov', '.mkv')):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ video format: mp4, avi, mov, mkv")
    
    # Load models
    try:
        from ai_models.yolo_detector import YOLODetector
        from ai_models.yolop_detector import YOLOPDetector
        from ai_models.depth_estimator import DepthEstimator
        
        yolo = YOLODetector() if detect_vehicles else None
        yolop = YOLOPDetector() if detect_lanes else None
        depth_est = DepthEstimator() if estimate_depth else None
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi load models: {str(e)}")
    
    # Lưu video tạm
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_file:
        tmp_file.write(await file.read())
        video_path = tmp_file.name
    
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        results = []
        frame_count = 0
        total_vehicles = 0
        total_warnings = 0
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            timestamp = frame_count / fps
            frame_result = {
                "frame_number": frame_count,
                "timestamp": round(timestamp, 2),
                "vehicles": [],
                "lanes": None,
                "warnings": []
            }
            
            # 1. Vehicle Detection
            if yolo:
                vehicles = yolo.detect(frame)
                frame_result["vehicles"] = vehicles
                total_vehicles += len(vehicles)
                
                # 2. Depth Estimation cho từng vehicle
                if depth_est:
                    depth_map = depth_est.estimate(frame)
                    
                    for vehicle in vehicles:
                        # Lấy depth tại center của bounding box
                        center_y = int(vehicle['bbox'][1])
                        center_x = int(vehicle['bbox'][0])
                        
                        if 0 <= center_y < depth_map.shape[0] and 0 <= center_x < depth_map.shape[1]:
                            distance = float(depth_map[center_y, center_x])
                            vehicle['distance'] = round(distance, 2)
                            
                            # 3. Cảnh báo nếu quá gần
                            if distance < warning_distance:
                                warning = {
                                    "type": "collision_warning",
                                    "message": f"Cảnh báo: Xe phía trước cách {distance:.1f}m!",
                                    "distance": round(distance, 2),
                                    "severity": "high" if distance < 3 else "medium",
                                    "object": vehicle
                                }
                                frame_result["warnings"].append(warning)
                                total_warnings += 1
            
            # 4. Lane Detection
            if yolop:
                lane_info = yolop.detect_lane(frame)
                frame_result["lanes"] = lane_info
                
                # Cảnh báo lệch làn
                if lane_info and lane_info.get('lane_departure', False):
                    warning = {
                        "type": "lane_departure",
                        "message": "Cảnh báo: Xe đang lệch làn!",
                        "severity": "medium"
                    }
                    frame_result["warnings"].append(warning)
                    total_warnings += 1
            
            # Chỉ lưu frame có detection hoặc warning
            if frame_result["vehicles"] or frame_result["warnings"]:
                results.append(frame_result)
            
            frame_count += 1
        
        cap.release()
        
        # Tạo summary
        summary = {
            "total_frames": frame_count,
            "processed_frames": len(results),
            "total_vehicles_detected": total_vehicles,
            "total_warnings": total_warnings,
            "average_fps": round(fps, 2),
            "duration": round(frame_count / fps, 2) if fps > 0 else 0
        }
        
        return {
            "success": True,
            "frames": results,
            "summary": summary
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý video: {str(e)}")
    
    finally:
        # Xóa file tạm
        if os.path.exists(video_path):
            os.remove(video_path)


@router.post("/image")
async def inference_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Phân tích 1 ảnh
    """
    try:
        from ai_models.yolo_detector import YOLODetector
        from ai_models.yolop_detector import YOLOPDetector
        from ai_models.depth_estimator import DepthEstimator
        
        # Load models
        yolo = YOLODetector()
        yolop = YOLOPDetector()
        depth_est = DepthEstimator()
        
        # Đọc ảnh
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise HTTPException(status_code=400, detail="Không thể đọc ảnh")
        
        # Detect
        vehicles = yolo.detect(image)
        lanes = yolop.detect_lane(image)
        depth_map = depth_est.estimate(image)
        
        # Thêm distance vào vehicles
        for vehicle in vehicles:
            center_y = int(vehicle['bbox'][1])
            center_x = int(vehicle['bbox'][0])
            
            if 0 <= center_y < depth_map.shape[0] and 0 <= center_x < depth_map.shape[1]:
                distance = float(depth_map[center_y, center_x])
                vehicle['distance'] = round(distance, 2)
        
        return {
            "success": True,
            "vehicles": vehicles,
            "lanes": lanes,
            "warnings": [
                {
                    "type": "collision_warning",
                    "message": f"Xe phía trước cách {v['distance']}m",
                    "severity": "high" if v['distance'] < 3 else "medium"
                }
                for v in vehicles if v.get('distance', 999) < 5
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý ảnh: {str(e)}")
