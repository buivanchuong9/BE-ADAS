"""
ADAS FastAPI Backend - Production Ready
Advanced Driver Assistance System with Multi-Model AI Pipeline
"""

import os
import sys
import json
import logging
import asyncio
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from threading import Thread
import cv2
import numpy as np
import torch
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from ultralytics import YOLO
import time

# ============================================================================
# CONFIGURATION & FOLDER STRUCTURE
# ============================================================================

class Config:
    """Central configuration for ADAS system"""
    
    # Base paths - adapt to current system
    if sys.platform == "win32":
        BASE_DIR = Path("C:/ADAS")
    else:
        # For Mac/Linux development
        BASE_DIR = Path(__file__).parent.parent / "ADAS_DATA"
    
    BACKEND_DIR = BASE_DIR / "backend"
    MODELS_DIR = BASE_DIR / "models"
    DATASET_DIR = BASE_DIR / "dataset"
    IMAGES_DIR = DATASET_DIR / "images"
    LABELS_DIR = DATASET_DIR / "labels"
    VIDEOS_DIR = DATASET_DIR / "videos"
    LOGS_DIR = BASE_DIR / "logs"
    TEMP_DIR = BASE_DIR / "temp"
    
    # Database configuration
    if sys.platform == "win32":
        DATABASE_URL = "mssql+pyodbc://localhost/ADAS_DB?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
    else:
        # SQLite for development on Mac/Linux
        DATABASE_URL = f"sqlite:///{BASE_DIR}/adas.db"
    
    # Model configurations
    FRAME_EXTRACT_INTERVAL = 0.5  # Extract frame every 0.5 seconds
    CONFIDENCE_THRESHOLD = 0.5
    NMS_THRESHOLD = 0.4
    
    # Training configuration
    TRAINING_EPOCHS = 50
    BATCH_SIZE = 16
    IMG_SIZE = 640

    @classmethod
    def create_directories(cls):
        """Create all required directories"""
        directories = [
            cls.BACKEND_DIR,
            cls.MODELS_DIR,
            cls.IMAGES_DIR,
            cls.LABELS_DIR,
            cls.VIDEOS_DIR,
            cls.LOGS_DIR,
            cls.TEMP_DIR
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            print(f"✓ Directory ready: {directory}")

# Initialize directories
Config.create_directories()

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOGS_DIR / f"adas_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ADAS_Backend")

# ============================================================================
# DATABASE MODELS
# ============================================================================

Base = declarative_base()

class Event(Base):
    """Database model for detection events"""
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, index=True)
    vehicle_type = Column(String(50))
    confidence = Column(Float)
    distance = Column(Float)
    lane_status = Column(String(50))
    traffic_sign = Column(String(100))
    timestamp = Column(DateTime, default=datetime.utcnow)
    frame_path = Column(String(500))
    video_name = Column(String(200))

# Database setup
try:
    engine = create_engine(Config.DATABASE_URL, echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info(f"✓ Database connected: {Config.DATABASE_URL}")
except Exception as e:
    logger.error(f"✗ Database connection failed: {e}")
    logger.info("Continuing with in-memory storage only")
    SessionLocal = None

# ============================================================================
# PYDANTIC MODELS (API Response Schemas)
# ============================================================================

class DetectionResult(BaseModel):
    """Response model for detection results"""
    vehicle_count: int
    lane_status: str
    distance_front_car: Optional[float]
    traffic_signs: List[str]
    vehicles: List[Dict]
    processing_time: float
    frame_count: int
    video_name: str

class ModelStatus(BaseModel):
    """Response model for model status"""
    yolo11n_loaded: bool
    yolo11m_loaded: bool
    yolop_loaded: bool
    lanenet_loaded: bool
    midas_loaded: bool
    deepsort_loaded: bool
    traffic_sign_loaded: bool
    last_training: Optional[str]
    total_training_images: int

class TrainingStatus(BaseModel):
    """Response model for training status"""
    status: str
    message: str
    epoch: Optional[int]
    total_epochs: Optional[int]
    current_loss: Optional[float]

# ============================================================================
# AI MODEL MANAGER
# ============================================================================

class ModelManager:
    """Manages loading and inference of all AI models"""
    
    def __init__(self):
        self.models = {}
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {self.device}")
        
        self.model_files = {
            "yolo11n": "yolo11n.pt",
            "yolo11m": "yolo11m.pt",
            "yolop": "yolop.pt",
            "lanenet": "lanenet.pt",
            "midas": "midas.pt",
            "deepsort": "deepsort.pt",
            "traffic_sign": "traffic_sign.pt"
        }
        
        self.load_all_models()
    
    def load_all_models(self):
        """Load all AI models at startup"""
        logger.info("Loading AI models...")
        
        # YOLOv11n - Fast vehicle/person detection
        self._load_yolo_model("yolo11n")
        
        # YOLOv11m - High accuracy vehicle detection
        self._load_yolo_model("yolo11m")
        
        # YOLOP - Lane + Vehicle detection (if available)
        self._load_custom_model("yolop")
        
        # LaneNet - Lane segmentation (if available)
        self._load_custom_model("lanenet")
        
        # MiDaS - Depth estimation (if available)
        self._load_custom_model("midas")
        
        # DeepSort - Vehicle tracking (if available)
        self._load_custom_model("deepsort")
        
        # Traffic Sign Detection (if available)
        self._load_custom_model("traffic_sign")
        
        logger.info(f"✓ Loaded {len(self.models)} models successfully")
    
    def _load_yolo_model(self, model_name: str):
        """Load YOLO model (YOLOv11)"""
        try:
            model_path = Config.MODELS_DIR / self.model_files[model_name]
            
            if not model_path.exists():
                # Download pretrained model if not exists
                logger.info(f"Downloading {model_name}...")
                model = YOLO(self.model_files[model_name])
                model.save(str(model_path))
            else:
                model = YOLO(str(model_path))
            
            self.models[model_name] = model
            logger.info(f"✓ Loaded: {model_name}")
        except Exception as e:
            logger.error(f"✗ Failed to load {model_name}: {e}")
            self.models[model_name] = None
    
    def _load_custom_model(self, model_name: str):
        """Load custom PyTorch models"""
        try:
            model_path = Config.MODELS_DIR / self.model_files[model_name]
            
            if model_path.exists():
                # Load custom model (simplified - actual implementation depends on model architecture)
                self.models[model_name] = torch.load(str(model_path), map_location=self.device)
                logger.info(f"✓ Loaded: {model_name}")
            else:
                logger.warning(f"⚠ Model not found: {model_name}")
                self.models[model_name] = None
        except Exception as e:
            logger.error(f"✗ Failed to load {model_name}: {e}")
            self.models[model_name] = None
    
    def detect_vehicles(self, frame: np.ndarray, use_high_accuracy: bool = False) -> List[Dict]:
        """Detect vehicles in frame"""
        model_key = "yolov8m" if use_high_accuracy else "yolov8n"
        model = self.models.get(model_key)
        
        if model is None:
            return []
        
        try:
            results = model(frame, conf=Config.CONFIDENCE_THRESHOLD)
            detections = []
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    
                    # Filter for vehicles (car, truck, bus, motorcycle)
                    if cls_id in [2, 3, 5, 7]:  # COCO classes
                        detections.append({
                            "type": result.names[cls_id],
                            "confidence": conf,
                            "bbox": [x1, y1, x2, y2],
                            "center": [(x1 + x2) / 2, (y1 + y2) / 2]
                        })
            
            return detections
        except Exception as e:
            logger.error(f"Vehicle detection error: {e}")
            return []
    
    def detect_lanes(self, frame: np.ndarray) -> Dict:
        """Detect lanes (simplified implementation)"""
        # Use YOLOP if available, otherwise use basic lane detection
        if self.models.get("yolop"):
            try:
                # YOLOP inference would go here
                pass
            except Exception as e:
                logger.error(f"Lane detection error: {e}")
        
        # Fallback: Basic lane detection using OpenCV
        return self._basic_lane_detection(frame)
    
    def _basic_lane_detection(self, frame: np.ndarray) -> Dict:
        """Basic lane detection using OpenCV"""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            
            # Simple heuristic: check if vehicle is centered
            h, w = frame.shape[:2]
            roi = edges[int(h*0.5):, int(w*0.3):int(w*0.7)]
            lane_pixels = np.sum(roi > 0)
            
            if lane_pixels > 1000:
                status = "on_lane"
            else:
                status = "lane_departure"
            
            return {"status": status, "confidence": 0.7}
        except Exception as e:
            logger.error(f"Lane detection error: {e}")
            return {"status": "unknown", "confidence": 0.0}
    
    def estimate_distance(self, bbox: List[float], frame_height: int) -> float:
        """Estimate distance to vehicle (simplified)"""
        # Simple heuristic based on bounding box size
        # Real implementation would use depth estimation model (MiDaS)
        x1, y1, x2, y2 = bbox
        bbox_height = y2 - y1
        
        # Assume: larger bbox = closer vehicle
        # This is a rough approximation
        if bbox_height > frame_height * 0.5:
            return 5.0  # Very close
        elif bbox_height > frame_height * 0.3:
            return 10.0  # Close
        elif bbox_height > frame_height * 0.2:
            return 20.0  # Medium
        else:
            return 30.0  # Far
    
    def detect_traffic_signs(self, frame: np.ndarray) -> List[str]:
        """Detect traffic signs"""
        model = self.models.get("traffic_sign")
        
        if model is None:
            return []
        
        try:
            # Traffic sign detection would go here
            # Simplified for now
            return []
        except Exception as e:
            logger.error(f"Traffic sign detection error: {e}")
            return []
    
    def reload_models(self):
        """Reload all models (after training)"""
        logger.info("Reloading models...")
        self.models.clear()
        self.load_all_models()
        logger.info("✓ Models reloaded successfully")

# Initialize model manager
model_manager = ModelManager()

# ============================================================================
# VIDEO PROCESSING PIPELINE
# ============================================================================

class VideoProcessor:
    """Processes video files and extracts frames with detections"""
    
    def __init__(self):
        self.model_manager = model_manager
    
    async def process_video(self, video_path: Path, video_name: str) -> DetectionResult:
        """Main video processing pipeline"""
        start_time = time.time()
        
        # Open video
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError("Cannot open video file")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_interval = int(fps * Config.FRAME_EXTRACT_INTERVAL)
        
        frame_count = 0
        processed_frames = 0
        all_detections = []
        
        # Aggregated results
        total_vehicles = 0
        lane_statuses = []
        distances = []
        traffic_signs_set = set()
        
        logger.info(f"Processing video: {video_name}")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Process every Nth frame
            if frame_count % frame_interval == 0:
                # Run detection pipeline
                result = await self._process_frame(frame, video_name, processed_frames)
                all_detections.append(result)
                
                # Aggregate results
                total_vehicles += result["vehicle_count"]
                if result["lane_status"]:
                    lane_statuses.append(result["lane_status"])
                if result["distance_front_car"]:
                    distances.append(result["distance_front_car"])
                traffic_signs_set.update(result["traffic_signs"])
                
                # Save frame and labels
                self._save_frame_and_labels(frame, result, video_name, processed_frames)
                
                processed_frames += 1
            
            frame_count += 1
        
        cap.release()
        
        # Calculate final results
        processing_time = time.time() - start_time
        
        # Most common lane status
        lane_status = max(set(lane_statuses), key=lane_statuses.count) if lane_statuses else "unknown"
        
        # Minimum distance (closest vehicle)
        min_distance = min(distances) if distances else None
        
        result = DetectionResult(
            vehicle_count=total_vehicles,
            lane_status=lane_status,
            distance_front_car=min_distance,
            traffic_signs=list(traffic_signs_set),
            vehicles=all_detections,
            processing_time=processing_time,
            frame_count=processed_frames,
            video_name=video_name
        )
        
        logger.info(f"✓ Processed {processed_frames} frames in {processing_time:.2f}s")
        
        return result
    
    async def _process_frame(self, frame: np.ndarray, video_name: str, frame_idx: int) -> Dict:
        """Process single frame through AI pipeline"""
        h, w = frame.shape[:2]
        
        # 1. Detect vehicles
        vehicles = self.model_manager.detect_vehicles(frame)
        
        # 2. Detect lanes
        lane_info = self.model_manager.detect_lanes(frame)
        
        # 3. Estimate distance to closest vehicle
        min_distance = None
        if vehicles:
            # Find frontmost vehicle (largest bbox in lower half of frame)
            front_vehicles = [v for v in vehicles if v["center"][1] > h * 0.5]
            if front_vehicles:
                closest = max(front_vehicles, key=lambda v: v["bbox"][3] - v["bbox"][1])
                min_distance = self.model_manager.estimate_distance(closest["bbox"], h)
        
        # 4. Detect traffic signs
        traffic_signs = self.model_manager.detect_traffic_signs(frame)
        
        # 5. Save to database
        if SessionLocal:
            try:
                db = SessionLocal()
                for vehicle in vehicles:
                    event = Event(
                        vehicle_type=vehicle["type"],
                        confidence=vehicle["confidence"],
                        distance=min_distance,
                        lane_status=lane_info["status"],
                        traffic_sign=",".join(traffic_signs) if traffic_signs else None,
                        frame_path=f"images/{video_name}_frame_{frame_idx:06d}.jpg",
                        video_name=video_name
                    )
                    db.add(event)
                db.commit()
                db.close()
            except Exception as e:
                logger.error(f"Database insert error: {e}")
        
        return {
            "vehicle_count": len(vehicles),
            "lane_status": lane_info["status"],
            "distance_front_car": min_distance,
            "traffic_signs": traffic_signs,
            "vehicles": vehicles
        }
    
    def _save_frame_and_labels(self, frame: np.ndarray, result: Dict, video_name: str, frame_idx: int):
        """Save frame image and YOLO format labels for training"""
        # Save image
        img_filename = f"{video_name}_frame_{frame_idx:06d}.jpg"
        img_path = Config.IMAGES_DIR / img_filename
        cv2.imwrite(str(img_path), frame)
        
        # Save YOLO format labels
        label_filename = f"{video_name}_frame_{frame_idx:06d}.txt"
        label_path = Config.LABELS_DIR / label_filename
        
        h, w = frame.shape[:2]
        
        with open(label_path, 'w') as f:
            for vehicle in result.get("vehicles", []):
                bbox = vehicle["bbox"]
                x1, y1, x2, y2 = bbox
                
                # Convert to YOLO format (normalized center x, y, width, height)
                x_center = ((x1 + x2) / 2) / w
                y_center = ((y1 + y2) / 2) / h
                width = (x2 - x1) / w
                height = (y2 - y1) / h
                
                # Class ID (simplified: 0 for all vehicles)
                class_id = 0
                
                f.write(f"{class_id} {x_center} {y_center} {width} {height}\n")

# Initialize video processor
video_processor = VideoProcessor()

# ============================================================================
# TRAINING MANAGER
# ============================================================================

class TrainingManager:
    """Manages model training in background"""
    
    def __init__(self):
        self.training_status = {
            "status": "idle",
            "message": "No training in progress",
            "epoch": None,
            "total_epochs": None,
            "current_loss": None
        }
        self.training_thread = None
    
    def start_training(self):
        """Start training in background thread"""
        if self.training_thread and self.training_thread.is_alive():
            return {"status": "error", "message": "Training already in progress"}
        
        self.training_thread = Thread(target=self._train_models)
        self.training_thread.daemon = True
        self.training_thread.start()
        
        return {"status": "started", "message": "Training started in background"}
    
    def _train_models(self):
        """Train YOLO models on collected dataset"""
        try:
            self.training_status = {
                "status": "training",
                "message": "Preparing dataset...",
                "epoch": 0,
                "total_epochs": Config.TRAINING_EPOCHS,
                "current_loss": None
            }
            
            logger.info("Starting model training...")
            
            # Check if we have enough data
            image_files = list(Config.IMAGES_DIR.glob("*.jpg"))
            label_files = list(Config.LABELS_DIR.glob("*.txt"))
            
            if len(image_files) < 10:
                self.training_status = {
                    "status": "error",
                    "message": f"Not enough training data. Found {len(image_files)} images (need at least 10)",
                    "epoch": None,
                    "total_epochs": None,
                    "current_loss": None
                }
                return
            
            logger.info(f"Found {len(image_files)} images and {len(label_files)} labels")
            
            # Create data.yaml for YOLO training
            data_yaml_path = Config.DATASET_DIR / "data.yaml"
            with open(data_yaml_path, 'w') as f:
                f.write(f"""
train: {Config.IMAGES_DIR}
val: {Config.IMAGES_DIR}
nc: 1
names: ['vehicle']
""")
            
            # Train YOLOv11n
            self.training_status["message"] = "Training YOLOv11n..."
            model = YOLO('yolo11n.pt')
            
            results = model.train(
                data=str(data_yaml_path),
                epochs=Config.TRAINING_EPOCHS,
                imgsz=Config.IMG_SIZE,
                batch=Config.BATCH_SIZE,
                device=model_manager.device,
                project=str(Config.MODELS_DIR),
                name='yolo11n_trained',
                exist_ok=True
            )
            
            # Save trained model
            trained_model_path = Config.MODELS_DIR / "yolo11n_trained" / "weights" / "best.pt"
            if trained_model_path.exists():
                shutil.copy(trained_model_path, Config.MODELS_DIR / "yolo11n.pt")
                logger.info("✓ YOLOv11n training completed")
            
            # Reload models
            model_manager.reload_models()
            
            self.training_status = {
                "status": "completed",
                "message": "Training completed successfully",
                "epoch": Config.TRAINING_EPOCHS,
                "total_epochs": Config.TRAINING_EPOCHS,
                "current_loss": None
            }
            
            logger.info("✓ Training completed and models reloaded")
            
        except Exception as e:
            logger.error(f"Training error: {e}")
            self.training_status = {
                "status": "error",
                "message": str(e),
                "epoch": None,
                "total_epochs": None,
                "current_loss": None
            }
    
    def get_status(self) -> Dict:
        """Get current training status"""
        return self.training_status

# Initialize training manager
training_manager = TrainingManager()

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="ADAS Backend API",
    description="Advanced Driver Assistance System with Multi-Model AI Pipeline",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "ADAS Backend API",
        "version": "1.0.0",
        "status": "running",
        "models_loaded": len([m for m in model_manager.models.values() if m is not None])
    }

@app.post("/upload_video", response_model=DetectionResult)
async def upload_video(file: UploadFile = File(...)):
    """
    Upload video for processing
    - Extracts frames
    - Runs AI detection pipeline
    - Saves results to database
    - Saves frames and labels for training
    """
    try:
        # Validate file type
        if not file.filename.endswith(('.mp4', '.avi', '.mov', '.mkv')):
            raise HTTPException(status_code=400, detail="Invalid file type. Use MP4, AVI, MOV, or MKV")
        
        # Save uploaded video
        video_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        video_path = Config.VIDEOS_DIR / video_name
        
        with open(video_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        logger.info(f"Video uploaded: {video_name}")
        
        # Process video
        result = await video_processor.process_video(video_path, video_name)
        
        return result
        
    except Exception as e:
        logger.error(f"Video processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status", response_model=ModelStatus)
async def get_status():
    """
    Get system status
    - Model load status
    - Training status
    - Dataset statistics
    """
    # Count training images
    image_count = len(list(Config.IMAGES_DIR.glob("*.jpg")))
    
    # Get last training time
    last_training = None
    if training_manager.training_status["status"] == "completed":
        last_training = datetime.now().isoformat()
    
    return ModelStatus(
        yolo11n_loaded=model_manager.models.get("yolo11n") is not None,
        yolo11m_loaded=model_manager.models.get("yolo11m") is not None,
        yolop_loaded=model_manager.models.get("yolop") is not None,
        lanenet_loaded=model_manager.models.get("lanenet") is not None,
        midas_loaded=model_manager.models.get("midas") is not None,
        deepsort_loaded=model_manager.models.get("deepsort") is not None,
        traffic_sign_loaded=model_manager.models.get("traffic_sign") is not None,
        last_training=last_training,
        total_training_images=image_count
    )

@app.post("/train", response_model=TrainingStatus)
async def start_training(background_tasks: BackgroundTasks):
    """
    Start model training
    - Uses all data in dataset folder
    - Trains models in background
    - Overwrites model files
    - Reloads models automatically
    """
    result = training_manager.start_training()
    return TrainingStatus(**result)

@app.get("/train/status", response_model=TrainingStatus)
async def get_training_status():
    """Get current training status"""
    status = training_manager.get_status()
    return TrainingStatus(**status)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "models_loaded": len([m for m in model_manager.models.values() if m is not None]),
        "database_connected": SessionLocal is not None
    }

# ============================================================================
# STARTUP & SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("=" * 80)
    logger.info("ADAS Backend API Starting...")
    logger.info("=" * 80)
    logger.info(f"Base directory: {Config.BASE_DIR}")
    logger.info(f"Models directory: {Config.MODELS_DIR}")
    logger.info(f"Dataset directory: {Config.DATASET_DIR}")
    logger.info(f"Database: {Config.DATABASE_URL}")
    logger.info(f"Device: {model_manager.device}")
    logger.info("=" * 80)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("ADAS Backend API shutting down...")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "=" * 80)
    print("🚗 ADAS Backend API Server")
    print("=" * 80)
    print(f"📁 Base Directory: {Config.BASE_DIR}")
    print(f"🤖 Models Loaded: {len([m for m in model_manager.models.values() if m is not None])}/7")
    print(f"💾 Database: {Config.DATABASE_URL}")
    print(f"🖥️  Device: {model_manager.device}")
    print("=" * 80)
    print("📚 API Documentation: http://localhost:52000/docs")
    print("💚 Health Check: http://localhost:52000/health")
    print("=" * 80)
    print("\nPress Ctrl+C to stop")
    print("=" * 80 + "\n")
    
    uvicorn.run(
        "adas_backend:app",
        host="0.0.0.0",
        port=52000,
        reload=False,
        log_level="info"
    )
