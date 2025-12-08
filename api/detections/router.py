"""
Detections API Router
Endpoints cho real-time detections từ frontend
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime

from database import get_db
from models import Detection, Event, Camera

router = APIRouter(prefix="/api/detections", tags=["Detections"])


@router.get("/recent")
async def get_recent_detections(
    limit: int = 20,
    camera_id: int = None,
    class_name: str = None,
    db: Session = Depends(get_db)
):
    """
    Lấy danh sách detections gần đây nhất
    Dùng cho live dashboard/ADAS page
    """
    query = db.query(Detection).order_by(Detection.timestamp.desc())
    
    if camera_id:
        query = query.filter(Detection.camera_id == camera_id)
    
    if class_name:
        query = query.filter(Detection.class_name == class_name)
    
    detections = query.limit(limit).all()
    
    # Parse bounding_box JSON string
    import json
    
    return {
        "success": True,
        "detections": [
            {
                "id": d.id,
                "class_name": d.class_name,
                "confidence": d.confidence,
                "bbox": json.loads(d.bounding_box) if d.bounding_box else [],
                "timestamp": d.timestamp.isoformat() if d.timestamp else None,
                "camera_id": d.camera_id,
                "distance_meters": d.distance_meters,
                "relative_speed": d.relative_speed
            }
            for d in detections
        ],
        "total": len(detections)
    }


@router.post("/save")
async def save_detection(
    detection: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Lưu detection từ frontend real-time inference
    
    Body:
    {
        "class_name": "car",
        "confidence": 0.95,
        "bbox": [x1, y1, x2, y2],
        "camera_id": 1,
        "distance_meters": 15.5 (optional),
        "relative_speed": 5.0 (optional)
    }
    """
    import json
    
    try:
        # Validate bbox
        bbox = detection.get("bbox", [])
        if len(bbox) != 4:
            raise HTTPException(status_code=400, detail="bbox must have 4 values [x1, y1, x2, y2]")
        
        db_detection = Detection(
            class_name=detection["class_name"],
            confidence=detection["confidence"],
            bounding_box=json.dumps(bbox),  # Store as JSON string
            camera_id=detection.get("camera_id", 1),
            distance_meters=detection.get("distance_meters"),
            relative_speed=detection.get("relative_speed"),
            trip_id=detection.get("trip_id"),
            frame_number=detection.get("frame_number"),
            timestamp=datetime.utcnow()
        )
        
        db.add(db_detection)
        db.commit()
        db.refresh(db_detection)
        
        return {
            "success": True,
            "id": db_detection.id,
            "message": "Detection saved successfully"
        }
    
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required field: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error saving detection: {str(e)}")


@router.get("/stats")
async def get_detection_stats(
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """
    Thống kê detections theo class trong N giờ qua
    """
    from sqlalchemy import func
    from datetime import timedelta
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    # Count by class
    class_counts = db.query(
        Detection.class_name,
        func.count(Detection.id).label('count'),
        func.avg(Detection.confidence).label('avg_confidence')
    ).filter(
        Detection.timestamp >= cutoff_time
    ).group_by(Detection.class_name).all()
    
    # Total detections
    total = db.query(func.count(Detection.id)).filter(
        Detection.timestamp >= cutoff_time
    ).scalar()
    
    return {
        "success": True,
        "time_range_hours": hours,
        "total_detections": total or 0,
        "by_class": [
            {
                "class_name": row.class_name,
                "count": row.count,
                "avg_confidence": float(row.avg_confidence) if row.avg_confidence else 0
            }
            for row in class_counts
        ]
    }


@router.delete("/{detection_id}")
async def delete_detection(
    detection_id: int,
    db: Session = Depends(get_db)
):
    """Xóa một detection"""
    detection = db.query(Detection).filter(Detection.id == detection_id).first()
    
    if not detection:
        raise HTTPException(status_code=404, detail="Detection not found")
    
    db.delete(detection)
    db.commit()
    
    return {
        "success": True,
        "message": f"Detection {detection_id} deleted"
    }
