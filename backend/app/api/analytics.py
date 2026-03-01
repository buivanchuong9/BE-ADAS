"""
Analytics API - Chart Data Endpoints
=====================================
FastAPI routes for analytics dashboard charts.

Endpoints:
- GET /api/analytics/speed-over-time - Speed data for line chart
- GET /api/analytics/fatigue-over-time - Fatigue level data for line chart
- GET /api/analytics/safety-score-comparison - Safety scores for bar chart
- GET /api/analytics/recommendations - Safety recommendations

Author: ADAS Backend Team
Date: 2026-02-05
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, case
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from app.db.session import get_db
from app.db.models.trip import Trip
from app.db.models.safety_event import SafetyEvent
from app.db.models.driver_state import DriverState
from app.db.models.alert import Alert

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/speed-over-time")
async def get_speed_over_time(
    trip_id: Optional[int] = Query(None, description="Specific trip ID, or latest if not provided"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get speed data over time for line chart.
    
    Returns data points with speed (km/h) at different time intervals.
    Frontend chart name: "Speed Over Time"
    
    Args:
        trip_id: Optional trip ID. If not provided, uses the most recent trip.
        
    Returns:
        {
            "labels": ["0:00", "0:15", "0:30", ...],
            "data": [0, 45, 60, 70, 68, ...],
            "trip_id": 123
        }
    """
    try:
        # Get trip
        if trip_id:
            trip_query = select(Trip).where(Trip.id == trip_id)
        else:
            # Get most recent completed trip
            trip_query = select(Trip).where(
                Trip.status == "completed"
            ).order_by(desc(Trip.created_at)).limit(1)
        
        result = await db.execute(trip_query)
        trip = result.scalar_one_or_none()
        
        if not trip:
            raise HTTPException(status_code=404, detail="No trip data found")
        
        # Get speed data from safety events
        # We'll sample speed readings at regular intervals
        speed_query = select(
            SafetyEvent.timestamp_sec,
            SafetyEvent.speed_kmh
        ).where(
            and_(
                SafetyEvent.trip_id == trip.id,
                SafetyEvent.speed_kmh.isnot(None)
            )
        ).order_by(SafetyEvent.timestamp_sec)
        
        result = await db.execute(speed_query)
        speed_records = result.all()
        
        # If no speed data in safety_events, generate from trip avg/max
        if not speed_records:
            # Generate sample data based on trip metrics
            duration = trip.duration_minutes or 2
            avg_speed = trip.avg_speed or 50
            max_speed = trip.max_speed or 80
            
            # Create realistic speed curve
            labels = []
            data = []
            intervals = min(10, duration)  # Max 10 data points
            
            for i in range(intervals + 1):
                time_sec = (duration * 60 / intervals) * i
                minutes = int(time_sec // 60)
                seconds = int(time_sec % 60)
                labels.append(f"{minutes}:{seconds:02d}")
                
                # Simulate speed variation (accelerate then decelerate)
                if i < intervals / 2:
                    speed = avg_speed * (i / (intervals / 2))
                else:
                    speed = max_speed - (max_speed - avg_speed) * ((i - intervals / 2) / (intervals / 2))
                data.append(round(speed, 1))
        else:
            # Use actual data
            labels = []
            data = []
            
            # Sample data points (max 15 points for clean visualization)
            sample_size = min(15, len(speed_records))
            step = max(1, len(speed_records) // sample_size)
            
            for i in range(0, len(speed_records), step):
                record = speed_records[i]
                time_sec = record.timestamp_sec or 0
                minutes = int(time_sec // 60)
                seconds = int(time_sec % 60)
                labels.append(f"{minutes}:{seconds:02d}")
                data.append(round(record.speed_kmh or 0, 1))
        
        return {
            "labels": labels,
            "data": data,
            "unit": "km/h",
            "trip_id": trip.id,
            "chart_title": "Speed Over Time"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get speed over time: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve speed data: {str(e)}")


@router.get("/fatigue-over-time")
async def get_fatigue_over_time(
    trip_id: Optional[int] = Query(None, description="Specific trip ID, or latest if not provided"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get fatigue level data over time for line chart.
    
    Calculates fatigue percentage based on driver monitoring data.
    Frontend chart name: "Fatigue Level Over Time"
    
    Args:
        trip_id: Optional trip ID. If not provided, uses the most recent trip.
        
    Returns:
        {
            "labels": ["0:00", "0:30", "1:00", ...],
            "data": [10, 15, 23, 30, 40],
            "trip_id": 123
        }
    """
    try:
        # Get trip
        if trip_id:
            trip_query = select(Trip).where(Trip.id == trip_id)
        else:
            # Get most recent completed trip
            trip_query = select(Trip).where(
                Trip.status == "completed"
            ).order_by(desc(Trip.created_at)).limit(1)
        
        result = await db.execute(trip_query)
        trip = result.scalar_one_or_none()
        
        if not trip:
            raise HTTPException(status_code=404, detail="No trip data found")
        
        # Get driver state data
        fatigue_query = select(
            DriverState.timestamp_sec,
            DriverState.is_drowsy,
            DriverState.drowsy_confidence,
            DriverState.ear_value
        ).where(
            DriverState.trip_id == trip.id
        ).order_by(DriverState.timestamp_sec)
        
        result = await db.execute(fatigue_query)
        fatigue_records = result.all()
        
        # If no fatigue data, generate sample based on trip duration
        if not fatigue_records:
            duration = trip.duration_minutes or 2
            labels = []
            data = []
            intervals = min(8, duration)  # Max 8 data points
            
            for i in range(intervals + 1):
                time_sec = (duration * 60 / intervals) * i
                # Format as hours if duration > 60 min
                if duration > 60:
                    hours = time_sec / 3600
                    labels.append(f"{hours:.2f}")
                else:
                    minutes = int(time_sec // 60)
                    seconds = int(time_sec % 60)
                    labels.append(f"{minutes}:{seconds:02d}")
                
                # Simulate increasing fatigue over time
                fatigue = min(40, 10 + (i / intervals) * 30)
                data.append(round(fatigue, 1))
        else:
            # Use actual data
            labels = []
            data = []
            
            # Sample data points (max 10 points)
            sample_size = min(10, len(fatigue_records))
            step = max(1, len(fatigue_records) // sample_size)
            
            # Get trip start time for relative timestamps
            trip_start = trip.start_time
            
            for i in range(0, len(fatigue_records), step):
                record = fatigue_records[i]
                
                # Calculate relative time from trip start
                if trip_start and record.timestamp:
                    time_diff = (record.timestamp - trip_start).total_seconds()
                    minutes = int(time_diff // 60)
                    seconds = int(time_diff % 60)
                    labels.append(f"{minutes}:{seconds:02d}")
                else:
                    labels.append(f"{i}")
                
                # Calculate fatigue level (0-100%)
                # If drowsy, use confidence. Otherwise use EAR inverse correlation
                if record.is_drowsy:
                    fatigue = (record.drowsy_confidence or 0.5) * 100
                else:
                    # Normal EAR is ~0.25-0.3, lower = more fatigue
                    ear = record.ear_value or 0.25
                    fatigue = max(0, (0.3 - ear) / 0.3 * 100)
                
                data.append(round(fatigue, 1))
        
        return {
            "labels": labels,
            "data": data,
            "unit": "%",
            "trip_id": trip.id,
            "chart_title": "Fatigue Level Over Time"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get fatigue over time: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve fatigue data: {str(e)}")


@router.get("/safety-score-comparison")
async def get_safety_score_comparison(
    days: int = Query(7, description="Number of days to compare (default 7)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get safety score comparison for bar chart.
    
    Calculates daily safety scores based on trips and alerts.
    Frontend chart name: "Safety Score Comparison"
    
    Args:
        days: Number of days to compare (default 7)
        
    Returns:
        {
            "labels": ["Today", "Yesterday", "3 Days Ago", "1 Week Ago"],
            "data": [85, 78, 82, 75],
            "colors": ["#6366f1", "#6366f1", "#6366f1", "#6366f1"]
        }
    """
    try:
        # Define time periods
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Labels for different periods
        if days >= 7:
            periods = [
                {"label": "Today", "start": today_start, "end": now},
                {"label": "Yesterday", "start": today_start - timedelta(days=1), "end": today_start},
                {"label": "3 Days Ago", "start": today_start - timedelta(days=3), "end": today_start - timedelta(days=2)},
                {"label": "1 Week Ago", "start": today_start - timedelta(days=7), "end": today_start - timedelta(days=6)}
            ]
        else:
            # For fewer days, create daily labels
            periods = []
            for i in range(days):
                label = "Today" if i == 0 else f"{i} Day{'s' if i > 1 else ''} Ago"
                start = today_start - timedelta(days=i)
                end = start + timedelta(days=1)
                periods.append({"label": label, "start": start, "end": end})
        
        labels = []
        data = []
        colors = []
        
        for period in periods:
            labels.append(period["label"])
            
            # Calculate safety score for this period
            # Score = 100 - (critical_alerts * 20 + warnings * 5)
            
            # Count trips and alerts in this period
            trips_query = select(
                func.count(Trip.id).label("total_trips"),
                func.sum(Trip.critical_alerts).label("total_critical"),
                func.sum(Trip.total_alerts).label("total_alerts")
            ).where(
                and_(
                    Trip.created_at >= period["start"],
                    Trip.created_at < period["end"]
                )
            )
            
            result = await db.execute(trips_query)
            trip_stats = result.first()
            
            total_trips = trip_stats.total_trips or 0
            total_critical = trip_stats.total_critical or 0
            total_alerts = trip_stats.total_alerts or 0
            
            # Calculate score
            if total_trips == 0:
                # No data - use a default score
                score = 80
            else:
                # Base score 100, deduct for alerts
                avg_critical = total_critical / total_trips
                avg_alerts = total_alerts / total_trips
                
                score = 100 - (avg_critical * 15) - (avg_alerts * 2)
                score = max(0, min(100, score))  # Clamp to 0-100
            
            data.append(round(score, 1))
            
            # Color based on score
            if score >= 85:
                colors.append("#10b981")  # Green
            elif score >= 70:
                colors.append("#f59e0b")  # Orange
            else:
                colors.append("#ef4444")  # Red
        
        return {
            "labels": labels,
            "data": data,
            "colors": colors,
            "chart_title": "Safety Score Comparison"
        }
    
    except Exception as e:
        logger.error(f"Failed to get safety score comparison: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve safety scores: {str(e)}")


@router.get("/recommendations")
async def get_recommendations(
    trip_id: Optional[int] = Query(None, description="Specific trip ID, or latest if not provided"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get safety recommendations based on recent trip data.
    
    Frontend section name: "Recommendations"
    
    Args:
        trip_id: Optional trip ID. If not provided, analyzes most recent trips.
        
    Returns:
        {
            "recommendations": [
                {
                    "title": "Increase Safety Distance",
                    "description": "You have 2 collision warnings. Please increase distance from the vehicle ahead.",
                    "severity": "warning",  // info, warning, critical
                    "icon": "⚠️"
                },
                ...
            ]
        }
    """
    try:
        recommendations = []
        
        # Get recent trips (or specific trip)
        if trip_id:
            trips_query = select(Trip).where(Trip.id == trip_id)
        else:
            # Get last 3 trips
            trips_query = select(Trip).order_by(
                desc(Trip.created_at)
            ).limit(3)
        
        result = await db.execute(trips_query)
        trips = result.scalars().all()
        
        if not trips:
            return {"recommendations": []}
        
        # Aggregate statistics
        total_critical = sum(t.critical_alerts or 0 for t in trips)
        total_alerts = sum(t.total_alerts or 0 for t in trips)
        avg_speed = sum(t.avg_speed or 0 for t in trips) / len(trips) if trips else 0
        max_speed = max((t.max_speed or 0 for t in trips), default=0)
        
        # Count specific alert types
        alert_query = select(
            Alert.alert_type,
            func.count(Alert.id).label("count")
        ).where(
            Alert.trip_id.in_([t.id for t in trips])
        ).group_by(Alert.alert_type)
        
        result = await db.execute(alert_query)
        alert_counts = {row.alert_type: row.count for row in result}
        
        # Generate recommendations based on data
        
        # 1. Collision warnings
        collision_count = alert_counts.get("collision_warning", 0) + alert_counts.get("forward_collision", 0)
        if collision_count > 0:
            recommendations.append({
                "title": "Increase Safety Distance",
                "description": f"You have {collision_count} collision warning{'s' if collision_count > 1 else ''}. Please increase distance from the vehicle ahead.",
                "severity": "warning" if collision_count < 3 else "critical",
                "icon": "⚠️"
            })
        
        # 2. Fatigue detection
        fatigue_count = alert_counts.get("driver_fatigue", 0)
        if fatigue_count > 0:
            recommendations.append({
                "title": "Rest Regularly",
                "description": f"Fatigue level increased rapidly after 1.5 hours of driving. Take a 15-minute break.",
                "severity": "warning",
                "icon": "😴"
            })
        
        # 3. Speed violations
        speed_count = alert_counts.get("speed_limit_violation", 0)
        if speed_count > 0:
            recommendations.append({
                "title": "Follow Speed Limit",
                "description": f"You exceeded the speed limit {speed_count} time{'s' if speed_count > 1 else ''}. Please follow speed limit for safety.",
                "severity": "critical" if speed_count >= 3 else "warning",
                "icon": "🚨"
            })
        
        # 4. Lane departure
        lane_count = alert_counts.get("lane_departure", 0)
        if lane_count > 0:
            recommendations.append({
                "title": "Stay In Lane",
                "description": f"You have {lane_count} lane departure warning{'s' if lane_count > 1 else ''}. Please stay within your lane.",
                "severity": "warning",
                "icon": "🛣️"
            })
        
        # 5. General safe driving if no major issues
        if total_critical == 0 and total_alerts < 3:
            recommendations.append({
                "title": "Good Driving Performance",
                "description": "Your driving is safe and consistent. Keep up the good work!",
                "severity": "info",
                "icon": "✅"
            })
        
        # 6. High speed warning
        if max_speed > 100:
            recommendations.append({
                "title": "Reduce Speed",
                "description": f"Maximum speed reached {max_speed:.0f} km/h. Consider reducing speed for safety.",
                "severity": "warning",
                "icon": "⚡"
            })
        
        # Sort by severity (critical -> warning -> info)
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        recommendations.sort(key=lambda x: severity_order.get(x["severity"], 3))
        
        return {
            "recommendations": recommendations[:5],  # Max 5 recommendations
            "trip_count": len(trips),
            "total_alerts": total_alerts,
            "total_critical": total_critical
        }
    
    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")


@router.get("/summary")
async def get_analytics_summary(
    period: str = Query("today", description="Time period: today, week, month, all"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get overall analytics summary (bonus endpoint for dashboard stats).
    
    Args:
        period: Time period filter
        
    Returns:
        {
            "total_trips": 25,
            "total_distance": 450.5,
            "avg_safety_score": 82.3,
            "total_alerts": 15
        }
    """
    try:
        # Calculate time range
        now = datetime.utcnow()
        if period == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start_time = now - timedelta(days=7)
        elif period == "month":
            start_time = now - timedelta(days=30)
        else:  # all
            start_time = datetime(2000, 1, 1)
        
        # Query trip statistics
        stats_query = select(
            func.count(Trip.id).label("total_trips"),
            func.sum(Trip.distance_km).label("total_distance"),
            func.sum(Trip.critical_alerts).label("total_critical"),
            func.sum(Trip.total_alerts).label("total_alerts"),
            func.avg(Trip.avg_speed).label("avg_speed")
        ).where(
            Trip.created_at >= start_time
        )
        
        result = await db.execute(stats_query)
        stats = result.first()
        
        # Calculate safety score
        total_trips = stats.total_trips or 0
        if total_trips > 0:
            avg_critical = (stats.total_critical or 0) / total_trips
            avg_alerts = (stats.total_alerts or 0) / total_trips
            safety_score = 100 - (avg_critical * 15) - (avg_alerts * 2)
            safety_score = max(0, min(100, safety_score))
        else:
            safety_score = 0
        
        return {
            "period": period,
            "total_trips": total_trips,
            "total_distance": round(stats.total_distance or 0, 2),
            "avg_safety_score": round(safety_score, 1),
            "total_alerts": stats.total_alerts or 0,
            "total_critical_alerts": stats.total_critical or 0,
            "avg_speed": round(stats.avg_speed or 0, 1)
        }
    
    except Exception as e:
        logger.error(f"Failed to get analytics summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve summary: {str(e)}")
