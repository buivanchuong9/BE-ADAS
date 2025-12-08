import base64
import io
import time
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image
from ultralytics.engine.results import Results

from vision.models import default_detection_model


def decode_base64_image(data: str) -> np.ndarray:
    """Decode base64 JPEG to OpenCV BGR image."""
    if "," in data:
        data = data.split(",")[1]
    img_bytes = base64.b64decode(data)
    image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def encode_base64_image(image: np.ndarray, quality: int = 80) -> str:
    """Encode OpenCV BGR image to base64 JPEG."""
    _, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return base64.b64encode(buffer).decode("utf-8")


def run_detection(image: np.ndarray) -> Tuple[List[Dict[str, Any]], float]:
    """
    Run object detection using YOLO model.
    Returns list of detections and inference time (seconds).
    """
    model = default_detection_model()
    start = time.perf_counter()
    results: List[Results] = model.predict(source=image, verbose=False)
    elapsed = time.perf_counter() - start

    detections: List[Dict[str, Any]] = []
    for r in results:
        boxes = r.boxes
        names = r.names
        for box in boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
            detections.append(
                {
                    "label": names.get(cls_id, str(cls_id)),
                    "confidence": conf,
                    "bbox": [x1, y1, x2, y2],
                }
            )
    return detections, elapsed

