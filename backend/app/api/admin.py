"""
Admin Dashboard API
===================
Handles administrative endpoints for dashboard overview and statistics.

Endpoints:
- GET /admin/overview: System overview stats
- GET /admin/statistics: Detailed charts data
"""
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
