# ADAS Backend - Production Ready FastAPI
# Version 3.0.0 - Competition Build

import asyncio
import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from vision.detector import decode_base64_image, run_detection
from vision.lane import detect_lanes

# Basic JSON logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s","module":"%(module)s"}',
)
logger = logging.getLogger("vision-backend")

API_PREFIX = "/api/v1"

# Thread pool for CPU-bound inference
executor = ThreadPoolExecutor(max_workers=max(os.cpu_count() or 4, 4))

app = FastAPI(
    title="ADAS Vision Backend",
    version="1.0.0",
    description="Real-time vision inference (YOLO + lane) with FastAPI/WebSocket",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FrameRequest(BaseModel):
    frame: str  # base64 JPEG


class DetectionResponse(BaseModel):
    label: str
    confidence: float
    bbox: List[float]


class FrameResponse(BaseModel):
    detections: List[DetectionResponse]
    lanes: Dict[str, Any]
    elapsed_ms: float


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    cid = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    request.state.correlation_id = cid
    response = await call_next(request)
    response.headers["x-correlation-id"] = cid
    return response


@app.get(f"{API_PREFIX}/health")
async def health():
    return {"status": "ok"}


@app.post(f"{API_PREFIX}/vision/frame", response_model=FrameResponse)
async def vision_frame(payload: FrameRequest):
    image = decode_base64_image(payload.frame)
    loop = asyncio.get_running_loop()
    detections, elapsed = await loop.run_in_executor(executor, run_detection, image)
    lanes = detect_lanes(image)

    logger.info(
        json.dumps(
            {
                "event": "frame_processed",
                "detections": len(detections),
                "lanes": lanes.get("count", 0),
                "elapsed_ms": round(elapsed * 1000, 2),
            }
        )
    )

    return {
        "detections": detections,
        "lanes": lanes,
        "elapsed_ms": round(elapsed * 1000, 2),
    }


@app.websocket(f"{API_PREFIX}/vision/stream")
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
