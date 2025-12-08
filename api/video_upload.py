"""
Video Upload & Storage API
Saves uploaded videos to database and filesystem for training
"""

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
from datetime import datetime
import hashlib
from typing import Optional

from database import get_db
from models import VideoDataset, Camera
from core.config import get_settings
from core.responses import APIResponse
from core.logging_config import get_logger

router = APIRouter(prefix="/api/videos", tags=["Videos"])
settings = get_settings()
logger = get_logger(__name__)

# Ensure upload directory exists
UPLOAD_DIR = settings.RAW_DATASET_PATH
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload", response_model=APIResponse)
async def upload_video(
    file: UploadFile = File(...),
    camera_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Upload video file and save to database + filesystem
    This video will be used for:
    - Real-time inference
    - Training data collection
    - Model improvement
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        # Check file extension
        allowed_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = Path(file.filename).stem
        unique_filename = f"{original_name}_{timestamp}{file_ext}"
        file_path = UPLOAD_DIR / unique_filename
        
        logger.info(f"📹 Uploading video: {unique_filename}")
        
        # Save file to disk
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = file_path.stat().st_size
        logger.info(f"✅ Video saved: {file_path} ({file_size / 1024 / 1024:.2f} MB)")
        
        # Calculate file hash for deduplication
        file_hash = calculate_file_hash(file_path)
        
        # Check if video already exists
        existing = db.query(VideoDataset).filter(
            VideoDataset.file_hash == file_hash
        ).first()
        
        if existing:
            logger.warning(f"⚠️ Duplicate video detected: {file_hash}")
            return APIResponse(
                success=True,
                message="Video already exists in database",
                data={
                    "id": existing.id,
                    "filename": existing.filename,
                    "uploaded_at": existing.uploaded_at.isoformat(),
                    "duplicate": True
                }
            )
        
        # Save to database
        video_record = VideoDataset(
            filename=unique_filename,
            file_path=str(file_path),
            file_size=file_size,
            file_hash=file_hash,
            camera_id=camera_id,
            description=description or "Uploaded via web interface",
            status="uploaded",
            uploaded_at=datetime.now()
        )
        
        db.add(video_record)
        db.commit()
        db.refresh(video_record)
        
        logger.info(f"💾 Video saved to database: ID={video_record.id}")
        
        return APIResponse(
            success=True,
            message="Video uploaded successfully and ready for training",
            data={
                "id": video_record.id,
                "filename": unique_filename,
                "file_path": str(file_path),
                "file_size_mb": round(file_size / 1024 / 1024, 2),
                "uploaded_at": video_record.uploaded_at.isoformat(),
                "camera_id": camera_id,
                "status": "uploaded",
                "ready_for_training": True
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Video upload failed: {e}")
        # Clean up file if database save failed
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=APIResponse)
async def list_videos(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get list of uploaded videos"""
    query = db.query(VideoDataset)
    
    if status:
        query = query.filter(VideoDataset.status == status)
    
    total = query.count()
    videos = query.order_by(VideoDataset.uploaded_at.desc()).offset(offset).limit(limit).all()
    
    return APIResponse(
        success=True,
        message=f"Retrieved {len(videos)} videos",
        data={
            "total": total,
            "videos": [
                {
                    "id": v.id,
                    "filename": v.filename,
                    "file_size_mb": round(v.file_size / 1024 / 1024, 2),
                    "uploaded_at": v.uploaded_at.isoformat(),
                    "status": v.status,
                    "camera_id": v.camera_id,
                    "processed": v.processed,
                    "frame_count": v.frame_count,
                    "labels_count": v.labels_count
                }
                for v in videos
            ]
        }
    )


@router.get("/{video_id}", response_model=APIResponse)
async def get_video_details(video_id: int, db: Session = Depends(get_db)):
    """Get video details"""
    video = db.query(VideoDataset).filter(VideoDataset.id == video_id).first()
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    return APIResponse(
        success=True,
        message="Video details retrieved",
        data={
            "id": video.id,
            "filename": video.filename,
            "file_path": video.file_path,
            "file_size_mb": round(video.file_size / 1024 / 1024, 2),
            "uploaded_at": video.uploaded_at.isoformat(),
            "status": video.status,
            "camera_id": video.camera_id,
            "processed": video.processed,
            "frame_count": video.frame_count,
            "labels_count": video.labels_count,
            "description": video.description
        }
    )


@router.delete("/{video_id}", response_model=APIResponse)
async def delete_video(video_id: int, db: Session = Depends(get_db)):
    """Delete video from database and filesystem"""
    video = db.query(VideoDataset).filter(VideoDataset.id == video_id).first()
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Delete file from filesystem
    file_path = Path(video.file_path)
    if file_path.exists():
        file_path.unlink()
        logger.info(f"🗑️ Deleted file: {file_path}")
    
    # Delete from database
    db.delete(video)
    db.commit()
    
    logger.info(f"💾 Deleted video from database: ID={video_id}")
    
    return APIResponse(
        success=True,
        message="Video deleted successfully",
        data={"id": video_id, "filename": video.filename}
    )


@router.post("/{video_id}/process", response_model=APIResponse)
async def process_video_for_training(video_id: int, db: Session = Depends(get_db)):
    """
    Process video to extract frames and prepare for training
    This will:
    1. Extract frames at intervals
    2. Run inference to get pseudo-labels
    3. Save frames + labels for training
    """
    video = db.query(VideoDataset).filter(VideoDataset.id == video_id).first()
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if video.processed:
        return APIResponse(
            success=True,
            message="Video already processed",
            data={"id": video_id, "status": "already_processed"}
        )
    
    try:
        # Import here to avoid circular dependency
        import cv2
        import numpy as np
        from ai_models.yolo_detector import YOLODetector
        
        logger.info(f"🎬 Processing video: {video.filename}")
        
        # Load video
        cap = cv2.VideoCapture(video.file_path)
        if not cap.isOpened():
            raise Exception("Cannot open video file")
        
        # Get video properties
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Initialize YOLO detector
        detector = YOLODetector()
        
        # Extract frames every N frames (e.g., 1 frame per second)
        frame_interval = fps  # 1 frame per second
        frames_extracted = 0
        labels_created = 0
        
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Process only specific frames
            if frame_idx % frame_interval == 0:
                # Run detection
                results = detector.detect(frame)
                
                # Only save if there are detections with high confidence
                if results and len(results) > 0:
                    # Save frame
                    frame_filename = f"{Path(video.filename).stem}_frame_{frame_idx:06d}.jpg"
                    frame_path = settings.AUTO_COLLECT_PATH / frame_filename
                    cv2.imwrite(str(frame_path), frame)
                    frames_extracted += 1
                    
                    # Save labels in YOLO format
                    label_filename = f"{Path(video.filename).stem}_frame_{frame_idx:06d}.txt"
                    label_path = settings.LABELS_PATH / label_filename
                    
                    with label_path.open('w') as f:
                        for det in results:
                            # Convert to YOLO format: class_id x_center y_center width height
                            class_id = det.get('class_id', 0)
                            bbox = det['bbox']
                            h, w = frame.shape[:2]
                            x_center = (bbox[0] + bbox[2]) / 2 / w
                            y_center = (bbox[1] + bbox[3]) / 2 / h
                            width = (bbox[2] - bbox[0]) / w
                            height = (bbox[3] - bbox[1]) / h
                            
                            f.write(f"{class_id} {x_center} {y_center} {width} {height}\n")
                    
                    labels_created += 1
            
            frame_idx += 1
        
        cap.release()
        
        # Update video record
        video.processed = True
        video.frame_count = frames_extracted
        video.labels_count = labels_created
        video.status = "processed"
        db.commit()
        
        logger.info(f"✅ Video processed: {frames_extracted} frames, {labels_created} labels")
        
        return APIResponse(
            success=True,
            message="Video processed successfully and ready for training",
            data={
                "id": video_id,
                "frames_extracted": frames_extracted,
                "labels_created": labels_created,
                "total_frames": total_frames,
                "status": "processed",
                "ready_for_training": True
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Video processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of file for deduplication"""
    sha256 = hashlib.sha256()
    with file_path.open('rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
