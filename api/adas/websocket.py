"""
ADAS WebSocket API - Real-time Camera Processing
Hỗ trợ webcam/video stream real-time với ADAS features
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, Any, Optional
import json
import base64
import cv2
import numpy as np
from pathlib import Path
import time
import asyncio
from datetime import datetime

# Import ADAS modules
from adas import ADASController
from adas.config import DISPLAY_WIDTH, DISPLAY_HEIGHT

# Import existing services
from ultralytics import YOLO
from database import get_db
from sqlalchemy.orm import Session
from core.config import get_settings

router = APIRouter(prefix="/ws/adas", tags=["ADAS WebSocket"])
settings = get_settings()

# Model cache
yolo_model_cache: Optional[YOLO] = None


def get_yolo_model():
    """Get or load YOLO model (cached) - Cross-platform path support"""
    global yolo_model_cache
    
    if yolo_model_cache is None:
        # Use settings for cross-platform model path
        model_path = settings.yolo_model_path
        
        # Fallback to auto-download if model doesn't exist
        if not model_path.exists():
            model_path = Path(settings.YOLO_MODEL_NAME)  # Will auto-download
        
        print(f"📦 Loading YOLO11 for ADAS: {model_path}")
        yolo_model_cache = YOLO(str(model_path))
        print("✅ YOLO11 loaded")
    
    return yolo_model_cache


def decode_frame(base64_str: str) -> Optional[np.ndarray]:
    """
    Decode base64 image to OpenCV frame
    
    Args:
        base64_str: Base64 encoded image
        
    Returns:
        OpenCV frame or None
    """
    try:
        # Remove data URI prefix if present
        if ',' in base64_str:
            base64_str = base64_str.split(',')[1]
        
        # Decode base64
        img_bytes = base64.b64decode(base64_str)
        
        # Convert to numpy array
        nparr = np.frombuffer(img_bytes, np.uint8)
        
        # Decode image
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        return frame
    
    except Exception as e:
        print(f"❌ Frame decode error: {e}")
        return None


def encode_frame(frame: np.ndarray, quality: int = 85) -> str:
    """
    Encode OpenCV frame to base64 JPEG
    
    Args:
        frame: OpenCV frame
        quality: JPEG quality (1-100)
        
    Returns:
        Base64 encoded string
    """
    try:
        # Encode to JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        _, buffer = cv2.imencode('.jpg', frame, encode_param)
        
        # Convert to base64
        base64_str = base64.b64encode(buffer).decode('utf-8')
        
        return f"data:image/jpeg;base64,{base64_str}"
    
    except Exception as e:
        print(f"❌ Frame encode error: {e}")
        return ""


@router.websocket("/stream")
async def adas_stream(websocket: WebSocket):
    """
    ADAS Real-time WebSocket Stream
    
    Client sends:
    {
        "type": "frame",
        "data": "base64_image",
        "vehicle_speed": 60.0,  // km/h
        "config": {
            "enable_tsr": true,
            "enable_fcw": true,
            "enable_ldw": true,
            "enable_audio": false
        }
    }
    
    Server responds:
    {
        "type": "adas_result",
        "timestamp": "2025-12-07T...",
        "frame": "base64_annotated_image",
        "data": {
            "vehicle_speed": 60.0,
            "speed_limit": 50,
            "alerts": [...],
            "tsr_detections": 2,
            "fcw_detections": 3,
            "ldw_data": {...},
            "closest_vehicle": {...}
        },
        "fps": 28.5
    }
    """
    await websocket.accept()
    print("🔌 ADAS WebSocket connected")
    
    # Initialize ADAS Controller
    adas_controller = None
    frame_count = 0
    start_time = time.time()
    
    try:
        # Load YOLO model
        yolo_model = get_yolo_model()
        
        # Default config
        config = {
            'enable_tsr': True,
            'enable_fcw': True,
            'enable_ldw': True,
            'enable_audio': False,  # Audio disabled for web
            'vehicle_speed': 0.0,
        }
        
        while True:
            try:
                # Receive message from client
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                data = json.loads(message)
                msg_type = data.get('type', '')
                
                # Handle different message types
                if msg_type == 'config':
                    # Update configuration
                    new_config = data.get('config', {})
                    config.update(new_config)
                    
                    # Reinitialize ADAS with new config
                    if adas_controller:
                        adas_controller.cleanup()
                    
                    adas_controller = ADASController(
                        yolo_model=yolo_model,
                        enable_tsr=config.get('enable_tsr', True),
                        enable_fcw=config.get('enable_fcw', True),
                        enable_ldw=config.get('enable_ldw', True),
                        enable_audio=False,  # Always disabled for web
                        vehicle_speed=config.get('vehicle_speed', 0.0),
                    )
                    
                    await websocket.send_json({
                        'type': 'config_updated',
                        'config': config
                    })
                    
                    print(f"⚙️  ADAS config updated: {config}")
                    continue
                
                elif msg_type == 'frame':
                    # Initialize ADAS if not already done
                    if adas_controller is None:
                        adas_controller = ADASController(
                            yolo_model=yolo_model,
                            enable_tsr=config.get('enable_tsr', True),
                            enable_fcw=config.get('enable_fcw', True),
                            enable_ldw=config.get('enable_ldw', True),
                            enable_audio=False,
                            vehicle_speed=config.get('vehicle_speed', 0.0),
                        )
                        print("🚀 ADAS Controller initialized")
                    
                    # Update vehicle speed if provided
                    vehicle_speed = data.get('vehicle_speed', config.get('vehicle_speed', 0.0))
                    adas_controller.set_vehicle_speed(vehicle_speed)
                    
                    # Decode frame
                    frame_data = data.get('data', '')
                    frame = decode_frame(frame_data)
                    
                    if frame is None:
                        await websocket.send_json({
                            'type': 'error',
                            'message': 'Invalid frame data'
                        })
                        continue
                    
                    # Resize frame to standard size
                    if frame.shape[1] != DISPLAY_WIDTH or frame.shape[0] != DISPLAY_HEIGHT:
                        frame = cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
                    
                    # Process frame through ADAS
                    process_start = time.time()
                    output_frame, adas_data = adas_controller.process_frame(frame)
                    process_time = time.time() - process_start
                    
                    # Calculate FPS
                    frame_count += 1
                    elapsed = time.time() - start_time
                    fps = frame_count / elapsed if elapsed > 0 else 0
                    
                    # Encode output frame
                    encoded_frame = encode_frame(output_frame, quality=80)
                    
                    # Prepare response
                    response = {
                        'type': 'adas_result',
                        'timestamp': datetime.utcnow().isoformat(),
                        'frame': encoded_frame,
                        'data': adas_data,
                        'fps': round(fps, 1),
                        'process_time_ms': round(process_time * 1000, 1),
                    }
                    
                    # Send result back to client
                    await websocket.send_json(response)
                
                elif msg_type == 'stats':
                    # Send statistics
                    if adas_controller:
                        stats = adas_controller.get_stats()
                        await websocket.send_json({
                            'type': 'stats',
                            'data': stats
                        })
                    else:
                        await websocket.send_json({
                            'type': 'error',
                            'message': 'ADAS not initialized'
                        })
                
                elif msg_type == 'reset':
                    # Reset ADAS
                    if adas_controller:
                        adas_controller.reset()
                        frame_count = 0
                        start_time = time.time()
                        
                        await websocket.send_json({
                            'type': 'reset_complete'
                        })
                    
                else:
                    await websocket.send_json({
                        'type': 'error',
                        'message': f'Unknown message type: {msg_type}'
                    })
            
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({
                    'type': 'ping',
                    'timestamp': datetime.utcnow().isoformat()
                })
    
    except WebSocketDisconnect:
        print("🔌 ADAS WebSocket disconnected")
    
    except Exception as e:
        print(f"❌ ADAS WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        if adas_controller:
            adas_controller.cleanup()
        
        print("🧹 ADAS WebSocket cleaned up")


@router.websocket("/video-stream")
async def adas_video_stream(websocket: WebSocket):
    """
    ADAS Video File Stream
    Upload video file and process with ADAS
    
    Client sends video chunks, server processes and returns ADAS results
    """
    await websocket.accept()
    print("🎥 ADAS Video Stream connected")
    
    try:
        # TODO: Implement video file processing
        # This would involve receiving video file chunks,
        # processing each frame with ADAS, and streaming results back
        
        await websocket.send_json({
            'type': 'info',
            'message': 'Video stream processing - Coming soon'
        })
        
        while True:
            message = await websocket.receive_text()
            # Process video chunks
            await asyncio.sleep(0.1)
    
    except WebSocketDisconnect:
        print("🎥 Video stream disconnected")
    
    except Exception as e:
        print(f"❌ Video stream error: {e}")
