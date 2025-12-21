"""
MAIN FASTAPI APPLICATION
=========================
Entry point for ADAS Video Analysis Backend.

This is the ONLY file that knows about FastAPI.
All AI logic is isolated in perception/ module.

Author: Senior ADAS Engineer
Date: 2025-12-21
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import sys

# Add parent directory to path for absolute imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import API routers (absolute import)
from app.api.video import router as video_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# Lifespan event handler (replaces deprecated on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=" * 80)
    logger.info("ADAS Video Analysis API Starting...")
    logger.info("=" * 80)
    logger.info("FastAPI application initialized")
    logger.info("Perception modules ready")
    logger.info("Storage directories configured")
    logger.info("API Documentation: https://adas-api.aiotlab.edu.vn/docs")
    logger.info("=" * 80)
    
    yield
    
    # Shutdown
    logger.info("=" * 80)
    logger.info("ADAS Video Analysis API Shutting Down...")
    logger.info("=" * 80)


# Create FastAPI app with lifespan
app = FastAPI(
    title="ADAS Video Analysis API",
    description="""
    Scientific ADAS Demo System for Research Council Evaluation
    
    ## Features
    
    ### Dashcam Video Analysis
    - **Curved Lane Detection**: Real geometry-based lane detection with polynomial fitting
    - **Object Detection**: YOLOv11-based vehicle and pedestrian detection
    - **Distance Estimation**: Monocular distance estimation with risk classification
    - **Lane Departure Warning**: Real-time LDW based on vehicle offset
    - **Forward Collision Warning**: TTC-based collision risk assessment
    - **Traffic Sign Recognition**: Detection of stop signs, speed limits, warning signs
    
    ### In-Cabin Video Analysis
    - **Driver Monitoring**: MediaPipe Face Mesh for facial analysis
    - **Drowsiness Detection**: EAR, MAR, and head pose-based drowsiness detection
    
    ## Architecture
    
    - **Frontend**: Upload video, poll for results, display annotated video
    - **Backend API** (FastAPI): REST endpoints for upload/results
    - **Service Layer**: Job management and orchestration
    - **Perception Layer**: Isolated AI modules (NO FastAPI dependency)
    
    ## Endpoints
    
    - `POST /api/video/upload`: Upload video for analysis
    - `GET /api/video/result/{job_id}`: Get analysis results
    - `GET /api/video/download/{job_id}/{filename}`: Download processed video
    
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS (allow frontend to call API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(video_router)


@app.get("/")
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "service": "ADAS Video Analysis API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "upload": "POST /api/video/upload",
            "result": "GET /api/video/result/{job_id}",
            "download": "GET /api/video/download/{job_id}/{filename}",
            "health": "GET /api/video/health",
            "docs": "GET /docs"
        },
        "documentation": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ADAS Video Analysis API"
    }


if __name__ == "__main__":
    import uvicorn
    
    # Production: https://adas-api.aiotlab.edu.vn/ on port 52000
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=52000,
        reload=True,
        log_level="info"
    )

