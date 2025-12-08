"""
ADAS Backend - Enhanced Services Layer
Production-ready business logic with proper error handling and validation
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from models import (
    Camera, Driver, Trip, Event, Detection, DriverStatus, 
    Analytics, AIModel, VideoDataset, Label, Alert
)
from schemas import (
    CameraCreate, DriverCreate, TripCreate, EventCreate,
    DetectionCreate, AnalyticsCreate
)
from core.exceptions import (
    NotFoundException, ValidationException, DatabaseException,
    raise_not_found, raise_validation_error
)
from core.logging_config import get_logger, PerformanceLogger

logger = get_logger(__name__)


# ============ Camera Service ============

class CameraService:
    """Enhanced camera management service"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger(f"{__name__}.CameraService")
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[Camera]:
        """Get all cameras with pagination"""
        try:
            with PerformanceLogger("CameraService.get_all", self.logger):
                return self.db.query(Camera).offset(skip).limit(limit).all()
        except Exception as e:
            self.logger.error(f"Failed to get cameras: {e}")
            raise DatabaseException(f"Failed to retrieve cameras: {str(e)}")
    
    def get_by_id(self, camera_id: int) -> Camera:
        """Get camera by ID"""
        camera = self.db.query(Camera).filter(Camera.id == camera_id).first()
        if not camera:
            raise_not_found("Camera", camera_id)
        return camera
    
    def get_active_cameras(self) -> List[Camera]:
        """Get all active cameras"""
        return self.db.query(Camera).filter(Camera.status == "active").all()
    
    def create(self, camera: CameraCreate) -> Camera:
        """Create new camera"""
        try:
            with PerformanceLogger("CameraService.create", self.logger):
                # Validate unique name
                existing = self.db.query(Camera).filter(Camera.name == camera.name).first()
                if existing:
                    raise_validation_error(f"Camera with name '{camera.name}' already exists")
                
                db_camera = Camera(**camera.dict())
                db_camera.created_at = datetime.utcnow()
                db_camera.status = "active"
                
                self.db.add(db_camera)
                self.db.commit()
                self.db.refresh(db_camera)
                
                self.logger.info(f"Camera created: {db_camera.id} - {db_camera.name}")
                return db_camera
        except ValidationException:
            raise
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to create camera: {e}")
            raise DatabaseException(f"Failed to create camera: {str(e)}")
    
    def update(self, camera_id: int, camera: CameraCreate) -> Camera:
        """Update camera"""
        try:
            db_camera = self.get_by_id(camera_id)
            
            for key, value in camera.dict().items():
                setattr(db_camera, key, value)
            
            self.db.commit()
            self.db.refresh(db_camera)
            
            self.logger.info(f"Camera updated: {camera_id}")
            return db_camera
        except NotFoundException:
            raise
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to update camera {camera_id}: {e}")
            raise DatabaseException(f"Failed to update camera: {str(e)}")
    
    def delete(self, camera_id: int) -> bool:
        """Delete camera"""
        try:
            db_camera = self.get_by_id(camera_id)
            self.db.delete(db_camera)
            self.db.commit()
            
            self.logger.info(f"Camera deleted: {camera_id}")
            return True
        except NotFoundException:
            raise
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to delete camera {camera_id}: {e}")
            raise DatabaseException(f"Failed to delete camera: {str(e)}")
    
    def update_status(self, camera_id: int, status: str, metadata: Optional[Dict] = None) -> Camera:
        """Update camera status and metadata"""
        try:
            db_camera = self.get_by_id(camera_id)
            db_camera.status = status
            db_camera.last_active_at = datetime.utcnow()
            
            if metadata:
                # Store additional metadata (e.g., resolution, fps, location)
                for key, value in metadata.items():
                    setattr(db_camera, key, value)
            
            self.db.commit()
            self.db.refresh(db_camera)
            
            self.logger.debug(f"Camera status updated: {camera_id} -> {status}")
            return db_camera
        except NotFoundException:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseException(f"Failed to update camera status: {str(e)}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get camera statistics"""
        try:
            total = self.db.query(func.count(Camera.id)).scalar()
            active = self.db.query(func.count(Camera.id)).filter(Camera.status == "active").scalar()
            inactive = total - active
            
            return {
                "total_cameras": total,
                "active_cameras": active,
                "inactive_cameras": inactive,
                "activity_rate": (active / total * 100) if total > 0 else 0
            }
        except Exception as e:
            self.logger.error(f"Failed to get camera statistics: {e}")
            return {"total_cameras": 0, "active_cameras": 0, "inactive_cameras": 0, "activity_rate": 0}


# ============ Driver Service ============

class DriverService:
    """Enhanced driver management service"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger(f"{__name__}.DriverService")
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[Driver]:
        """Get all drivers"""
        return self.db.query(Driver).offset(skip).limit(limit).all()
    
    def get_by_id(self, driver_id: int) -> Driver:
        """Get driver by ID"""
        driver = self.db.query(Driver).filter(Driver.id == driver_id).first()
        if not driver:
            raise_not_found("Driver", driver_id)
        return driver
    
    def create(self, driver: DriverCreate) -> Driver:
        """Create new driver"""
        try:
            db_driver = Driver(**driver.dict())
            db_driver.created_at = datetime.utcnow()
            db_driver.status = "active"
            db_driver.safety_score = 100.0
            
            self.db.add(db_driver)
            self.db.commit()
            self.db.refresh(db_driver)
            
            self.logger.info(f"Driver created: {db_driver.id} - {db_driver.name}")
            return db_driver
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to create driver: {e}")
            raise DatabaseException(f"Failed to create driver: {str(e)}")
    
    def update_safety_score(self, driver_id: int, score: float, reason: Optional[str] = None) -> Driver:
        """Update driver safety score"""
        try:
            if not 0 <= score <= 100:
                raise_validation_error("Safety score must be between 0 and 100")
            
            db_driver = self.get_by_id(driver_id)
            old_score = db_driver.safety_score
            db_driver.safety_score = score
            db_driver.last_active_at = datetime.utcnow()
            
            self.db.commit()
            self.db.refresh(db_driver)
            
            self.logger.info(
                f"Driver {driver_id} safety score updated: {old_score:.1f} -> {score:.1f}"
                + (f" (Reason: {reason})" if reason else "")
            )
            return db_driver
        except (NotFoundException, ValidationException):
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseException(f"Failed to update safety score: {str(e)}")
    
    def get_driver_statistics(self, driver_id: int, days: int = 30) -> Dict[str, Any]:
        """Get driver statistics for specified period"""
        try:
            driver = self.get_by_id(driver_id)
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Get trips
            trips = self.db.query(Trip).filter(
                and_(Trip.driver_id == driver_id, Trip.start_time >= start_date)
            ).all()
            
            # Get events
            events = self.db.query(Event).filter(
                and_(Event.driver_id == driver_id, Event.timestamp >= start_date)
            ).all()
            
            # Calculate metrics
            total_trips = len(trips)
            total_events = len(events)
            dangerous_events = len([e for e in events if e.severity in ["warning", "danger", "critical"]])
            
            return {
                "driver_id": driver_id,
                "driver_name": driver.name,
                "current_safety_score": driver.safety_score,
                "period_days": days,
                "total_trips": total_trips,
                "total_events": total_events,
                "dangerous_events": dangerous_events,
                "safety_rate": ((total_events - dangerous_events) / total_events * 100) if total_events > 0 else 100
            }
        except NotFoundException:
            raise
        except Exception as e:
            self.logger.error(f"Failed to get driver statistics: {e}")
            raise DatabaseException(f"Failed to get driver statistics: {str(e)}")


# ============ Detection Service ============

class DetectionService:
    """Enhanced detection management service"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger(f"{__name__}.DetectionService")
    
    def save_detection(self, detection_data: Dict[str, Any]) -> Detection:
        """Save detection result"""
        try:
            detection = Detection(
                timestamp=datetime.utcnow(),
                camera_id=detection_data.get("camera_id"),
                model_name=detection_data.get("model_name", "yolo11n"),
                class_name=detection_data["class_name"],
                confidence=detection_data["confidence"],
                bbox_x1=detection_data["bbox"]["x1"],
                bbox_y1=detection_data["bbox"]["y1"],
                bbox_x2=detection_data["bbox"]["x2"],
                bbox_y2=detection_data["bbox"]["y2"],
                distance=detection_data.get("distance"),
                ttc=detection_data.get("ttc"),
                frame_id=detection_data.get("frame_id", 0)
            )
            
            self.db.add(detection)
            self.db.commit()
            self.db.refresh(detection)
            
            return detection
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to save detection: {e}")
            raise DatabaseException(f"Failed to save detection: {str(e)}")
    
    def get_recent_detections(self, limit: int = 50, camera_id: Optional[int] = None) -> List[Detection]:
        """Get recent detections"""
        try:
            query = self.db.query(Detection).order_by(desc(Detection.timestamp))
            
            if camera_id:
                query = query.filter(Detection.camera_id == camera_id)
            
            return query.limit(limit).all()
        except Exception as e:
            self.logger.error(f"Failed to get recent detections: {e}")
            raise DatabaseException(f"Failed to retrieve detections: {str(e)}")
    
    def get_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get detection statistics"""
        try:
            start_time = datetime.utcnow() - timedelta(hours=hours)
            
            detections = self.db.query(Detection).filter(Detection.timestamp >= start_time).all()
            
            total = len(detections)
            if total == 0:
                return {
                    "total_detections": 0,
                    "detections_by_class": {},
                    "avg_confidence": 0.0,
                    "period_hours": hours
                }
            
            # Group by class
            by_class = {}
            total_confidence = 0.0
            
            for det in detections:
                by_class[det.class_name] = by_class.get(det.class_name, 0) + 1
                total_confidence += det.confidence
            
            # Sort by count
            top_classes = sorted(
                [{"class": k, "count": v} for k, v in by_class.items()],
                key=lambda x: x["count"],
                reverse=True
            )[:10]
            
            return {
                "total_detections": total,
                "detections_by_class": by_class,
                "top_classes": top_classes,
                "avg_confidence": total_confidence / total,
                "period_hours": hours,
                "detection_rate_per_hour": total / hours
            }
        except Exception as e:
            self.logger.error(f"Failed to get detection statistics: {e}")
            return {
                "total_detections": 0,
                "detections_by_class": {},
                "top_classes": [],
                "avg_confidence": 0.0,
                "period_hours": hours,
                "detection_rate_per_hour": 0.0
            }


# ============ Alert Service ============

class AlertService:
    """Enhanced alert management service"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger(f"{__name__}.AlertService")
    
    def create_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        detection_id: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> Alert:
        """Create new alert"""
        try:
            alert = Alert(
                timestamp=datetime.utcnow(),
                alert_type=alert_type,
                severity=severity,
                message=message,
                detection_id=detection_id,
                played=False
            )
            
            if metadata:
                alert.object_class = metadata.get("object_class")
                alert.distance = metadata.get("distance")
                alert.ttc = metadata.get("ttc")
                alert.confidence = metadata.get("confidence", 0.0)
            
            self.db.add(alert)
            self.db.commit()
            self.db.refresh(alert)
            
            self.logger.warning(f"Alert created: {alert.alert_type} - {alert.severity} - {alert.message}")
            return alert
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to create alert: {e}")
            raise DatabaseException(f"Failed to create alert: {str(e)}")
    
    def get_latest_alerts(self, limit: int = 20, unplayed_only: bool = False) -> List[Alert]:
        """Get latest alerts"""
        try:
            query = self.db.query(Alert).order_by(desc(Alert.timestamp))
            
            if unplayed_only:
                query = query.filter(Alert.played == False)
            
            return query.limit(limit).all()
        except Exception as e:
            self.logger.error(f"Failed to get alerts: {e}")
            return []
    
    def mark_as_played(self, alert_id: int) -> Alert:
        """Mark alert as played"""
        try:
            alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
            if not alert:
                raise_not_found("Alert", alert_id)
            
            alert.played = True
            self.db.commit()
            self.db.refresh(alert)
            
            return alert
        except NotFoundException:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseException(f"Failed to mark alert as played: {str(e)}")
    
    def get_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get alert statistics"""
        try:
            start_time = datetime.utcnow() - timedelta(hours=hours)
            alerts = self.db.query(Alert).filter(Alert.timestamp >= start_time).all()
            
            total = len(alerts)
            by_type = {}
            by_severity = {}
            critical_count = 0
            
            for alert in alerts:
                by_type[alert.alert_type] = by_type.get(alert.alert_type, 0) + 1
                by_severity[alert.severity] = by_severity.get(alert.severity, 0) + 1
                if alert.severity == "critical":
                    critical_count += 1
            
            return {
                "total_alerts": total,
                "alerts_by_type": by_type,
                "alerts_by_severity": by_severity,
                "critical_count": critical_count,
                "period_hours": hours
            }
        except Exception as e:
            self.logger.error(f"Failed to get alert statistics: {e}")
            return {
                "total_alerts": 0,
                "alerts_by_type": {},
                "alerts_by_severity": {},
                "critical_count": 0,
                "period_hours": hours
            }


# Export all services
__all__ = [
    'CameraService',
    'DriverService',
    'DetectionService',
    'AlertService',
]
