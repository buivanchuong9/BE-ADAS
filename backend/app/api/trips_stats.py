"""
Trips and Statistics API endpoints - Phase 3 Medium Priority
Handles trip tracking and analytics
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime, timedelta
import random

from ..models import storage, Trip, TripCreateRequest, TripCompleteRequest, TripStatus

router = APIRouter(prefix="/api", tags=["trips", "statistics"])


# ============================================================================
# TRIPS ENDPOINTS
# ============================================================================

@router.post("/trips")
async def create_trip(request: TripCreateRequest):
    """
    Create a new trip
    
    Request body:
    - driver_id: Optional driver identifier
    - vehicle_id: Optional vehicle identifier
    - start_time: ISO timestamp
    - end_time: Optional end time
    - start_location: Optional location string
    - end_location: Optional location string
    - distance_km: Optional distance
    - metadata: Optional metadata
    """
    trip_id = storage.trip_counter
    storage.trip_counter += 1
    
    trip = Trip(
        id=trip_id,
        driver_id=request.driver_id,
        vehicle_id=request.vehicle_id,
        start_time=request.start_time,
        end_time=request.end_time,
        distance_km=request.distance_km or 0.0,
        duration_minutes=0,
        safety_score=random.randint(75, 95),
        events_count=0,
        status=TripStatus.ONGOING if not request.end_time else TripStatus.COMPLETED
    )
    
    storage.trips[trip_id] = trip
    
    return {
        "success": True,
        "trip_id": trip_id
    }


@router.get("/trips/list")
async def get_trips_list(
    limit: int = 50,
    page: int = 1,
    driver_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    """
    Get list of trips
    
    Query Params:
    - limit: Number of trips per page (default: 50)
    - page: Page number (default: 1)
    - driver_id: Filter by driver ID
    - from_date: Start date filter (ISO format)
    - to_date: End date filter (ISO format)
    """
    trips = list(storage.trips.values())
    
    # Apply filters
    if driver_id:
        trips = [t for t in trips if t.driver_id == driver_id]
    
    if from_date:
        trips = [t for t in trips if t.start_time >= from_date]
    
    if to_date:
        trips = [t for t in trips if t.start_time <= to_date]
    
    # Sort by start_time (most recent first)
    trips.sort(key=lambda x: x.start_time, reverse=True)
    
    # Pagination
    total = len(trips)
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_trips = trips[start_idx:end_idx]
    
    return {
        "success": True,
        "trips": [t.model_dump() for t in paginated_trips],
        "total": total
    }


@router.get("/trips/{id}")
async def get_trip_details(id: int):
    """
    Get detailed information about a trip
    
    Path Params:
    - id: Trip ID
    """
    if id not in storage.trips:
        raise HTTPException(status_code=404, detail=f"Trip {id} not found")
    
    trip = storage.trips[id]
    
    # Get events for this trip (dummy - would need trip_id in events metadata)
    trip_events = [e for e in storage.events.values() if e.metadata and e.metadata.get("trip_id") == id]
    
    # Get detections for this trip (dummy)
    trip_detections = []
    
    response = trip.model_dump()
    response["events"] = [e.model_dump() for e in trip_events]
    response["detections"] = trip_detections
    response["avg_speed"] = round(random.uniform(45.0, 75.0), 1)
    response["route"] = None  # Would contain GPS coordinates in real implementation
    
    return {
        "success": True,
        "trip": response
    }


@router.put("/trips/{id}/complete")
async def complete_trip(id: int, request: TripCompleteRequest):
    """
    Mark a trip as completed
    
    Path Params:
    - id: Trip ID
    
    Request body:
    - end_time: ISO timestamp
    - distance_km: Total distance traveled
    """
    if id not in storage.trips:
        raise HTTPException(status_code=404, detail=f"Trip {id} not found")
    
    trip = storage.trips[id]
    trip.end_time = request.end_time
    trip.distance_km = request.distance_km
    trip.status = TripStatus.COMPLETED
    
    # Calculate duration
    try:
        start = datetime.fromisoformat(trip.start_time.replace('Z', '+00:00'))
        end = datetime.fromisoformat(request.end_time.replace('Z', '+00:00'))
        duration = (end - start).total_seconds() / 60
        trip.duration_minutes = int(duration)
    except Exception as e:
        # Fallback to default duration if datetime parsing fails
        trip.duration_minutes = 60  # Default
    
    return {
        "success": True,
        "message": "Trip completed successfully",
        "trip": trip.model_dump()
    }


@router.get("/trips/analytics")
async def get_trips_analytics():
    """
    Get trip analytics for dashboard
    
    Returns:
    - total_trips: Total number of trips
    - total_distance_km: Total distance traveled
    - avg_safety_score: Average safety score
    - by_date: Daily breakdown
    """
    trips = list(storage.trips.values())
    
    total_trips = len(trips)
    total_distance = sum(t.distance_km for t in trips)
    avg_safety_score = sum(t.safety_score for t in trips) / total_trips if total_trips > 0 else 0
    
    # Generate daily breakdown (last 7 days)
    by_date = []
    for i in range(7):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_trips = random.randint(5, 20)
        by_date.append({
            "date": date,
            "trips_count": daily_trips,
            "total_distance": round(random.uniform(100, 500), 1),
            "avg_score": round(random.uniform(80, 95), 1)
        })
    
    by_date.reverse()
    
    return {
        "success": True,
        "total_trips": total_trips,
        "total_distance_km": round(total_distance, 1),
        "avg_safety_score": round(avg_safety_score, 1),
        "by_date": by_date
    }


# ============================================================================
# STATISTICS ENDPOINTS
# ============================================================================

@router.get("/statistics/summary")
async def get_statistics_summary():
    """
    Get overall system statistics summary
    
    Returns comprehensive stats for dashboard
    """
    # Calculate storage (dummy)
    total_storage_gb = sum(v.file_size_mb for v in storage.videos.values()) / 1024
    
    # Last 24 hours stats
    now = datetime.now()
    twenty_four_hours_ago = (now - timedelta(hours=24)).isoformat()
    
    recent_videos = len([v for v in storage.videos.values() if v.uploaded_at >= twenty_four_hours_ago])
    recent_detections = len([d for d in storage.detections if d.timestamp >= twenty_four_hours_ago])
    recent_events = len([e for e in storage.events.values() if e.timestamp >= twenty_four_hours_ago])
    
    return {
        "success": True,
        "total_videos": len(storage.videos),
        "total_detections": len(storage.detections),
        "total_events": len(storage.events),
        "total_trips": len(storage.trips),
        "total_storage_gb": round(total_storage_gb, 2),
        "active_cameras": random.randint(2, 5),
        "last_24h": {
            "videos": recent_videos,
            "detections": recent_detections,
            "events": recent_events
        }
    }


@router.get("/statistics/detections-by-class")
async def get_detections_by_class(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    """
    Get detection statistics by class
    
    Query Params:
    - from_date: Start date filter
    - to_date: End date filter
    """
    detections = storage.detections.copy()
    
    # Apply date filters
    if from_date:
        detections = [d for d in detections if d.timestamp >= from_date]
    
    if to_date:
        detections = [d for d in detections if d.timestamp <= to_date]
    
    # Count by class
    from collections import Counter
    class_counter = Counter(d.class_name for d in detections)
    total = len(detections)
    
    # Calculate stats
    classes = []
    for class_name, count in class_counter.items():
        class_detections = [d for d in detections if d.class_name == class_name]
        avg_confidence = sum(d.confidence for d in class_detections) / len(class_detections)
        
        classes.append({
            "class_name": class_name,
            "count": count,
            "percentage": round(count / total * 100, 1) if total > 0 else 0,
            "avg_confidence": round(avg_confidence, 3)
        })
    
    # Sort by count descending
    classes.sort(key=lambda x: x["count"], reverse=True)
    
    return {
        "success": True,
        "classes": classes
    }


@router.get("/statistics/events-by-type")
async def get_events_by_type():
    """
    Get event statistics by type
    """
    events = list(storage.events.values())
    
    # Count by type
    from collections import Counter
    type_counter = Counter(e.type for e in events)
    total = len(events)
    
    # Calculate stats
    types = []
    for event_type, count in type_counter.items():
        type_events = [e for e in events if e.type == event_type]
        last_occurrence = max(e.timestamp for e in type_events) if type_events else None
        
        types.append({
            "type": event_type,
            "count": count,
            "percentage": round(count / total * 100, 1) if total > 0 else 0,
            "last_occurrence": last_occurrence
        })
    
    # Sort by count descending
    types.sort(key=lambda x: x["count"], reverse=True)
    
    return {
        "success": True,
        "types": types
    }


@router.get("/statistics/performance")
async def get_performance_metrics():
    """
    Get system performance metrics
    """
    # Generate dummy performance metrics
    return {
        "success": True,
        "avg_inference_time_ms": round(random.uniform(15.0, 35.0), 1),
        "avg_fps": round(random.uniform(25.0, 32.0), 1),
        "total_frames_processed": random.randint(100000, 500000),
        "models_loaded": [m.id for m in storage.models_catalog.values() if m.downloaded],
        "gpu_usage": round(random.uniform(40.0, 75.0), 1),
        "cpu_usage": round(random.uniform(30.0, 60.0), 1),
        "memory_usage_mb": round(random.uniform(2048, 4096), 1)
    }
