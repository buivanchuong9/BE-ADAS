# Vision API (ADAS Backend)

Base URL: `/api/v1`

## Endpoints

### POST `/vision/frame`
Accept a single base64 JPEG frame and return detections.

Request body:
```json
{
  "frame": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABA..."
}
```

Response:
```json
{
  "detections": [
    {"label": "person", "confidence": 0.91, "bbox": [x1, y1, x2, y2]}
  ],
  "lanes": {
    "count": 2,
    "lanes": [{"x1": 10, "y1": 100, "x2": 200, "y2": 110}]
  },
  "elapsed_ms": 24.5
}
```

Rate: send at reasonable frame rate (e.g., 5–10 fps) for POST.

### WebSocket `/vision/stream`
Real-time streaming; send frames, receive detections per frame.

Client message:
```json
{"frame": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABA..."}
```

Server message:
```json
{
  "type": "frame_result",
  "detections": [...],
  "lanes": {...},
  "elapsed_ms": 25.1,
  "timestamp": 1711111111.123
}
```

Use 15–30 FPS. Keep payloads small: JPEG quality ~70–80, resize on FE if needed.

## Frame format
- Base64-encoded JPEG. If data URI prefix exists, it is supported.
- Color: RGB; internally converted to BGR for OpenCV.

## Models
- Object detection: YOLOv8n (loaded once, cached).
- Lane detection: lightweight Canny + Hough fallback (replaceable with LaneNet/UltraFastLane).
- Hooks available in `vision/detector.py` and `vision/lane.py`.

## Performance tips
- Prefer WebSocket for streaming.
- If GPU present (CUDA), torch will use it automatically.
- Reduce resolution before sending (e.g., 640x360) for higher FPS.
- Batch on FE if needed; keep messages <1MB.

## Logging
- Each processed frame logs detections, lane count, and latency in JSON format.

