# ============================================
# ADAS Backend - Production Docker Image
# FastAPI + WebSocket + YOLOv11
# ============================================

FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies for OpenCV and other libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    wget \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire backend source code
COPY . .

# Create necessary directories
RUN mkdir -p \
    ai_models/weights \
    dataset/raw \
    dataset/labels \
    dataset/auto_collected \
    logs/alerts \
    adas_core/tests/unit \
    adas_core/tests/integration \
    adas_core/tests/scenarios

# 🆕 Download YOLO11 model automatically (if not mounted via volume)
RUN python3 -c "from ultralytics import YOLO; YOLO('yolo11n.pt')" || echo "Will download on first run"

# Expose port for FastAPI + WebSocket
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run FastAPI with uvicorn (WebSocket support included by default)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
