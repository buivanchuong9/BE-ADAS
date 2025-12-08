import threading
from functools import lru_cache
from typing import Any, Dict

from ultralytics import YOLO


_model_lock = threading.Lock()
_cached_models: Dict[str, Any] = {}


def load_yolo(model_name: str = "yolov8n.pt") -> YOLO:
    """
    Load YOLO model once and cache it.
    """
    with _model_lock:
        if model_name not in _cached_models:
            _cached_models[model_name] = YOLO(model_name)
        return _cached_models[model_name]


@lru_cache(maxsize=1)
def default_detection_model() -> YOLO:
    return load_yolo("yolov8n.pt")

