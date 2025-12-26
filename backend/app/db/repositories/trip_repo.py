"""
Trip Repository
===============
Data access layer for trips.
"""

from typing import Optional, List
from sqlalchemy import select, desc, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from .base import BaseRepository
from ..models.trip import Trip, TripStatus


class TripRepository(BaseRepository[Trip]):
    """Repository for trip operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(Trip, session)
    
    async def create_trip(
        self,
        driver_id: Optional[int],
        vehicle_id: Optional[int],
        start_time: datetime,
        **kwargs
    ) -> Trip:
        """Create a new trip"""
        return await self.create(
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            start_time=start_time,
            status=TripStatus.ONGOING,
            **kwargs
        )
    
    async def complete_trip(
        self,
        trip_id: int,
        end_time: datetime,
        distance_km: float,
        safety_score: float
    ) -> Optional[Trip]:
        """Complete a trip"""
        trip = await self.get_by_id(trip_id)
        if not trip:
            return None
        
        # Calculate duration
        duration_minutes = int((end_time - trip.start_time).total_seconds() / 60)
        
        return await self.update(
            trip_id,
            end_time=end_time,
            distance_km=distance_km,
            duration_minutes=duration_minutes,
            safety_score=safety_score,
            status=TripStatus.COMPLETED
        )
    
    async def get_by_driver(
        self,
        driver_id: int,
        status: Optional[TripStatus] = None,
        limit: int = 50
    ) -> List[Trip]:
        """Get trips by driver"""
        query = select(Trip).where(Trip.driver_id == driver_id)
        
        if status:
            query = query.where(Trip.status == status)
        
        query = query.order_by(desc(Trip.start_time)).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_vehicle(
        self,
        vehicle_id: int,
        limit: int = 50
    ) -> List[Trip]:
        """Get trips by vehicle"""
        result = await self.session.execute(
            select(Trip)
            .where(Trip.vehicle_id == vehicle_id)
            .order_by(desc(Trip.start_time))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_ongoing_trips(self) -> List[Trip]:
        """Get all ongoing trips"""
        result = await self.session.execute(
            select(Trip)
            .where(Trip.status == TripStatus.ONGOING)
            .order_by(Trip.start_time)
        )
        return list(result.scalars().all())
    
    async def get_trips_in_daterange(
        self,
        start_date: datetime,
        end_date: datetime,
        driver_id: Optional[int] = None
    ) -> List[Trip]:
        """Get trips within date range"""
        query = select(Trip).where(
            and_(
                Trip.start_time >= start_date,
                Trip.start_time <= end_date
            )
        )
        
        if driver_id:
            query = query.where(Trip.driver_id == driver_id)
        
        query = query.order_by(desc(Trip.start_time))
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update_safety_metrics(
        self,
        trip_id: int,
        events_count: int,
        critical_events_count: int,
        safety_score: float
    ) -> Optional[Trip]:
        """Update trip safety metrics"""
        return await self.update(
            trip_id,
            events_count=events_count,
            critical_events_count=critical_events_count,
            safety_score=safety_score
        )
