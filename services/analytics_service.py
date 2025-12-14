# Analytics Service - Real data aggregation from database
# NO mock data - all metrics from actual processing

import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from models import VideoDataset, ADASEvent, Detection

logger = logging.getLogger("adas-backend")


class AnalyticsService:
    """
    Aggregates analytics from database for admin dashboard.
    All data is REAL - computed from actual video processing.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_overview(self) -> Dict[str, Any]:
        """Get overview statistics"""
        
        # Count total videos
        total_videos = self.db.query(VideoDataset).count()
        
        # Count total events
        total_events = self.db.query(ADASEvent).count()
        
        # Sum total processing time
        total_time = self.db.query(
            func.sum(VideoDataset.duration)
        ).scalar() or 0.0
        
        # Calculate average events per video
        avg_events = total_events / total_videos if total_videos > 0 else 0.0
        
        # Events by severity
        events_by_severity = {}
        severity_counts = self.db.query(
            ADASEvent.severity,
            func.count(ADASEvent.id)
        ).group_by(ADASEvent.severity).all()
        
        for severity, count in severity_counts:
            events_by_severity[severity] = count
        
        # Events by type
        events_by_type = {}
        type_counts = self.db.query(
            ADASEvent.event_type,
            func.count(ADASEvent.id)
        ).group_by(ADASEvent.event_type).all()
        
        for event_type, count in type_counts:
            events_by_type[event_type] = count
        
        return {
            "total_videos": total_videos,
            "total_events": total_events,
            "total_processing_time_s": round(total_time, 2),
            "avg_events_per_video": round(avg_events, 2),
            "events_by_severity": events_by_severity,
            "events_by_type": events_by_type
        }
    
    def get_video_timeline(self, video_id: str) -> List[Dict[str, Any]]:
        """Get timeline of events for a specific video"""
        
        # Find video
        video = self.db.query(VideoDataset).filter(
            VideoDataset.filename == video_id
        ).first()
        
        if not video:
            return []
        
        # Get all events (would need to link events to videos in schema)
        # For now, return empty list
        return []
    
    def get_statistics(self, period: str = "day") -> Dict[str, Any]:
        """Get aggregated statistics for a time period"""
        
        # Calculate time range
        now = datetime.now()
        if period == "day":
            start_time = now - timedelta(days=1)
        elif period == "week":
            start_time = now - timedelta(weeks=1)
        elif period == "month":
            start_time = now - timedelta(days=30)
        else:
            start_time = now - timedelta(days=1)
        
        # Count events in period
        events_count = self.db.query(ADASEvent).filter(
            ADASEvent.timestamp >= start_time
        ).count()
        
        # Count videos in period
        videos_count = self.db.query(VideoDataset).filter(
            VideoDataset.created_at >= start_time
        ).count()
        
        return {
            "period": period,
            "events_count": events_count,
            "videos_count": videos_count,
            "start_time": start_time.isoformat(),
            "end_time": now.isoformat()
        }
    
    def get_chart_data(self, chart_type: str) -> Dict[str, Any]:
        """Get chart data for visualization"""
        
        if chart_type == "events_by_type":
            # Bar chart of events by type
            type_counts = self.db.query(
                ADASEvent.event_type,
                func.count(ADASEvent.id)
            ).group_by(ADASEvent.event_type).all()
            
            labels = [t[0] for t in type_counts]
            data = [t[1] for t in type_counts]
            
            return {
                "chart_type": "bar",
                "title": "Events by Type",
                "labels": labels,
                "datasets": [
                    {
                        "label": "Event Count",
                        "data": data,
                        "backgroundColor": "rgba(54, 162, 235, 0.8)"
                    }
                ]
            }
        
        elif chart_type == "events_by_severity":
            # Pie chart of events by severity
            severity_counts = self.db.query(
                ADASEvent.severity,
                func.count(ADASEvent.id)
            ).group_by(ADASEvent.severity).all()
            
            labels = [s[0] for s in severity_counts]
            data = [s[1] for s in severity_counts]
            
            return {
                "chart_type": "pie",
                "title": "Events by Severity",
                "labels": labels,
                "datasets": [
                    {
                        "label": "Event Count",
                        "data": data,
                        "backgroundColor": [
                            "rgba(255, 99, 132, 0.8)",
                            "rgba(255, 206, 86, 0.8)",
                            "rgba(75, 192, 192, 0.8)"
                        ]
                    }
                ]
            }
        
        else:
            return {
                "chart_type": "unknown",
                "title": "No Data",
                "labels": [],
                "datasets": []
            }
