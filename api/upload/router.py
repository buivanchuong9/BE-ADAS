"""
Upload API Router
Xử lý upload video và auto-labeling
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import os
import cv2
import json
from datetime import datetime
import shutil
from pathlib import Path

from database import get_db
from models import VideoDataset, Label, Detection

router = APIRouter(prefix="/api/upload", tags=["Upload"])

# Cấu hình
UPLOAD_DIR = Path("dataset/raw/videos")
FRAMES_DIR = Path("dataset/raw/frames")
LABELS_DIR = Path("dataset/labels")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
LABELS_DIR.mkdir(parents=True, exist_ok=True)


async def process_video_auto_label(video_path: str, video_id: int, db: Session):
    """
    Background task: Auto-labeling với YOLO + YOLOP + MiDaS
    """
    try:
        from ai_models.yolo_detector import YOLODetector
        from ai_models.yolop_detector import YOLOPDetector
        from ai_models.depth_estimator import DepthEstimator
        
        # Load models
        yolo = YOLODetector()
        yolop = YOLOPDetector()
        depth = DepthEstimator()
        
        # Đọc video
        cap = cv2.VideoCapture(video_path)
        frame_count = 0
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # Xử lý mỗi 5 frame (giảm tải)
            if frame_count % 5 == 0:
                # 1. YOLO: Detect vehicles
                vehicle_boxes = yolo.detect(frame)
                
                # 2. YOLOP: Detect lanes
                lane_info = yolop.detect_lane(frame)
                
                # 3. MiDaS: Estimate depth
                depth_map = depth.estimate(frame)
                
                # 4. Lưu frame
                frame_filename = f"frame_{video_id}_{frame_count}.jpg"
                frame_path = FRAMES_DIR / frame_filename
                cv2.imwrite(str(frame_path), frame)
                
                # 5. Tạo label (YOLO format)
                label_data = []
                for box in vehicle_boxes:
                    x_center, y_center, width, height = box['bbox']
                    class_id = box['class_id']
                    confidence = box['confidence']
                    distance = depth_map[int(box['y'])][int(box['x'])]  # Depth từ MiDaS
                    
                    # YOLO format: class x_center y_center width height
                    label_data.append({
                        "class_id": class_id,
                        "bbox": [x_center, y_center, width, height],
                        "confidence": confidence,
                        "distance": float(distance)
                    })
                
                # 6. Lưu label vào DB
                label_json = json.dumps(label_data)
                db_label = Label(
                    video_id=video_id,
                    frame_number=frame_count,
                    label_data=label_json,
                    has_vehicle=len(vehicle_boxes) > 0,
                    has_lane=lane_info is not None,
                    auto_labeled=True,
                    created_at=datetime.now()
                )
                db.add(db_label)
                
            frame_count += 1
        
        cap.release()
        
        # Update video status
        video = db.query(VideoDataset).filter(VideoDataset.id == video_id).first()
        if video:
            video.total_frames = frame_count
            video.labeled_frames = frame_count // 5
            video.status = "labeled"
            video.processed_at = datetime.now()
        
        db.commit()
        
    except Exception as e:
        print(f"Error auto-labeling: {e}")
        # Update video status to error
        video = db.query(VideoDataset).filter(VideoDataset.id == video_id).first()
        if video:
            video.status = "error"
            video.error_message = str(e)
            db.commit()


@router.post("/video")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    description: str = "",
    auto_label: bool = True,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    🔥 Upload video và tự động label
    
    Args:
        file: Video file
        description: Mô tả video
        auto_label: Tự động chạy YOLO/YOLOP/MiDaS để label
    
    Returns:
        {
            "video_id": int,
            "filename": str,
            "status": "processing" | "uploaded",
            "message": str
        }
    """
    
    # Validate video format
    if not file.filename.endswith(('.mp4', '.avi', '.mov', '.mkv')):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ video format: mp4, avi, mov, mkv")
    
    # Tạo unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    video_path = UPLOAD_DIR / filename
    
    # Lưu video
    try:
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi lưu video: {str(e)}")
    
    # Lấy thông tin video
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if fps > 0 else 0
    cap.release()
    
    # Lưu vào database
    video_record = VideoDataset(
        filename=filename,
        original_filename=file.filename,
        file_path=str(video_path),
        description=description,
        fps=fps,
        total_frames=total_frames,
        width=width,
        height=height,
        duration=duration,
        status="uploaded",
        created_at=datetime.now()
    )
    db.add(video_record)
    db.commit()
    db.refresh(video_record)
    
    # Chạy auto-label nếu được yêu cầu
    if auto_label:
        background_tasks.add_task(process_video_auto_label, str(video_path), video_record.id, db)
        status = "processing"
        message = "Video đang được xử lý và auto-label"
    else:
        status = "uploaded"
        message = "Video đã upload thành công"
    
    return {
        "video_id": video_record.id,
        "filename": filename,
        "total_frames": total_frames,
        "fps": fps,
        "duration": duration,
        "status": status,
        "message": message
    }


@router.get("/video/{video_id}/status")
async def get_video_status(video_id: int, db: Session = Depends(get_db)):
    """
    Kiểm tra trạng thái xử lý video
    """
    video = db.query(VideoDataset).filter(VideoDataset.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video không tồn tại")
    
    return {
        "video_id": video.id,
        "filename": video.filename,
        "status": video.status,
        "total_frames": video.total_frames,
        "labeled_frames": video.labeled_frames,
        "progress": (video.labeled_frames / video.total_frames * 100) if video.total_frames > 0 else 0,
        "error_message": video.error_message
    }
