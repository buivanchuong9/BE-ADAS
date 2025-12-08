"""
Driver Monitoring API - Real-time driver state monitoring
Endpoints for DMS (Driver Monitoring System)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import base64
import cv2
import numpy as np
from datetime import datetime
import asyncio

router = APIRouter(prefix="/api/driver", tags=["Driver Monitoring"])


@router.websocket("/ws/monitor")
async def websocket_driver_monitor(websocket: WebSocket):
    """
    WebSocket endpoint for real-time driver monitoring
    
    Client sends: {"frame": "base64_encoded_image"}
    Server returns: {
        "state": "alert|drowsy|distracted|phone_use|asleep",
        "attention_score": 0.95,
        "ear": 0.28,
        "perclos": 0.05,
        "yawn_detected": false,
        "yawn_count": 0,
        "head_pose": {"pitch": 0, "yaw": 5, "roll": 0},
        "gaze_direction": "forward",
        "emotion": "neutral",
        "alerts": [],
        "face_detected": true
    }
    """
    await websocket.accept()
    
    try:
        # Import driver monitor
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent.parent.parent))
        from adas_core.perception.driver_monitor import DriverMonitor
        from adas_core.config import get_config
        
        # Initialize driver monitor
        config = get_config()
        dms_config = config.get_perception_config('driver_monitor')
        
        if not dms_config or not dms_config.get('enabled', False):
            await websocket.send_json({
                "error": "Driver monitoring is disabled in config",
                "success": False
            })
            await websocket.close()
            return
        
        print("🎬 Initializing Driver Monitoring System...")
        driver_monitor = DriverMonitor(dms_config)
        
        if not await driver_monitor.initialize():
            await websocket.send_json({
                "error": "Failed to initialize driver monitor",
                "success": False
            })
            await websocket.close()
            return
        
        await websocket.send_json({
            "success": True,
            "message": "Driver Monitoring System ready",
            "features": {
                "drowsiness_detection": dms_config.get('enable_drowsiness', True),
                "distraction_detection": dms_config.get('enable_distraction', True),
                "phone_detection": dms_config.get('enable_phone_detection', True),
                "emotion_recognition": dms_config.get('enable_emotion', True),
            }
        })
        
        frame_count = 0
        print(f"✅ Driver monitor ready, waiting for frames...")
        
        while True:
            # Receive frame from client
            data = await websocket.receive_text()
            request = json.loads(data)
            
            if "frame" not in request:
                await websocket.send_json({"error": "No frame provided"})
                continue
            
            # Decode base64 image
            frame_data = base64.b64decode(
                request["frame"].split(",")[1] if "," in request["frame"] else request["frame"]
            )
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                await websocket.send_json({"error": "Invalid frame data"})
                continue
            
            # Process frame
            result = await driver_monitor.process(frame)
            
            # Extract DMS result from metadata
            dms_result = result.metadata.get('driver_monitor')
            
            if dms_result:
                # Send DMS result to client
                await websocket.send_json({
                    "success": True,
                    "state": dms_result.state.value,
                    "attention_score": round(dms_result.attention_score, 2),
                    "ear": round(dms_result.eye_aspect_ratio, 2),
                    "perclos": round(dms_result.perclos, 2),
                    "yawn_detected": dms_result.yawn_detected,
                    "yawn_count": dms_result.yawn_count,
                    "head_pose": {
                        "pitch": round(dms_result.pitch, 1),
                        "yaw": round(dms_result.yaw, 1),
                        "roll": round(dms_result.roll, 1)
                    },
                    "gaze_direction": dms_result.gaze_direction,
                    "looking_away_duration": round(dms_result.looking_away_duration, 1),
                    "phone_detected": dms_result.phone_detected,
                    "emotion": dms_result.emotion.value,
                    "alerts": dms_result.alerts,
                    "face_detected": dms_result.face_detected,
                    "face_bbox": dms_result.face_bbox,
                    "confidence": round(dms_result.confidence, 2),
                    "stats": {
                        "fps": round(result.fps, 1),
                        "inference_time": round(result.inference_time_ms, 2)
                    },
                    "frame_count": frame_count
                })
            else:
                await websocket.send_json({
                    "error": "Failed to process frame",
                    "success": False
                })
            
            frame_count += 1
            
            # Log every 30 frames
            if frame_count % 30 == 0:
                if dms_result:
                    print(f"📊 Frame {frame_count}: State={dms_result.state.value}, "
                          f"Attention={dms_result.attention_score:.2f}, "
                          f"EAR={dms_result.eye_aspect_ratio:.2f}, "
                          f"Alerts={len(dms_result.alerts)}")
    
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for driver monitoring")
    except Exception as e:
        print(f"Driver monitoring error: {str(e)}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.send_json({"error": str(e), "success": False})
        except:
            pass


@router.get("/stats")
async def get_driver_stats():
    """
    Get driver monitoring statistics
    
    Returns:
        - Total monitoring time
        - Drowsiness events
        - Distraction events
        - Average attention score
    """
    # TODO: Implement statistics tracking
    return {
        "total_sessions": 0,
        "total_monitoring_time": 0,
        "drowsiness_events": 0,
        "distraction_events": 0,
        "avg_attention_score": 0.0
    }
