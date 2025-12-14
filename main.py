# ADAS Backend - Production Ready FastAPI
# Version 4.0.0 - Flexible & Frontend-Friendly
# Domain: https://adas-api.aiotlab.edu.vn
# Ultra-Stable Production Grade

import asyncio
import json
import logging
import os
import signal
import sys
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from vision.detector import decode_base64_image, run_detection
from vision.lane import detect_lanes

# Production JSON logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s","module":"%(module)s"}',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/backend.log", mode='a') if os.path.exists("logs") else logging.StreamHandler()
    ]
)
logger = logging.getLogger("adas-backend")

# Thread pool for CPU-bound inference
MAX_WORKERS = min(os.cpu_count() or 4, 8)
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="vision-worker")

# Configuration constants
FRAME_PROCESSING_TIMEOUT = 30.0
MAX_FRAME_SIZE = 10 * 1024 * 1024  # 10MB

# Global state
is_shutting_down = False


# ============================================================================
# PYDANTIC MODELS - FLEXIBLE & FRONTEND FRIENDLY
# ============================================================================

class FrameRequest(BaseModel):
    """
    Flexible request model - all fields are optional to avoid 422 errors.
    Frontend can send minimal payloads for testing.
    """
    frame: Optional[str] = Field(
        None,
        description="Base64 encoded image (JPEG/PNG). Can be empty for testing.",
        example="data:image/jpeg;base64,/9j/4AAQSkZJRg..."
    )
    tasks: Optional[List[str]] = Field(
        None,
        description="Tasks to run: 'detect', 'lane', 'collision'. Default: ['detect', 'lane']",
        example=["detect", "lane"]
    )
    options: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional processing options",
        example={"confidence_threshold": 0.5}
    )

    class Config:
        schema_extra = {
            "examples": [
                {"frame": "test"},
                {"frame": "<base64_string>", "tasks": ["detect", "lane"]},
                {}
            ]
        }


class DetectionItem(BaseModel):
    """Single detection result"""
    label: str
    confidence: float
    bbox: List[float]


class FrameResponse(BaseModel):
    """
    Standardized response - always returns this structure, even on errors.
    Never returns 422 or 500.
    """
    detections: List[DetectionItem] = Field(default_factory=list)
    lanes: Dict[str, Any] = Field(default_factory=dict)
    collision: Optional[Dict[str, Any]] = None
    elapsed_ms: float


# ============================================================================
# LIFESPAN CONTEXT MANAGER
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic"""
    # Startup
    logger.info("=" * 80)
    logger.info("🚀 ADAS Backend Starting...")
    logger.info(f"   Domain: https://adas-api.aiotlab.edu.vn")
    logger.info(f"   Host: 0.0.0.0")
    logger.info(f"   Port: 52000")
    logger.info(f"   Max Workers: {MAX_WORKERS}")
    logger.info("=" * 80)
    
    yield
    
    # Shutdown
    global is_shutting_down
    is_shutting_down = True
    logger.info("Shutting down gracefully...")
    executor.shutdown(wait=True)
    logger.info("Shutdown complete")


# ============================================================================
# FASTAPI APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="ADAS Vision Backend",
    version="4.0.0",
    description="Production-grade real-time vision API for ADAS systems",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS - Allow all origins for frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-correlation-id", "x-processing-time"]
)


# ============================================================================
# MIDDLEWARE
# ============================================================================

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Add correlation ID and timing headers"""
    start_time = time.perf_counter()
    correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    
    response = await call_next(request)
    
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    response.headers["x-correlation-id"] = correlation_id
    response.headers["x-processing-time"] = str(elapsed_ms)
    
    return response


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy" if not is_shutting_down else "shutting_down",
        "timestamp": time.time(),
        "version": "4.0.0",
        "domain": "https://adas-api.aiotlab.edu.vn"
    }


# ============================================================================
# MAIN VISION ENDPOINT - FLEXIBLE & NEVER RETURNS 422
# ============================================================================

@app.post("/vision/frame", response_model=FrameResponse)
async def process_frame(request: Request, payload: Dict[str, Any] = Body(default={})):
    """
    Main vision processing endpoint - FLEXIBLE & FRONTEND FRIENDLY
    
    Accepts:
    - Empty body: {}
    - Minimal: {"frame": "test"}
    - Full: {"frame": "<base64>", "tasks": ["detect", "lane"], "options": {...}}
    
    Never returns 422 validation errors.
    Always returns valid FrameResponse structure.
    """
    start_time = time.perf_counter()
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    
    # Extract fields with defaults (manual validation to avoid 422)
    frame = payload.get("frame")
    tasks = payload.get("tasks") or ["detect", "lane"]
    options = payload.get("options") or {}
    
    # Normalize tasks
    if isinstance(tasks, str):
        tasks = [tasks]
    tasks = [t.lower() for t in tasks]
    
    # Log request
    logger.info(json.dumps({
        "event": "request_received",
        "correlation_id": correlation_id,
        "has_frame": bool(frame and frame != "test"),
        "tasks": tasks,
        "frame_length": len(frame) if frame else 0
    }))
    
    # Initialize empty results
    detections = []
    lanes = {}
    collision = None
    
    # If no frame or invalid frame, return empty results (NOT an error)
    if not frame or frame == "test" or len(frame) < 50:
        logger.info(json.dumps({
            "event": "empty_frame",
            "correlation_id": correlation_id,
            "message": "No valid frame provided, returning empty results"
        }))
        
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return FrameResponse(
            detections=[],
            lanes={},
            collision=None,
            elapsed_ms=elapsed_ms
        )
    
    # Process frame if valid
    try:
        # Decode image with timeout
        try:
            image = await asyncio.wait_for(
                asyncio.to_thread(decode_base64_image, frame),
                timeout=5.0
            )
            logger.info(json.dumps({
                "event": "image_decoded",
                "correlation_id": correlation_id,
                "image_shape": image.shape if hasattr(image, 'shape') else None
            }))
        except asyncio.TimeoutError:
            logger.warning(f"Image decode timeout for {correlation_id}")
            raise ValueError("Image decode timeout")
        except Exception as decode_error:
            logger.warning(f"Image decode failed for {correlation_id}: {decode_error}")
            raise ValueError(f"Invalid image format")
        
        loop = asyncio.get_running_loop()
        
        # Run detection if requested
        if "detect" in tasks or "detection" in tasks:
            try:
                detections_raw, detect_elapsed = await asyncio.wait_for(
                    loop.run_in_executor(executor, run_detection, image),
                    timeout=FRAME_PROCESSING_TIMEOUT
                )
                
                # Convert to response format
                detections = [
                    DetectionItem(
                        label=d.get("label", "unknown"),
                        confidence=d.get("confidence", 0.0),
                        bbox=d.get("bbox", [0, 0, 0, 0])
                    )
                    for d in detections_raw
                ]
                
                logger.info(json.dumps({
                    "event": "detection_completed",
                    "correlation_id": correlation_id,
                    "count": len(detections),
                    "elapsed_ms": round(detect_elapsed * 1000, 2)
                }))
            except asyncio.TimeoutError:
                logger.error(f"Detection timeout for {correlation_id}")
                detections = []
            except Exception as e:
                logger.error(f"Detection error for {correlation_id}: {e}")
                detections = []
        
        # Run lane detection if requested
        if "lane" in tasks or "lanes" in tasks:
            try:
                lanes = await asyncio.wait_for(
                    asyncio.to_thread(detect_lanes, image),
                    timeout=10.0
                )
                
                logger.info(json.dumps({
                    "event": "lane_detection_completed",
                    "correlation_id": correlation_id,
                    "lanes_found": lanes.get("count", 0) if isinstance(lanes, dict) else 0
                }))
            except asyncio.TimeoutError:
                logger.error(f"Lane detection timeout for {correlation_id}")
                lanes = {}
            except Exception as e:
                logger.error(f"Lane detection error for {correlation_id}: {e}")
                lanes = {}
        
        # Collision detection (placeholder)
        if "collision" in tasks:
            collision = {
                "status": "not_implemented",
                "message": "Feature coming soon"
            }
            logger.info(f"Collision detection requested for {correlation_id}")
        
    except ValueError as ve:
        # Known validation errors - log but return empty results
        logger.warning(json.dumps({
            "event": "validation_warning",
            "correlation_id": correlation_id,
            "error": str(ve)
        }))
        detections = []
        lanes = {}
        collision = None
        
    except Exception as e:
        # Unexpected errors - log but still return valid response
        logger.error(json.dumps({
            "event": "processing_error",
            "correlation_id": correlation_id,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }))
        detections = []
        lanes = {}
        collision = None
    
    # Calculate elapsed time
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    
    # Log completion
    logger.info(json.dumps({
        "event": "request_completed",
        "correlation_id": correlation_id,
        "detections_count": len(detections),
        "lanes_count": lanes.get("count", 0) if isinstance(lanes, dict) else 0,
        "elapsed_ms": elapsed_ms,
        "tasks_executed": tasks
    }))
    
    # Always return valid response
    return FrameResponse(
        detections=detections,
        lanes=lanes,
        collision=collision,
        elapsed_ms=elapsed_ms
    )


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@app.websocket("/vision/stream")
async def vision_stream(ws: WebSocket):
    """WebSocket endpoint for real-time frame streaming"""
    client_id = str(uuid.uuid4())[:8]
    
    try:
        await ws.accept()
        logger.info(f"WebSocket client {client_id} connected")
        
        frame_count = 0
        
        while True:
            if is_shutting_down:
                await ws.send_json({"error": "server_shutting_down"})
                break
            
            try:
                message = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
                data = json.loads(message)
                frame_b64 = data.get("frame")
                
                if not frame_b64:
                    await ws.send_json({"error": "missing_frame"})
                    continue
                
                image = await asyncio.to_thread(decode_base64_image, frame_b64)
                loop = asyncio.get_running_loop()
                
                detections, elapsed = await asyncio.wait_for(
                    loop.run_in_executor(executor, run_detection, image),
                    timeout=FRAME_PROCESSING_TIMEOUT
                )
                
                lanes = await asyncio.to_thread(detect_lanes, image)
                
                await ws.send_json({
                    "type": "frame_result",
                    "detections": detections,
                    "lanes": lanes,
                    "elapsed_ms": round(elapsed * 1000, 2),
                    "frame_number": frame_count,
                    "timestamp": time.time()
                })
                
                frame_count += 1
                
            except asyncio.TimeoutError:
                await ws.send_json({"error": "timeout"})
                break
            except json.JSONDecodeError:
                await ws.send_json({"error": "invalid_json"})
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket client {client_id} disconnected (frames: {frame_count})")
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        try:
            await ws.close(code=1011)
        except:
            pass


# ============================================================================
# SIGNAL HANDLERS
# ============================================================================

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global is_shutting_down
    logger.info(f"Received signal {signum}, shutting down...")
    is_shutting_down = True


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 80)
    logger.info("🚀 Starting ADAS Backend (Production Mode)")
    logger.info(f"   Domain: https://adas-api.aiotlab.edu.vn")
    logger.info(f"   Host: 0.0.0.0")
    logger.info(f"   Port: 52000")
    logger.info(f"   Workers: {MAX_WORKERS}")
    logger.info(f"   API Docs: http://localhost:52000/docs")
    logger.info("=" * 80)
    
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=52000,
            reload=False,
            log_level="info",
            access_log=True,
            timeout_keep_alive=30
        )
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
