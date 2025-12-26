"""
Safety Event Repository
========================
Data access layer for safety events.
"""

from typing import Optional, List
from sqlalchemy import select, desc, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from .base import BaseRepository
from ..models.safety_event import SafetyEvent, EventType, EventSeverity


class SafetyEventRepository(BaseRepository[SafetyEvent]):
    """Repository for safety event operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(SafetyEvent, session)
    
    async def create_event(
        self,
        trip_id: int,
        video_job_id: int,
        event_type: EventType,
        severity: EventSeverity,
        description: str,
        risk_score: float,
        timestamp: datetime,
        **kwargs
    ) -> SafetyEvent:
        """Create a safety event"""
        return await self.create(
            trip_id=trip_id,
            video_job_id=video_job_id,
            event_type=event_type,
            severity=severity,
            description=description,
            risk_score=risk_score,
            timestamp=timestamp,
            **kwargs
        )
    
    async def get_by_trip(
        self,
        trip_id: int,
        event_type: Optional[EventType] = None,
        severity: Optional[EventSeverity] = None,
        limit: int = 100
    ) -> List[SafetyEvent]:
        """Get events for a trip with optional filters"""
        query = select(SafetyEvent).where(SafetyEvent.trip_id == trip_id)
        
        if event_type:
            query = query.where(SafetyEvent.event_type == event_type)
        if severity:
            query = query.where(SafetyEvent.severity == severity)
        
        query = query.order_by(desc(SafetyEvent.timestamp)).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_video_job(self, video_job_id: int) -> List[SafetyEvent]:
        """Get all events for a video job"""
        result = await self.session.execute(
            select(SafetyEvent)
            .where(SafetyEvent.video_job_id == video_job_id)
            .order_by(SafetyEvent.timestamp)
        )
        return list(result.scalars().all())
    
    async def get_critical_events(
        self,
        trip_id: Optional[int] = None,
        limit: int = 50
    ) -> List[SafetyEvent]:
        """Get critical severity events"""
        query = select(SafetyEvent).where(
            SafetyEvent.severity == EventSeverity.CRITICAL
        )
        
        if trip_id:
            query = query.where(SafetyEvent.trip_id == trip_id)
        
        query = query.order_by(desc(SafetyEvent.timestamp)).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def count_by_trip(
        self,
        trip_id: int,
        severity: Optional[EventSeverity] = None
    ) -> int:
        """Count events for a trip"""
        query = select(func.count()).where(SafetyEvent.trip_id == trip_id)
        
        if severity:
            query = query.where(SafetyEvent.severity == severity)
        
        result = await self.session.execute(query)
        return result.scalar_one()
    
    async def get_events_in_timerange(
        self,
        start_time: datetime,
        end_time: datetime,
        event_type: Optional[EventType] = None
    ) -> List[SafetyEvent]:
        """Get events within time range"""
        query = select(SafetyEvent).where(
            and_(
                SafetyEvent.timestamp >= start_time,
                SafetyEvent.timestamp <= end_time
            )
        )
        
        if event_type:
            query = query.where(SafetyEvent.event_type == event_type)
        
        query = query.order_by(SafetyEvent.timestamp)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
