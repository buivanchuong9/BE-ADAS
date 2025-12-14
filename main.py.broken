# ADAS Backend - Production Ready FastAPI
# Version 3.0.0 - Competition Build
# Cloudflare Tunnel Compatible
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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Body, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from vision.detector import decode_base64_image, run_detection
from vision.lane import detect_lanes

# Production JSON logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s","module":"%(module)s","process":"%(process)d"}',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/backend.log", mode='a') if os.path.exists("logs") else logging.StreamHandler()
    ]
)
logger = logging.getLogger("vision-backend")

# Thread pool for CPU-bound inference with controlled resources
MAX_WORKERS = min(os.cpu_count() or 4, 8)  # Limit max workers to prevent resource exhaustion
executor = ThreadPoolExecutor(
    max_workers=MAX_WORKERS,
    thread_name_prefix="vision-worker"
)

# Configuration constants
FRAME_PROCESSING_TIMEOUT = 30.0  # seconds
MAX_FRAME_SIZE = 10 * 1024 * 1024  # 10MB
REQUEST_TIMEOUT = 60.0  # seconds

# Global state
is_shutting_down = False


# Global Exception Handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions to prevent server crashes"""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    error_id = str(uuid.uuid4())[:8]
    
    logger.error(json.dumps({
        "event": "unhandled_exception",
        "error_id": error_id,
        "correlation_id": correlation_id,
        "error": str(exc),
        "error_type": type(exc).__name__,
        "traceback": traceback.format_exc(),
        "path": request.url.path,
        "method": request.method
    }))
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "error_id": error_id,
            "message": "An unexpected error occurred. Please try again.",
            "correlation_id": correlation_id
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors gracefully - no 422, return safe default"""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    
    logger.warning(json.dumps({
        "event": "validation_warning",
        "correlation_id": correlation_id,
        "errors": str(exc.errors()),
        "body": str(exc.body)
    }))
    
    # Return valid empty response instead of 422
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "detections": [],
            "lanes": {},
            "collision": None,
     
    
    @validator('frame')
    def validate_frame_size(cls, v):
        """Validate frame size to prevent memory issues"""
        if v and len(v) > MAX_FRAME_SIZE:
            logger.warning(f"Frame too large: {len(v)} bytes (max: {MAX_FRAME_SIZE})")
            return None  # Return None for oversized frames
        return v
    
    @validator('tasks')
    def validate_tasks(cls, v):
        """Normalize and validate tasks"""
        if not v:
            return ["detect", "lane"]
        # Normalize task names
        valid_tasks = {"detect", "detection", "lane", "lanes", "collision"}
        norequest_middleware(request: Request, call_next):
    """Add correlation ID, timeout, and error handling"""
    start_time = time.perf_counter()
    cid = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    request.state.correlation_id = cid
    
    # Check if shutting down
    if is_shutting_down:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Server is shutting down", "retry_after": 5}
        )
    
    try:
        # Add timeout to all requests
        response = await asyncio.wait_for(
            call_next(request),
            timeout=REQUEST_TIMEOUT
        )
        
        # Add custom headers
        elapsed = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["x-correlation-id"] = cid
        response.headers["x-processing-time"] = str(elapsed)
        
        return response
        
    except asyncio.TimeoutError:
        logger.error(json.dumps({
            "event": "request_timeout",
            "correlation_id": cid,
            "path": request.url.path,
            "timeout": REQUEST_TIMEOUT
        }))
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={
                "error": "Request timeout",
                "message": f"Request exceeded {REQUEST_TIMEOUT}s timeout",
                "correlation_id": cid
            }
        )
    except Exception as e:
        logger.error(json.dumps({
            "event": "middleware_error",
            "correlation_id": cid,
            "error": str(e),
            "traceback": traceback.format_exc()
        }))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal error", "correlation_id": cid}
        )
    
    yield
    
    # Shutdown
    global is_shutting_down
    is_shutting_down = True
    logger.info("Shutting down gracefully...")
    executor.shutdown(wait=True, cancel_futures=False)
    logger.info("Executor shutdown complete")


app = FastAPI(
    title="ADAS Vision Backend",
    version="1.0.0",
    description="Production-grade real-time vision inference with YOLO + lane detection",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FrameRequest(BaseModel):
    frame: Optional[str] = Field(
       Advanced health check with system status"""
    try:
        health_status = {
            "status": "healthy" if not is_shutting_down else "shutting_down",
            "timestamp": time.time(),
            "uptime_seconds": time.perf_counter(),
            "executor": {
                "max_workers": MAX_WORKERS,
                "active": True
            },
            "version": "1.0.0"
        }
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": time.time()
        4 encoded image (JPEG/PNG). Can be empty for testing.",
        example="data:image/jpeg;base64,/9j/4AAQSkZJRg..."
    )
    tasks: Optional[List[str]] = Field(
        None,
        description="Tasks to run: 'detect', 'lane', 'collision'. Default: ['detect', 'lane']",
        example=["detect", "lane"]
    )
    options: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional options for processing",
        example={"confidence_threshold": 0.5}
    )


class DetectionResponse(BaseModel):
    label: str
    confidence: float
    bbox: List[float]


class FrameResponse(BaseModel):
    detections: List[DetectionResponse] = Field(default_factory=list)
    lanes: Dict[str, Any] = Field(default_factory=dict)
    collision: Optional[Dict[str, Any]] = Field(None, description="Collision detection results")
    elapsed_ms: float


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    cid = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    request.state.correlation_id = cid
    response = await call_next(request)
    response.headers["x-correlation-id"] = cid
    return response


@app.on_event("startup")
async def startup_event():
    """Log all registered routes on startup for debugging"""
    logger.info("=" * 80)
    logger.info("🚀 ADAS Vision Backend Starting...")
    logger.info(f"   Host: 0.0.0.0")
    logger.info(f"   Port: 52000")
    logger.info(f"   Cloudflare Tunnel Compatible: ✅")
    logger.info("=" * 80)
    logger.info("📍 Registered Routes:")
    for route in app.routes:
        if hasattr(route, "methods"):
            methods = ",".join(route.methods)
            logger.info(f"   {methods with timeout protection
    try:
        # Decode image with timeout
        try:
            image = await asyncio.wait_for(
                asyncio.to_thread(decode_base64_image, payload.frame),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.error("Image decode timeout")
            raise ValueError("Image decode timeout")
        except Exception as decode_error:
            logger.error(f"Image decode failed: {decode_error}")
            raise ValueError(f"Invalid image format: {str(decode_error)}")
        
        loop = asyncio.get_running_loop()
        
        # Run detection if requested with timeout
        if "detect" in tasks or "detection" in tasks:
            try:
                detections, detect_elapsed = await asyncio.wait_for(
                    loop.run_in_executor(executor, run_detection, image),
                    timeout=FRAME_PROCESSING_TIMEOUT
                )
                logger.info(json.dumps({
                    "event": "detection_completed",
                    "count": len(detections),
                    "elapsed_ms": round(detect_elapsed * 1000, 2)
                }))
            except asyncio.TimeoutError:
                logger.error(f"Detection timeout after {FRAME_PROCESSING_TIMEOUT}s")
                detections = []
            except Exception as e:
                logger.error(json.dumps({
                    "event": "detection_error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }))
                detections = []
        
        # Run lane detection if requested with timeout
        if "lane" in tasks or "lanes" in tasks:
            try:
                lanes = await asyncio.wait_for(
                    asyncio.to_thread(detect_lanes, image),
                    timeout=10.0
                )
                logger.info(json.dumps({
                    "event": "lane_detection_completed",
                    "lanes_found": lanes.get("count", 0) if isinstance(lanes, dict) else 0
                }))
            except asyncio.TimeoutError:
                logger.error("Lane detection timeout")
                lanes = {}
            except Exception as e:
                logger.error(json.dumps({
                    "event": "lane_detection_error",
                    "error": str(e),
                    "error_type": type(e).__name__
                }))
                lanes = {}
        
        # Collision detection placeholder (can be implemented later)
        if "collision" in tasks:
            try:
                collision = {"status": "not_implemented", "message": "Feature coming soon"}
                logger.info("Collision detection requested but not implemented")
            except Exception as e:
                logger.error(f"Collision detection error: {e}")
                collision = None
        
    except ValueError as ve:
        # Known validation errors
        logger.warning(json.dumps({
            "event": "validation_error",
            "error": str(ve)
        }))
        detections = []
        lanes = {}
        collision = None
        
    except Exception as e:
        # Catch all other errors
        logger.error(json.dumps({
            "event": "frame_processing_error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "detections": [],
            "lanes": {},
            "collision": None,
            "elapsed_ms": elapsed_ms
        }
    
    # Try to decode and process frame
    """WebSocket endpoint with robust error handling"""
    client_id = str(uuid.uuid4())[:8]
    
    try:
        await ws.accept()
        logger.info(f"WebSocket client {client_id} connected")
        
        frame_count = 0
        error_count = 0
        max_errors = 10
        
        while True:
            if is_shutting_down:
                await ws.send_json({"error": "server_shutting_down"})
                break
                
            try:
                # Receive with timeout
                message = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
                data = json.loads(message)
                frame_b64 = data.get("frame")
                
                if not frame_b64:
                    await ws.send_json({"error": "missing_frame", "frame_number": frame_count})
                    continue

                # Process frame with timeout
                try:
                    image = await asyncio.wait_for(
                        asyncio.to_thread(decode_base64_image, frame_b64),
                        timeout=5.0
def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global is_shutting_down
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    is_shutting_down = True


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 80)
    logger.info("🚀 Starting ADAS Backend (Production Mode)")
    logger.info(f"   Host: 0.0.0.0")
    logger.info(f"   Port: 52000")
    logger.info(f"   Workers: {MAX_WORKERS}")
    logger.info(f"   Timeout: {FRAME_PROCESSING_TIMEOUT}s")
    logger.info(f"   Max Frame Size: {MAX_FRAME_SIZE / 1024 / 1024:.1f}MB")
    logger.info("=" * 80)
    
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=52000,
            reload=False,
            log_level="info",
            access_log=True,
            timeout_keep_alive=30,
            limit_concurrency=100,
            limit_max_requests=10000
        )
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1
                    detections, elapsed = await asyncio.wait_for(
                        loop.run_in_executor(executor, run_detection, image),
                        timeout=FRAME_PROCESSING_TIMEOUT
                    )
                    
                    lanes = await asyncio.wait_for(
                        asyncio.to_thread(detect_lanes, image),
                        timeout=10.0
                    )

                    await ws.send_json({
                        "type": "frame_result",
                        "detections": detections,
                        "lanes": lanes,
                        "elapsed_ms": round(elapsed * 1000, 2),
                        "timestamp": time.time(),
                        "frame_number": frame_count
                    })
                    
                    frame_count += 1
                    error_count = 0  # Reset error count on success
                    
                except asyncio.TimeoutError:
                    await ws.send_json({
                        "type": "error",
                        "error": "processing_timeout",
                        "frame_number": frame_count
                    })
                    error_count += 1
                    
                except Exception as process_error:
                    logger.error(f"WS processing error: {process_error}")
                    await ws.send_json({
                        "type": "error",
                        "error": "processing_failed",
                        "message": str(process_error),
                        "frame_number": frame_count
                    })
                    error_count += 1
                
                # Disconnect if too many errors
                if error_count >= max_errors:
                    logger.warning(f"Client {client_id} exceeded max errors ({max_errors})")
                    await ws.send_json({"error": "too_many_errors", "closing": True})
                    break
                    
            except asyncio.TimeoutError:
                # Client inactive for too long
                await ws.send_json({"error": "inactive_timeout"})
                break
                
            except json.JSONDecodeError as je:
                logger.warning(f"Invalid JSON from client {client_id}: {je}")
                await ws.send_json({"error": "invalid_json"})
                error_count += 1
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket client {client_id} disconnected (frames: {frame_count})")
        
    except Exception as e:
        logger.error(json.dumps({
            "event": "websocket_error",
            "client_id": client_id,
            "error": str(e),
            "traceback": traceback.format_exc()
        }))
        try:
            await ws.close(code=1011, reason="Internal server error")
        except:
            pass
    
    finally:
        logger.info(f"WebSocket session {client_id} ended (processed: {frame_count} frames)"ailed: {e}")
                lanes = {}
        
        # Collision detection placeholder (can be implemented later)
        if "collision" in tasks:
            collision = {"status": "not_implemented"}
            logger.info("Collision detection requested but not implemented")
        
    except Exception as e:
        logger.error(json.dumps({
            "event": "frame_processing_error",
            "error": str(e),
            "error_type": type(e).__name__
        }))
        # Return empty results on error instead of crashing
        detections = []
        lanes = {}
        collision = None
    
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    
    logger.info(json.dumps({
        "event": "frame_processed",
        "detections": len(detections),
        "lanes": lanes.get("count", 0) if isinstance(lanes, dict) else 0,
        "elapsed_ms": elapsed_ms,
        "tasks_executed": tasks
    }))
    
    return {
        "detections": detections,
        "lanes": lanes,
        "collision": collision,
        "elapsed_ms": elapsed_ms
    }


@app.websocket("/vision/stream")
async def vision_stream(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            message = await ws.receive_text()
            data = json.loads(message)
            frame_b64 = data.get("frame")
            if not frame_b64:
                await ws.send_json({"error": "missing frame"})
                continue

            image = decode_base64_image(frame_b64)
            loop = asyncio.get_running_loop()
            detections, elapsed = await loop.run_in_executor(executor, run_detection, image)
            lanes = detect_lanes(image)

            await ws.send_json(
                {
                    "type": "frame_result",
                    "detections": detections,
                    "lanes": lanes,
                    "elapsed_ms": round(elapsed * 1000, 2),
                    "timestamp": time.time(),
                }
            )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
        await ws.close(code=1011, reason=str(e))


if __name__ == "__main__":
    logger.info("🔥 Starting ADAS Backend on 0.0.0.0:52000")
    uvicorn.run("main:app", host="0.0.0.0", port=52000, reload=False, log_level="info")
