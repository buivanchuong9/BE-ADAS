# Core configuration - Production grade
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads" / "videos"
LOGS_DIR = BASE_DIR / "logs"
MODELS_DIR = BASE_DIR / "ai_models" / "weights"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", 52000))
DEBUG_MODE = os.getenv("DEBUG", "False").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./adas_backend.db")

DEFAULT_CONFIDENCE_THRESHOLD = 0.5
MAX_VIDEO_SIZE_MB = 500
MAX_WORKERS = min(os.cpu_count() or 4, 8)

DEFAULT_ENABLE_FCW = True
DEFAULT_ENABLE_LDW = True
DEFAULT_ENABLE_TSR = True
DEFAULT_ENABLE_PEDESTRIAN = True
