"""
WebSocket API for Real-time Inference
Webcam → Base64 frames → Model inference → Detection results
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Any, List, Optional
import json
import base64
import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO
import time
from collections import defaultdict


router = APIRouter(prefix="/ws", tags=["WebSocket"])

# Model cache
models_cache: Dict[str, Any] = {}
MODELS_DIR = Path("ai_models/weights")

# Object tracking để giảm nháy
class ObjectTracker:
    def __init__(self, iou_threshold=0.3, max_age=10):
        self.tracks = {}  # track_id -> {bbox, class, conf, age, smooth_bbox, frames_seen}
        self.next_id = 0
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.smoothing_factor = 0.7  # 0.7 = moderate smoothing, responsive
        self.min_frames_to_show = 1  # Show IMMEDIATELY - no delay!
        self.confidence_threshold = 0.25  # Show detections > 25%
    
    def calculate_iou(self, box1, box2):
        """Calculate Intersection over Union"""
        x1_min, y1_min, x1_max, y1_max = box1
        x2_min, y2_min, x2_max, y2_max = box2
        
        # Intersection
        inter_xmin = max(x1_min, x2_min)
        inter_ymin = max(y1_min, y2_min)
        inter_xmax = min(x1_max, x2_max)
        inter_ymax = min(y1_max, y2_max)
        
        if inter_xmax < inter_xmin or inter_ymax < inter_ymin:
            return 0.0
        
        inter_area = (inter_xmax - inter_xmin) * (inter_ymax - inter_ymin)
        box1_area = (x1_max - x1_min) * (y1_max - y1_min)
        box2_area = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = box1_area + box2_area - inter_area
        
        return inter_area / union_area if union_area > 0 else 0.0
    
    def smooth_bbox(self, old_bbox, new_bbox):
        """Smooth bounding box transition"""
        alpha = self.smoothing_factor
        return [
            old_bbox[0] * alpha + new_bbox[0] * (1 - alpha),
            old_bbox[1] * alpha + new_bbox[1] * (1 - alpha),
            old_bbox[2] * alpha + new_bbox[2] * (1 - alpha),
            old_bbox[3] * alpha + new_bbox[3] * (1 - alpha)
        ]
    
    def smooth_confidence(self, old_conf, new_conf):
        """Smooth confidence"""
        return old_conf * 0.7 + new_conf * 0.3
    
    def update(self, detections):
        """Update tracks with new detections - SHOW IMMEDIATELY"""
        matched_tracks = set()
        updated_detections = []
        
        for det in detections:
            bbox = det['bbox']
            cls = det['cls']
            conf = det['conf']
            
            # Find best matching track
            best_iou = 0
            best_track_id = None
            
            for track_id, track in self.tracks.items():
                if track['cls'] == cls:
                    iou = self.calculate_iou(bbox, track['smooth_bbox'])
                    if iou > best_iou and iou > self.iou_threshold:
                        best_iou = iou
                        best_track_id = track_id
            
            if best_track_id is not None:
                # Update existing track
                old_bbox = self.tracks[best_track_id]['smooth_bbox']
                old_conf = self.tracks[best_track_id]['conf']
                smooth_bbox = self.smooth_bbox(old_bbox, bbox)
                smooth_conf = self.smooth_confidence(old_conf, conf)
                
                self.tracks[best_track_id]['bbox'] = bbox
                self.tracks[best_track_id]['smooth_bbox'] = smooth_bbox
                self.tracks[best_track_id]['conf'] = smooth_conf
                self.tracks[best_track_id]['age'] = 0
                self.tracks[best_track_id]['frames_seen'] += 1
                self.tracks[best_track_id]['is_new'] = False
                
                matched_tracks.add(best_track_id)
                
                # SHOW IMMEDIATELY - no min_frames requirement!
                det['track_id'] = best_track_id
                det['bbox'] = smooth_bbox
                det['conf'] = smooth_conf
                det['is_new'] = False
                det['stable'] = True
                updated_detections.append(det)
            else:
                # Create new track and SHOW IMMEDIATELY
                track_id = self.next_id
                self.next_id += 1
                self.tracks[track_id] = {
                    'bbox': bbox,
                    'smooth_bbox': bbox,
                    'cls': cls,
                    'conf': conf,
                    'age': 0,
                    'is_new': True,
                    'frames_seen': 1
                }
                # ADD TO OUTPUT IMMEDIATELY!
                det['track_id'] = track_id
                det['is_new'] = True
                det['stable'] = False
                updated_detections.append(det)
        
        # Age out unmatched tracks
        tracks_to_remove = []
        for track_id in self.tracks:
            if track_id not in matched_tracks:
                self.tracks[track_id]['age'] += 1
                # Keep showing for 3 frames to reduce flicker
                if self.tracks[track_id]['age'] <= 3:
                    det = {
                        'bbox': self.tracks[track_id]['smooth_bbox'],
                        'conf': self.tracks[track_id]['conf'] * 0.95,
                        'cls': self.tracks[track_id]['cls'],
                        'class': self.tracks[track_id]['cls'],
                        'track_id': track_id,
                        'is_new': False,
                        'stable': True,
                        'fading': True
                    }
                    updated_detections.append(det)
                
                if self.tracks[track_id]['age'] > self.max_age:
                    tracks_to_remove.append(track_id)
        
        for track_id in tracks_to_remove:
            del self.tracks[track_id]
        
        return updated_detections# Global tracker per WebSocket connection
trackers: Dict[str, ObjectTracker] = {}


def load_model(model_id: str):
    """Load model vào cache với error handling"""
    if model_id in models_cache:
        return models_cache[model_id]
    
    model_file = None
    # Support both YOLOv8 and YOLOv11
    if model_id.startswith("yolov8") or model_id.startswith("yolo11"):
        model_file = MODELS_DIR / f"{model_id}.pt"
    elif model_id == "yolo":
        # Default to yolo11n for generic "yolo" request
        model_file = MODELS_DIR / "yolo11n.pt"
    elif model_id == "yolop":
        model_file = MODELS_DIR / "yolop.pt"
    elif model_id == "midas_small":
        model_file = MODELS_DIR / "midas_small.pt"
    
    if model_file and model_file.exists():
        if model_id.startswith("yolov8") or model_id.startswith("yolo11") or model_id == "yolo":
            try:
                print(f"Loading model: {model_id} from {model_file}")
                models_cache[model_id] = YOLO(str(model_file))
                print(f"✅ Model {model_id} loaded successfully")
            except Exception as e:
                print(f"❌ Error loading {model_id}: {e}")
                return None
        # TODO: Add YOLOP and MiDaS loading
        return models_cache[model_id]
    
    print(f"❌ Model file not found: {model_file}")
    return None


@router.websocket("/infer/{model_id}")
async def websocket_inference(websocket: WebSocket, model_id: str):
    """
    WebSocket endpoint cho real-time inference
    
    Client gửi: {"frame": "base64_encoded_image"}
    Server trả: {"detections": [...], "fps": 30, "latency_ms": 15}
    """
    await websocket.accept()
    
    try:
        # Load model
        model = load_model(model_id)
        if model is None:
            await websocket.send_json({
                "error": f"Model {model_id} not found or not downloaded",
                "success": False
            })
            await websocket.close()
            return
        
        await websocket.send_json({
            "success": True,
            "message": f"Model {model_id} loaded successfully",
            "ready": True
        })
        
        # Initialize tracker cho connection này
        connection_id = str(id(websocket))
        trackers[connection_id] = ObjectTracker(iou_threshold=0.25, max_age=15)
        
        frame_count = 0
        print(f"🎬 Waiting for frames from client...")
        
        while True:
            # Nhận frame từ client
            data = await websocket.receive_text()
            request = json.loads(data)
            
            if frame_count == 0:
                print(f"🎯 First frame received! Starting inference...")
            
            if "frame" not in request:
                await websocket.send_json({"error": "No frame provided"})
                continue
            
            # Decode base64 image
            frame_data = base64.b64decode(request["frame"].split(",")[1] if "," in request["frame"] else request["frame"])
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                await websocket.send_json({"error": "Invalid frame data"})
                continue
            
            # Run inference
            import time
            start_time = time.time()
            
            if model_id.startswith("yolo11") or model_id.startswith("yolov8") or model_id == "yolo":
                # Giảm conf để NHẠY BÉN hơn - phát hiện mọi thứ!
                results = model(frame, conf=0.20, iou=0.45, imgsz=640, verbose=False)[0]
                
                detections = []
                for box in results.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    class_name = results.names[cls]
                    
                    # Tính toán thêm thông tin ADAS
                    width = float(x2 - x1)
                    height = float(y2 - y1)
                    
                    # Ước lượng khoảng cách dựa trên kích thước object (meters)
                    frame_height = frame.shape[0]
                    relative_size = height / frame_height
                    estimated_distance = max(1.0, (1.0 / (relative_size + 0.01)) * 3.0)
                    
                    # Ước lượng TTC (Time To Collision) - giả định tốc độ 50 km/h
                    speed_mps = 50 / 3.6  # 50 km/h to m/s
                    ttc = estimated_distance / speed_mps if speed_mps > 0 else 999
                    
                    # Xác định object nguy hiểm và biển báo
                    danger_classes = ['person', 'car', 'truck', 'bus', 'motorcycle', 'bicycle']
                    traffic_signs = ['stop sign', 'parking meter', 'traffic light']
                    is_danger = class_name in danger_classes
                    is_traffic_sign = class_name in traffic_signs
                    
                    # CHỈ thông báo giọng nói cho BIỂN BÁO
                    voice_alert = None
                    if is_traffic_sign:
                        if class_name == 'stop sign':
                            voice_alert = "Biển báo STOP phía trước! Dừng lại!"
                        elif class_name == 'traffic light':
                            voice_alert = "Đèn giao thông phía trước! Chú ý!"
                        elif class_name == 'parking meter':
                            voice_alert = "Khu vực đỗ xe có trả phí!"
                    
                    # Format theo frontend expect
                    detections.append({
                        "bbox": [float(x1), float(y1), float(x2), float(y2)],
                        "conf": conf,
                        "cls": class_name,
                        "class": class_name,
                        "class_id": cls,
                        "distance_m": round(estimated_distance, 2),
                        "ttc": round(ttc, 2) if is_danger else None,
                        "danger": is_danger,
                        "traffic_sign": is_traffic_sign,
                        "voice_alert": voice_alert
                    })
                
                # Apply tracking để smooth detections
                tracker = trackers[connection_id]
                detections = tracker.update(detections)
                
                latency_ms = (time.time() - start_time) * 1000
                frame_count += 1
                
                # Thống kê theo class
                class_counts = {}
                new_objects_count = 0
                voice_alerts = []
                for det in detections:
                    cls_name = det["cls"]
                    class_counts[cls_name] = class_counts.get(cls_name, 0) + 1
                    if det.get('is_new', False):
                        new_objects_count += 1
                    if det.get('voice_alert'):
                        voice_alerts.append({
                            "message": det['voice_alert'],
                            "priority": "high" if det.get('danger') else "medium"
                        })
                
                # Đếm cảnh báo
                danger_objects = [d for d in detections if d.get("danger", False)]
                critical_count = sum(1 for d in danger_objects if d.get("ttc") and d["ttc"] < 2.0)
                
                # Tạo alerts
                alerts = []
                for det in danger_objects:
                    if det.get("ttc") and det["ttc"] < 3.0:
                        level = "danger" if det["ttc"] < 2.0 else "warning"
                        alerts.append({
                            "level": level,
                            "message": f"{det['cls'].upper()} detected ahead!",
                            "distance": det.get("distance_m", 0),
                            "ttc": det["ttc"]
                        })
                
                # Send results theo format frontend expect
                await websocket.send_json({
                    "success": True,
                    "detections": detections,
                    "alerts": alerts,
                    "voice_alerts": voice_alerts,  # Voice alerts cho frontend
                    "stats": {
                        "fps": round(1000 / latency_ms, 1) if latency_ms > 0 else 0,
                        "inference_time": round(latency_ms, 2),
                        "total_objects": len(detections),
                        "unique_classes": list(class_counts.keys()),
                        "new_objects_count": new_objects_count
                    },
                    "frame_count": frame_count,
                    "model_id": model_id
                })
                
                # Debug log
                if frame_count % 30 == 0:  # Log mỗi 30 frames
                    print(f"📊 Frame {frame_count}: {len(detections)} objects ({new_objects_count} new), {latency_ms:.1f}ms ({round(1000/latency_ms, 1)} FPS), Tracks: {len(tracker.tracks)}")
            
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for model {model_id}")
        # Cleanup tracker
        connection_id = str(id(websocket))
        if connection_id in trackers:
            del trackers[connection_id]
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
        # Cleanup tracker
        connection_id = str(id(websocket))
        if connection_id in trackers:
            del trackers[connection_id]
        try:
            await websocket.send_json({"error": str(e), "success": False})
        except:
            pass


# TEMPORARILY DISABLED - ai_models.adas_unified_pro module needs fixing
# Will re-enable after module is properly implemented
"""
@router.websocket("/adas-unified")
async def websocket_adas_unified(websocket: WebSocket):
    ADAS Unified endpoint - All features in 1 model (PRO VERSION)
    Client sends: {"frame": "base64..."}
    Server returns: {detections, lanes, ldw, stats, alerts, tracks}
    await websocket.accept()
    
    try:
        # Import ADAS Unified Pro Model
        import sys
        from pathlib import Path
        # Ensure backend-python is in path
        backend_path = str(Path(__file__).parent.parent)
        if backend_path not in sys.path:
            sys.path.append(backend_path)
            
        from ai_models.adas_unified_pro import ADASUnifiedPro
        from api.websocket_inference import load_model
        
        # Load YOLO model for object detection
        print("Loading YOLO model for ADAS Pro...")
        yolo_model = load_model("yolo11n")
        if yolo_model is None:
             await websocket.send_json({
                "error": "Failed to load YOLO model",
                "success": False
            })
             return

        # Initialize ADAS Pro
        print("Initializing ADAS Unified Pro...")
        adas_model = ADASUnifiedPro()
        print("✅ ADAS Unified Pro ready")
        
        await websocket.send_json({
            "success": True,
            "message": "ADAS Unified Pro Model loaded",
            "features": ["detection", "lane_detection", "ldw", "tracking", "collision_warning", "bsm"]
        })
        
        while True:
            data = await websocket.receive_text()
            try:
                request = json.loads(data)
            except json.JSONDecodeError:
                continue
            
            if "frame" not in request:
                continue
            
            # Decode frame
            try:
                frame_data = base64.b64decode(request["frame"].split(",")[1] if "," in request["frame"] else request["frame"])
                nparr = np.frombuffer(frame_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            except Exception:
                continue
            
            if frame is None:
                continue
            
            # Run unified inference
            result = adas_model.process_frame(frame, model=yolo_model)
            
            # Send results
            await websocket.send_json({
                "success": True,
                "detections": result['detections'],
                "tracks": result['tracks'],
                "lanes": result['lanes'],
                "ldw": result['ldw'],
                "alerts": result['alerts'],
                "stats": result['stats'],
                "model": "ADAS Unified Pro"
            })
            
    except WebSocketDisconnect:
        print("ADAS Unified WebSocket disconnected")
    except Exception as e:
        print(f"ADAS Unified error: {e}")
        import traceback
        traceback.print_exc()
"""


@router.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    """
    Generic WebSocket endpoint cho multiple models
    Client gửi: {"model_id": "yolo11n", "frame": "base64..."}
    """
    await websocket.accept()
    
    try:
        await websocket.send_json({
            "success": True,
            "message": "WebSocket connected",
            "supported_models": ["yolo11n", "yolo11s", "yolo11m", "yolop", "midas_small"]
        })
        
        current_model = None
        current_model_id = None
        
        while True:
            data = await websocket.receive_text()
            request = json.loads(data)
            
            model_id = request.get("model_id", "yolo11n")
            
            # Reload model if changed
            if model_id != current_model_id:
                current_model = load_model(model_id)
                current_model_id = model_id
                
                if current_model is None:
                    await websocket.send_json({
                        "error": f"Model {model_id} not available",
                        "success": False
                    })
                    continue
            
            if "frame" not in request:
                continue
            
            # Decode frame
            frame_data = base64.b64decode(request["frame"].split(",")[1] if "," in request["frame"] else request["frame"])
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                continue
            
            # Run inference
            import time
            start_time = time.time()
            
            if model_id.startswith("yolo11") or model_id.startswith("yolov8"):
                # Giảm conf threshold và imgsz để nhanh + nhạy hơn
                results = current_model(frame, conf=0.15, iou=0.4, imgsz=416, verbose=False)[0]
                
                detections = []
                for box in results.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    
                    detections.append({
                        "bbox": [float(x1), float(y1), float(x2), float(y2)],
                        "confidence": conf,
                        "class": results.names[cls],
                        "class_id": cls
                    })
                
                latency_ms = (time.time() - start_time) * 1000
                
                # Auto-learning removed: detections are not auto-saved
                
                await websocket.send_json({
                    "success": True,
                    "detections": detections,
                    "latency_ms": round(latency_ms, 2),
                    "model_id": model_id
                })
            
    except WebSocketDisconnect:
        print("WebSocket stream disconnected")
    except Exception as e:
        print(f"WebSocket stream error: {str(e)}")
