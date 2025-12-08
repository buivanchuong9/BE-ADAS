"""
Dataset API Router
Quản lý dataset cho training
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime

from database import get_db
from schemas import DatasetResponse, LabelResponse

router = APIRouter(prefix="/api/dataset", tags=["Dataset"])


@router.get("/videos", response_model=List[DatasetResponse])
async def list_videos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: str = None,
    db: Session = Depends(get_db)
):
    """
    Danh sách tất cả videos trong dataset
    """
    from models import VideoDataset
    
    query = db.query(VideoDataset)
    
    if status:
        query = query.filter(VideoDataset.status == status)
    
    videos = query.offset(skip).limit(limit).all()
    
    return videos


@router.get("/videos/{video_id}", response_model=DatasetResponse)
async def get_video(video_id: int, db: Session = Depends(get_db)):
    """
    Chi tiết 1 video
    """
    from models import VideoDataset
    
    video = db.query(VideoDataset).filter(VideoDataset.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video không tồn tại")
    
    return video


@router.get("/videos/{video_id}/labels", response_model=List[LabelResponse])
async def get_video_labels(video_id: int, db: Session = Depends(get_db)):
    """
    Lấy tất cả labels của 1 video
    """
    from models import VideoDataset, Label
    
    # Kiểm tra video tồn tại
    video = db.query(VideoDataset).filter(VideoDataset.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video không tồn tại")
    
    # Lấy labels
    labels = db.query(Label).filter(Label.video_id == video_id).all()
    
    return labels


@router.delete("/videos/{video_id}")
async def delete_video(video_id: int, db: Session = Depends(get_db)):
    """
    Xóa video và labels
    """
    from models import VideoDataset, Label
    import os
    
    video = db.query(VideoDataset).filter(VideoDataset.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video không tồn tại")
    
    # Xóa file
    if os.path.exists(video.file_path):
        os.remove(video.file_path)
    
    # Xóa labels
    db.query(Label).filter(Label.video_id == video_id).delete()
    
    # Xóa video record
    db.delete(video)
    db.commit()
    
    return {"success": True, "message": "Đã xóa video"}


@router.get("/stats")
async def get_dataset_stats(db: Session = Depends(get_db)):
    """
    Thống kê dataset
    """
    from models import VideoDataset, Label
    from sqlalchemy import func
    
    total_videos = db.query(func.count(VideoDataset.id)).scalar()
    total_labeled = db.query(func.count(VideoDataset.id)).filter(
        VideoDataset.status == "labeled"
    ).scalar()
    total_frames = db.query(func.sum(VideoDataset.total_frames)).scalar() or 0
    total_labels = db.query(func.count(Label.id)).scalar()
    
    # Labels với vehicle
    labels_with_vehicle = db.query(func.count(Label.id)).filter(
        Label.has_vehicle == True
    ).scalar()
    
    # Labels với lane
    labels_with_lane = db.query(func.count(Label.id)).filter(
        Label.has_lane == True
    ).scalar()
    
    return {
        "total_videos": total_videos,
        "labeled_videos": total_labeled,
        "total_frames": total_frames,
        "total_labels": total_labels,
        "labels_with_vehicle": labels_with_vehicle,
        "labels_with_lane": labels_with_lane,
        "auto_labeled_percentage": round(
            (labels_with_vehicle / total_labels * 100) if total_labels > 0 else 0,
            2
        )
    }
