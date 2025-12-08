"""
Analytics API - Real data from database
Provides dashboard statistics and insights
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from datetime import datetime, timedelta
from typing import Dict, Any, List
from database import get_db
from models import Detection, Trip, Event, Driver, Camera, Alert

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/dashboard")
async def get_dashboard_stats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get comprehensive dashboard statistics from real database
    Returns actual counts and metrics - NO FAKE DATA
    """
    try:
        # Total detections from database
        total_detections = db.query(func.count(Detection.id)).scalar() or 0
        
        # Total trips
        total_trips = db.query(func.count(Trip.id)).scalar() or 0
        
        # Total events
        total_events = db.query(func.count(Event.id)).scalar() or 0
        
        # Total alerts
        total_alerts = db.query(func.count(Alert.id)).scalar() or 0
        
        # Total drivers
        total_drivers = db.query(func.count(Driver.id)).scalar() or 0
        
        # Define yesterday for time-based queries
        yesterday = datetime.now() - timedelta(hours=24)
        
        # Active cameras (cameras with status='active' or recent activity)
        active_cameras = db.query(func.count(Camera.id)).filter(
            Camera.status == "active"
        ).scalar() or 0
        
        # If no cameras marked active, count cameras with recent activity
        if active_cameras == 0:
            active_cameras = db.query(func.count(func.distinct(Detection.camera_id))).filter(
                Detection.timestamp >= yesterday
            ).scalar() or 0
        
        # Recent detections (last 24 hours)
        recent_detections = db.query(func.count(Detection.id)).filter(
            Detection.timestamp >= yesterday
        ).scalar() or 0
        
        # Detection breakdown by class (last 24 hours)
        detection_classes = db.query(
            Detection.class_name,
            func.count(Detection.id).label('count'),
            func.avg(Detection.confidence).label('avg_confidence')
        ).filter(
            Detection.timestamp >= yesterday
        ).group_by(
            Detection.class_name
        ).order_by(
            desc('count')
        ).limit(10).all()
        
        classes_breakdown = [
            {
                "class_name": cls.class_name,
                "count": cls.count,
                "avg_confidence": round(float(cls.avg_confidence or 0), 3)
            }
            for cls in detection_classes
        ]
        
        # Average safety score from drivers (not trips)
        avg_safety_score = db.query(func.avg(Driver.safety_score)).scalar()
        avg_safety_score = round(float(avg_safety_score or 100), 1)
        
        # Recent alerts breakdown by severity
        alert_by_severity = db.query(
            Alert.severity,
            func.count(Alert.id).label('count')
        ).filter(
            Alert.created_at >= yesterday
        ).group_by(
            Alert.severity
        ).all()
        
        alerts_breakdown = {
            severity: count for severity, count in alert_by_severity
        }
        
        # Active trips (not ended)
        active_trips = db.query(func.count(Trip.id)).filter(
            Trip.end_time == None
        ).scalar() or 0
        
        return {
            "status": "success",
            "data": {
                # Core metrics
                "totalDetections": total_detections,
                "totalTrips": total_trips,
                "totalEvents": total_events,
                "totalAlerts": total_alerts,
                "totalDrivers": total_drivers,
                "activeCameras": active_cameras,
                "activeTrips": active_trips,
                
                # Calculated metrics
                "avgSafetyScore": avg_safety_score,
                "recent24hDetections": recent_detections,
                
                # Breakdowns
                "detectionsByClass": classes_breakdown,
                "alertsBySeverity": alerts_breakdown,
                
                # Metadata
                "timestamp": datetime.now().isoformat(),
                "dataSource": "real_database",
                "period": "last_24_hours"
            }
        }
        
    except Exception as e:
        print(f"Analytics error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/detections/timeline")
async def get_detections_timeline(
    hours: int = 24,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detection timeline for charts
    Returns hourly detection counts
    """
    try:
        start_time = datetime.now() - timedelta(hours=hours)
        
        # Group by hour
        timeline = db.query(
            func.strftime('%Y-%m-%d %H:00:00', Detection.timestamp).label('hour'),
            func.count(Detection.id).label('count')
        ).filter(
            Detection.timestamp >= start_time
        ).group_by('hour').order_by('hour').all()
        
        return {
            "status": "success",
            "data": {
                "timeline": [
                    {"time": hour, "count": count}
                    for hour, count in timeline
                ],
                "hours": hours,
                "total": sum(count for _, count in timeline)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trips/statistics")
async def get_trip_statistics(
    limit: int = 10,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get trip statistics and recent trips
    """
    try:
        # Recent trips
        recent_trips = db.query(Trip).order_by(
            desc(Trip.start_time)
        ).limit(limit).all()
        
        trips_data = [
            {
                "id": trip.id,
                "driver_id": trip.driver_id,
                "camera_id": trip.camera_id,
                "start_time": trip.start_time.isoformat() if trip.start_time else None,
                "end_time": trip.end_time.isoformat() if trip.end_time else None,
                "distance_km": trip.distance_km,
                "duration_minutes": trip.duration_minutes,
                "safety_score": trip.safety_score,
                "total_alerts": trip.total_alerts,
                "status": "active" if trip.end_time is None else "completed"
            }
            for trip in recent_trips
        ]
        
        # Average metrics
        avg_distance = db.query(func.avg(Trip.distance_km)).scalar() or 0
        avg_duration = db.query(func.avg(Trip.duration_minutes)).scalar() or 0
        avg_safety = db.query(func.avg(Trip.safety_score)).scalar() or 0
        
        return {
            "status": "success",
            "data": {
                "recentTrips": trips_data,
                "averages": {
                    "distance_km": round(float(avg_distance), 2),
                    "duration_minutes": round(float(avg_duration), 1),
                    "safety_score": round(float(avg_safety), 1)
                },
                "total_trips": db.query(func.count(Trip.id)).scalar() or 0
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/health")
async def get_system_health(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get system health metrics
    """
    try:
        # Database connectivity
        db.execute("SELECT 1")
        db_healthy = True
        
        # Check recent activity (last hour)
        last_hour = datetime.now() - timedelta(hours=1)
        recent_activity = db.query(func.count(Detection.id)).filter(
            Detection.timestamp >= last_hour
        ).scalar() or 0
        
        return {
            "status": "success",
            "data": {
                "database": "healthy" if db_healthy else "unhealthy",
                "recent_activity": recent_activity,
                "activity_rate": f"{recent_activity} detections/hour",
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        return {
            "status": "error",
            "data": {
                "database": "unhealthy",
                "error": str(e)
            }
        }
