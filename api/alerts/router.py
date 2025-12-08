"""
Alerts API Router
Quản lý voice alerts và warnings
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime, timedelta
import os

from database import get_db
from models import Alert

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


@router.get("/latest")
async def get_latest_alerts(
    limit: int = Query(10, ge=1, le=100),
    severity: str = None,
    unplayed_only: bool = False,
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Lấy alerts mới nhất
    
    Args:
        limit: Số lượng alerts
        severity: Filter by severity (critical, high, medium, low)
        unplayed_only: Chỉ lấy alerts chưa play
    
    Returns:
        List of alerts with audio URLs
    """
    query = db.query(Alert).order_by(Alert.created_at.desc())
    
    if severity:
        query = query.filter(Alert.severity == severity)
    
    if unplayed_only:
        query = query.filter(Alert.played == False)
    
    alerts = query.limit(limit).all()
    
    result = []
    for alert in alerts:
        result.append({
            "id": alert.id,
            "ttc": alert.ttc,
            "distance": alert.distance,
            "relative_speed": alert.relative_speed,
            "severity": alert.severity,
            "alert_type": alert.alert_type,
            "message": alert.message,
            "audio_url": f"/api/alerts/audio/{alert.id}" if alert.audio_path else None,
            "played": alert.played,
            "created_at": alert.created_at.isoformat()
        })
    
    return result


@router.get("/audio/{alert_id}")
async def get_alert_audio(alert_id: int, db: Session = Depends(get_db)):
    """
    Download alert audio file
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    if not alert.audio_path or not os.path.exists(alert.audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    # Mark as played
    alert.played = True
    db.commit()
    
    return FileResponse(
        alert.audio_path,
        media_type="audio/wav",
        filename=os.path.basename(alert.audio_path)
    )


@router.post("/mark-played/{alert_id}")
async def mark_alert_played(alert_id: int, db: Session = Depends(get_db)):
    """
    Đánh dấu alert đã play
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.played = True
    db.commit()
    
    return {"success": True, "message": "Alert marked as played"}


@router.get("/stats")
async def get_alert_stats(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Thống kê alerts
    """
    from sqlalchemy import func
    
    # Time range
    since = datetime.now() - timedelta(hours=hours)
    
    # Total alerts
    total = db.query(func.count(Alert.id)).filter(
        Alert.created_at >= since
    ).scalar()
    
    # By severity
    severity_counts = db.query(
        Alert.severity,
        func.count(Alert.id)
    ).filter(
        Alert.created_at >= since
    ).group_by(Alert.severity).all()
    
    severity_stats = {sev: count for sev, count in severity_counts}
    
    # By type
    type_counts = db.query(
        Alert.alert_type,
        func.count(Alert.id)
    ).filter(
        Alert.created_at >= since
    ).group_by(Alert.alert_type).all()
    
    type_stats = {atype: count for atype, count in type_counts}
    
    # Min TTC
    min_ttc = db.query(func.min(Alert.ttc)).filter(
        Alert.created_at >= since,
        Alert.ttc.isnot(None)
    ).scalar()
    
    # Average distance for critical alerts
    avg_critical_distance = db.query(func.avg(Alert.distance)).filter(
        Alert.created_at >= since,
        Alert.severity == 'critical',
        Alert.distance.isnot(None)
    ).scalar()
    
    return {
        "total_alerts": total,
        "severity_breakdown": severity_stats,
        "type_breakdown": type_stats,
        "min_ttc": round(min_ttc, 2) if min_ttc else None,
        "avg_critical_distance": round(avg_critical_distance, 2) if avg_critical_distance else None,
        "time_range_hours": hours
    }


@router.delete("/clear-old")
async def clear_old_alerts(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Xóa alerts cũ (cleanup)
    """
    cutoff = datetime.now() - timedelta(days=days)
    
    # Get old alerts
    old_alerts = db.query(Alert).filter(Alert.created_at < cutoff).all()
    
    deleted_count = 0
    for alert in old_alerts:
        # Delete audio file if exists
        if alert.audio_path and os.path.exists(alert.audio_path):
            try:
                os.remove(alert.audio_path)
            except:
                pass
        
        db.delete(alert)
        deleted_count += 1
    
    db.commit()
    
    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} alerts older than {days} days"
    }
