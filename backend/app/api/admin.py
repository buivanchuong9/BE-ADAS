from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List, Dict, Any

from app.db.session import get_db
from app.db.models.video import Video
from app.db.models.job_queue import JobQueue
from app.db.models.user import User

# Router with /admin prefix to match frontend calls
router = APIRouter(prefix="/admin", tags=["admin"])


class OverviewStats(BaseModel):
    total_users: int
    total_videos: int
    total_processed: int
    active_jobs: int
    system_status: str


class ChartData(BaseModel):
    labels: List[str]
    datasets: List[Dict[str, Any]]


class ProcessingStats(BaseModel):
    daily_uploads: ChartData
    status_distribution: ChartData


@router.get("/overview", response_model=OverviewStats)
async def get_overview(db: AsyncSession = Depends(get_db)):
    """
    Get system overview statistics for the admin dashboard.
    """
    # Count total users
    user_count = await db.scalar(select(func.count(User.id))) or 0
    
    # Count total videos
    video_count = await db.scalar(select(func.count(Video.id))) or 0
    
    # Count completed jobs
    processed_count = await db.scalar(
        select(func.count(JobQueue.id)).where(JobQueue.status == 'completed')
    ) or 0
    
    # Count active jobs (pending or processing)
    active_count = await db.scalar(
        select(func.count(JobQueue.id)).where(JobQueue.status.in_(['pending', 'processing']))
    ) or 0

    return OverviewStats(
        total_users=user_count,
        total_videos=video_count,
        total_processed=processed_count,
        active_jobs=active_count,
        system_status="operational"
    )


@router.get("/statistics", response_model=ProcessingStats)
async def get_statistics(db: AsyncSession = Depends(get_db)):
    """
    Get detailed statistics for dashboard charts using REAL database data.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    # 1. Status Distribution
    # Query: SELECT status, COUNT(*) FROM job_queue GROUP BY status
    status_query = select(JobQueue.status, func.count(JobQueue.id)).group_by(JobQueue.status)
    status_result = await db.execute(status_query)
    status_counts = dict(status_result.all())
    
    # Prepare Status Chart Data
    # Define standard colors and order
    target_statuses = ["completed", "failed", "processing", "pending"]
    color_map = {
        "completed": "rgb(54, 162, 235)",   # Blue
        "failed": "rgb(255, 99, 132)",      # Red
        "processing": "rgb(75, 192, 192)",  # Teal
        "pending": "rgb(255, 205, 86)"      # Yellow
    }
    
    status_labels = []
    status_data = []
    bg_colors = []
    
    # Add known statuses in order
    for st in target_statuses:
        count = status_counts.get(st, 0)
        status_labels.append(st.capitalize())
        status_data.append(count)
        bg_colors.append(color_map.get(st, "rgb(201, 203, 207)"))
        
    # Add any other statuses found in DB that weren't in target_statuses
    for st, count in status_counts.items():
        if st not in target_statuses and st is not None:
            status_labels.append(str(st).capitalize())
            status_data.append(count)
            bg_colors.append("rgb(201, 203, 207)") # Grey

    # 2. Daily Uploads (Last 7 days)
    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=6)
    
    # Query: Group by Date(created_at)
    # Using func.date() works for PostgreSQL and SQLite
    daily_query = (
        select(func.date(JobQueue.created_at), func.count(JobQueue.id))
        .where(JobQueue.created_at >= seven_days_ago)
        .group_by(func.date(JobQueue.created_at))
    )
    daily_result = await db.execute(daily_query)
    
    # Convert DB result list [(date, count), ...] into dict for easy lookup
    daily_data_db = {d: c for d, c in daily_result.all() if d is not None}
    
    # Fill in all 7 days (even if count is 0)
    daily_labels = []
    daily_counts = []
    
    for i in range(7):
        date_loop = seven_days_ago + timedelta(days=i)
        
        # Check if date_loop exists in result keys (handling date vs datetime string issues)
        # SQLAlchemy func.date usually returns datetime.date object
        count = daily_data_db.get(date_loop, 0)
        
        # Format label: "Mon", "Tue" etc.
        daily_labels.append(date_loop.strftime("%a"))
        daily_counts.append(count)

    return ProcessingStats(
        daily_uploads=ChartData(
            labels=daily_labels,
            datasets=[
                {
                    "label": "Videos Uploaded",
                    "data": daily_counts,
                    "borderColor": "rgb(75, 192, 192)",
                    "tension": 0.3, # Smoother curve
                    "fill": True,
                    "backgroundColor": "rgba(75, 192, 192, 0.2)"
                }
            ]
        ),
        status_distribution=ChartData(
            labels=status_labels,
            datasets=[
                {
                    "label": "Job Status",
                    "data": status_data,
                    "backgroundColor": bg_colors,
                    "hoverOffset": 4
                }
            ]
        )
    )


# --- NEW DASHBOARD ENDPOINTS ---


# --- NEW DASHBOARD ENDPOINTS (V2 - Matched to Frontend) ---

@router.get("/dashboard/cards")
async def get_dashboard_cards(db: AsyncSession = Depends(get_db)):
    """
    Get data for the upper 4 info cards.
    """
    from datetime import date
    from app.db.models.safety_event import SafetyEvent
    
    # Active Jobs as proxy for Active Cameras
    active_jobs_count = await db.scalar(
        select(func.count(JobQueue.id)).where(JobQueue.status.in_(['processing', 'pending']))
    ) or 0
    
    system_status = "Trực tuyến" if active_jobs_count > 0 else "Ngoại tuyến"
    
    # Total Detections
    total_detections = await db.scalar(select(func.count(SafetyEvent.id))) or 0
    
    # Today's Alerts
    today = date.today()
    today_alerts = await db.scalar(
        select(func.count(SafetyEvent.id)).where(func.date(SafetyEvent.created_at) == today)
    ) or 0
    
    # Active Cameras
    active_cameras = active_jobs_count
    
    return {
        "system_status": system_status,
        "active_cameras": active_cameras,
        "total_detections": total_detections,
        "today_alerts": today_alerts
    }


@router.get("/dashboard/charts/detection-trend")
async def get_realtime_trend(db: AsyncSession = Depends(get_db)):
    """
    Chart 1: Real-Time Detection Trend
    Line chart: Detection count over time (last 30 mins, 5-min intervals).
    Series: 'Xe cộ' (Vehicles), 'Người đi bộ' (Pedestrians).
    """
    from datetime import datetime, timedelta
    from app.db.models.safety_event import SafetyEvent
    
    now = datetime.now()
    thirty_mins_ago = now - timedelta(minutes=30)
    
    # Buckets: 10:00, 10:05, 10:10...
    labels = []
    vehicle_data = []
    person_data = []
    
    # Generate 6 buckets of 5 minutes
    for i in range(7):
        time_slot = thirty_mins_ago + timedelta(minutes=i*5)
        label = time_slot.strftime("%H:%M")
        labels.append(label)
        
        # Determine time range for this bucket
        start_time = time_slot
        end_time = time_slot + timedelta(minutes=5)
        
        # Query count for this range
        # Note: In a real intense system, we'd use date_trunc in SQL. 
        # Here we loop for simplicity and readability.
        v_count = await db.scalar(
            select(func.count(SafetyEvent.id))
            .where(SafetyEvent.created_at >= start_time)
            .where(SafetyEvent.created_at < end_time)
            .where(SafetyEvent.event_type.in_(['vehicle_detection', 'process_vehicle']))
        ) or 0
        
        p_count = await db.scalar(
            select(func.count(SafetyEvent.id))
            .where(SafetyEvent.created_at >= start_time)
            .where(SafetyEvent.created_at < end_time)
            .where(SafetyEvent.event_type.in_(['person_detection', 'process_person', 'pedestrian_detected']))
        ) or 0
        
        vehicle_data.append(v_count)
        person_data.append(p_count)
        
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Xe cộ",
                "data": vehicle_data,
                "borderColor": "#36A2EB",
                "backgroundColor": "rgba(54, 162, 235, 0.1)",
                "fill": True,
                "tension": 0.4
            },
            {
                "label": "Người đi bộ",
                "data": person_data,
                "borderColor": "#4BC0C0",
                "backgroundColor": "rgba(75, 192, 192, 0.1)",
                "fill": True,
                "tension": 0.4
            }
        ]
    }


@router.get("/dashboard/charts/detection-accuracy")
async def get_accuracy_history(db: AsyncSession = Depends(get_db)):
    """
    Chart 2: Detection Accuracy Over Time (Last 7 Days)
    Line chart: Uses Average Drowsiness Confidence as a proxy for Detection Accuracy.
    """
    from datetime import datetime, timedelta
    from app.db.models.driver_state import DriverState
    
    today = datetime.now().date()
    labels = []
    accuracy_data = []
    
    # Last 7 days
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        # Label: "Mon", "Tue"
        labels.append(day.strftime("%a"))
        
        # Real Logic: Calculate average confidence of driver state detections for this day
        # Note: Using CAST to Date works in PostgreSQL
        query = select(func.avg(DriverState.drowsy_confidence)).where(
            func.date(DriverState.timestamp) == day
        )
        avg_conf = await db.scalar(query)
        
        if avg_conf is not None:
            # Scale 0-1 to 0-100%
            percentage = round(avg_conf * 100, 1)
        else:
             # If no data, use a baseline or 0. 
             # For a dashboard to look good if empty, we might return 0 or carry over.
             # But let's return 0 to be honest about "Real Data".
             percentage = 0.0
        
        accuracy_data.append(percentage)

    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Độ chính xác (%)",
                "data": accuracy_data,
                "borderColor": "#2ECC71", # Green
                "pointBackgroundColor": "#2ECC71",
                "pointBorderColor": "#fff",
                "tension": 0.4
            }
        ]
    }


@router.get("/dashboard/charts/detection-distribution")
async def get_distribution_chart(db: AsyncSession = Depends(get_db)):
    """
    Chart 3: Detection Distribution (Pie Chart)
    """
    from app.db.models.safety_event import SafetyEvent
    
    # Define mapping to standard categories
    # Map event_types to: "Xe" (Vehicles), "Người" (People), "Chu kỳ" (Cycles - if any), "Khác" (Other)
    
    # Query all counts by type
    query = select(SafetyEvent.event_type, func.count(SafetyEvent.id)).group_by(SafetyEvent.event_type)
    result = await db.execute(query)
    raw_data = result.all()
    
    # Aggregate
    distribution = {
        "Xe": 0,
        "Người": 0,
        "Chu kỳ": 0,
        "Khác": 0
    }
    
    for event_type, count in raw_data:
        etype = str(event_type).lower()
        if "vehicle" in etype or "car" in etype or "truck" in etype:
            distribution["Xe"] += count
        elif "person" in etype or "pedestrian" in etype:
            distribution["Người"] += count
        elif "cycle" in etype or "bike" in etype:
            distribution["Chu kỳ"] += count
        else:
            distribution["Khác"] += count
            
    # Format for chart
    return {
        "labels": list(distribution.keys()),
        "datasets": [{
            "data": list(distribution.values()),
            "backgroundColor": [
                "#36A2EB", # Blue - Xe
                "#9966FF", # Purple - Người
                "#FF9F40", # Orange - Chu kỳ (Mock color from image is Pink/Purple mixed)
                "#4BC0C0"  # Teal - Khác
            ]
        }]
    }


@router.get("/dashboard/charts/system-performance")
async def get_system_performance_chart(db: AsyncSession = Depends(get_db)):
    """
    Chart 4: System Performance (Processing FPS)
    """
    from app.db.models.video_analytics import VideoAnalytics
    
    # Get last 7 entries (to match '0 1 2 3 4 5 6' in image)
    query = select(VideoAnalytics).order_by(VideoAnalytics.created_at.desc()).limit(7)
    result = await db.execute(query)
    analytics_nodes = result.scalars().all()
    
    analytics_nodes.reverse()
    
    # Labels: Just generic index or time? Image shows 0-6. Let's use simple index or time.
    # User image has '0 1 2 3 4 5 6'.
    labels = [str(i) for i in range(len(analytics_nodes))]
    if not labels:
        labels = ["0", "1", "2", "3", "4", "5", "6"]
        
    data = [a.processing_fps or 0 for a in analytics_nodes]
    # Pad with 0 if no data
    while len(data) < 7:
        data.insert(0, 0)
    
    return {
        "labels": labels,
        "datasets": [{
            "label": "Hiệu suất",
            "data": data,
            "borderColor": "#36A2EB",
            "backgroundColor": "rgba(54, 162, 235, 0.2)",
            "tension": 0.4,
            "fill": True
        }]
    }


