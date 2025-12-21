"""
Streaming API endpoints - Phase 1 Critical
Handles real-time detection streaming via HTTP polling (no WebSocket)
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional
from datetime import datetime
import uuid
import random
import base64

from ..models import storage, StreamSession, StreamStartRequest, StreamStopRequest, StreamStatus

router = APIRouter(prefix="/api/stream", tags=["streaming"])


@router.post("/start")
async def start_stream(request: StreamStartRequest):
    """
    Start a streaming session for real-time detection
    
    Request body:
    - source: "webcam" or "video"
    - model_id: Model to use (default: "yolo11n")
    - video_id: Optional video ID if source is "video"
    - config: Optional configuration
    
    Returns:
    - session_id: Unique session ID
    - polling_url: URL to poll for results
    """
    # Validate model exists
    if request.model_id not in storage.models_catalog:
        raise HTTPException(status_code=400, detail=f"Model '{request.model_id}' not found")
    
    model = storage.models_catalog[request.model_id]
    if not model.downloaded:
        raise HTTPException(
            status_code=400, 
            detail=f"Model '{request.model_id}' not downloaded. Please download it first."
        )
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    
    # Create session
    session = StreamSession(
        session_id=session_id,
        source=request.source,
        model_id=request.model_id,
        video_id=request.video_id,
        status=StreamStatus.PROCESSING,
        created_at=datetime.now().isoformat(),
        fps=30.0,
        frame_count=0
    )
    
    storage.stream_sessions[session_id] = session
    
    return {
        "success": True,
        "session_id": session_id,
        "polling_url": f"/api/stream/poll/{session_id}",
        "message": "Streaming session started successfully"
    }


@router.get("/poll/{session_id}")
async def poll_stream(session_id: str):
    """
    Poll for detection results from a streaming session
    
    Path Params:
    - session_id: Session ID from /api/stream/start
    
    Returns:
    - detections: Array of detected objects
    - fps: Current processing FPS
    - latency_ms: Processing latency
    - frame_id: Current frame number
    - status: "processing", "stopped", or "error"
    
    Frontend should poll this endpoint every 100-200ms
    """
    if session_id not in storage.stream_sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    
    session = storage.stream_sessions[session_id]
    
    # Update frame count
    session.frame_count += 1
    
    # Generate dummy detections
    num_detections = random.randint(0, 5)
    detections = []
    
    classes = ["car", "person", "motorcycle", "truck", "bicycle"]
    
    for i in range(num_detections):
        detections.append({
            "class_name": random.choice(classes),
            "confidence": round(random.uniform(0.6, 0.95), 3),
            "bbox": [
                random.randint(50, 800),
                random.randint(50, 400),
                random.randint(900, 1400),
                random.randint(500, 900)
            ]
        })
    
    # Simulate FPS and latency
    fps = round(random.uniform(25.0, 32.0), 1)
    latency_ms = round(random.uniform(15.0, 35.0), 1)
    
    return {
        "success": True,
        "detections": detections,
        "fps": fps,
        "latency_ms": latency_ms,
        "frame_id": session.frame_count,
        "status": session.status.value
    }


@router.post("/frame")
async def process_frame(
    session_id: str = Form(...),
    frame: str = Form(...),
    timestamp: Optional[float] = Form(None)
):
    """
    Process a single frame from webcam
    
    FormData:
    - session_id: Session ID from /api/stream/start
    - frame: Base64 encoded image or binary data
    - timestamp: Frame timestamp
    
    Returns:
    - detections: Detected objects in the frame
    - latency_ms: Processing time
    """
    if session_id not in storage.stream_sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    
    session = storage.stream_sessions[session_id]
    session.frame_count += 1
    
    # Generate dummy detections
    num_detections = random.randint(1, 4)
    detections = []
    
    classes = ["car", "person", "motorcycle", "truck", "bicycle"]
    
    for i in range(num_detections):
        detections.append({
            "class_name": random.choice(classes),
            "confidence": round(random.uniform(0.65, 0.96), 3),
            "bbox": [
                random.randint(50, 800),
                random.randint(50, 400),
                random.randint(900, 1400),
                random.randint(500, 900)
            ]
        })
    
    latency_ms = round(random.uniform(12.0, 28.0), 1)
    
    return {
        "success": True,
        "detections": detections,
        "latency_ms": latency_ms,
        "frame_id": session.frame_count
    }


@router.post("/stop")
async def stop_stream(request: StreamStopRequest):
    """
    Stop a streaming session
    
    Request body:
    - session_id: Session ID to stop
    """
    if request.session_id not in storage.stream_sessions:
        raise HTTPException(status_code=404, detail=f"Session '{request.session_id}' not found")
    
    session = storage.stream_sessions[request.session_id]
    session.status = StreamStatus.STOPPED
    
    return {
        "success": True,
        "message": f"Streaming session stopped. Processed {session.frame_count} frames.",
        "total_frames": session.frame_count
    }
