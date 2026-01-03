"""
VIDEO SSE API - Server-Sent Events for Realtime Partial Results
==================================================================
Streaming endpoint for realtime video processing updates.

Frontend receives partial results within 1-3s after video upload.

Endpoints:
- GET /api/video/stream/{job_id} - SSE stream for job progress

Author: Senior ADAS Engineer
Date: 2026-01-03 (Production Enhancement)
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import asyncio
import json
from typing import AsyncGenerator
from datetime import datetime

from app.db.session import get_db
from app.db.repositories.job_queue_repo import JobQueueRepository
from app.db.repositories.safety_event_repo import SafetyEventRepository
from app.db.models.job_queue import JobStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["video-sse"])


async def event_stream(job_id: str, db: AsyncSession) -> AsyncGenerator[str, None]:
    """
    Server-Sent Events stream for job progress.
    
    Sends updates:
    - Every 2 seconds: Job status, progress, event count
    - On completion: Full results with all events
    - On error: Error details
    
    Args:
        job_id: Job ID to stream
        db: Database session
        
    Yields:
        SSE formatted messages
    """
    repo = JobQueueRepository(db)
    event_repo = SafetyEventRepository(db)
    
    # Check if job exists
    job = await repo.get_by_job_id(job_id)
    if not job:
        yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
        return
    
    logger.info(f"[SSE] Client connected to stream for job {job_id}")
    
    last_status = None
    last_progress = 0
    last_event_count = 0
    retry_count = 0
    max_retries = 180  # 3 minutes timeout
    
    try:
        while retry_count < max_retries:
            # Refresh job state
            await db.refresh(job)
            
            current_status = job.status
            current_progress = job.progress_percent or 0
            
            # Get event count
            events = await event_repo.get_by_job_id(job.id)
            current_event_count = len(events)
            
            # Check if state changed
            state_changed = (
                current_status != last_status or
                current_progress != last_progress or
                current_event_count != last_event_count
            )
            
            if state_changed or retry_count % 5 == 0:  # Send keepalive every 10s
                # Prepare update payload
                update = {
                    "job_id": job_id,
                    "status": current_status.value if isinstance(current_status, JobStatus) else current_status,
                    "progress": current_progress,
                    "event_count": current_event_count,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Send partial events (last 5 new events)
                if current_event_count > last_event_count:
                    new_events = events[last_event_count:][:5]  # Latest 5 events
                    update["partial_events"] = [
                        {
                            "type": e.event_type,
                            "level": e.severity,
                            "time": float(e.timestamp_sec),
                            "frame": e.frame_number,
                            "description": e.description
                        }
                        for e in new_events
                    ]
                
                # Send SSE message
                yield f"event: progress\ndata: {json.dumps(update)}\n\n"
                
                last_status = current_status
                last_progress = current_progress
                last_event_count = current_event_count
            
            # Check if job is complete
            if current_status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                # Send final result
                final_result = {
                    "job_id": job_id,
                    "status": current_status.value if isinstance(current_status, JobStatus) else current_status,
                    "progress": 100 if current_status == JobStatus.COMPLETED else current_progress,
                    "event_count": current_event_count,
                    "processing_time": job.processing_time_seconds,
                    "result_path": job.result_path,
                    "error": job.error_message,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Include all events on completion
                if current_status == JobStatus.COMPLETED:
                    final_result["events"] = [
                        {
                            "type": e.event_type,
                            "level": e.severity,
                            "time": float(e.timestamp_sec),
                            "frame": e.frame_number,
                            "description": e.description,
                            "data": e.meta_data
                        }
                        for e in events
                    ]
                
                yield f"event: complete\ndata: {json.dumps(final_result)}\n\n"
                logger.info(f"[SSE] Job {job_id} completed, closing stream")
                break
            
            # Wait before next poll
            await asyncio.sleep(2)
            retry_count += 1
        
        # Timeout
        if retry_count >= max_retries:
            logger.warning(f"[SSE] Stream timeout for job {job_id}")
            yield f"event: timeout\ndata: {json.dumps({'error': 'Stream timeout after 3 minutes'})}\n\n"
    
    except asyncio.CancelledError:
        logger.info(f"[SSE] Client disconnected from stream {job_id}")
    except Exception as e:
        logger.error(f"[SSE] Stream error for job {job_id}: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"


@router.get("/stream/{job_id}")
async def stream_job_progress(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    **[NEW] Realtime SSE stream for video processing progress.**
    
    Frontend receives partial results within 1-3 seconds of upload.
    
    Event Types:
    - `progress`: Periodic updates (every 2s or on change)
    - `complete`: Final result with all events
    - `error`: Error occurred
    - `timeout`: Stream timeout (3 minutes)
    
    Usage:
    ```javascript
    const eventSource = new EventSource('/api/video/stream/' + jobId);
    
    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        console.log('Progress:', data.progress, '%');
        console.log('Events detected:', data.event_count);
        // Update UI with partial events
        if (data.partial_events) {
            data.partial_events.forEach(event => {
                addEventToUI(event);
            });
        }
    });
    
    eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        console.log('Processing complete!');
        console.log('Total events:', data.events.length);
        eventSource.close();
    });
    
    eventSource.addEventListener('error', (e) => {
        console.error('Stream error:', e.data);
        eventSource.close();
    });
    ```
    
    Args:
        job_id: Job ID from video upload
        db: Database session
        
    Returns:
        SSE stream with realtime updates
    """
    logger.info(f"[SSE] Starting stream for job {job_id}")
    
    return StreamingResponse(
        event_stream(job_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/stream/{job_id}/events")
async def get_partial_events(
    job_id: str,
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    Get partial events for a job (non-streaming alternative).
    
    Use this endpoint if SSE is not supported by client.
    Poll every 2-3 seconds for updates.
    
    Args:
        job_id: Job ID
        limit: Number of events to return (default: 10)
        offset: Offset for pagination (default: 0)
        db: Database session
        
    Returns:
        {
            "job_id": str,
            "status": str,
            "progress": int,
            "event_count": int,
            "events": [...latest events...]
        }
    """
    try:
        repo = JobQueueRepository(db)
        event_repo = SafetyEventRepository(db)
        
        # Get job
        job = await repo.get_by_job_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        
        # Get events
        all_events = await event_repo.get_by_job_id(job.id)
        
        # Paginate
        events = all_events[offset:offset+limit]
        
        return {
            "job_id": job_id,
            "status": job.status.value if isinstance(job.status, JobStatus) else job.status,
            "progress": job.progress_percent or 0,
            "event_count": len(all_events),
            "total_events": len(all_events),
            "events": [
                {
                    "type": e.event_type,
                    "level": e.severity,
                    "time": float(e.timestamp_sec),
                    "frame": e.frame_number,
                    "description": e.description
                }
                for e in events
            ]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get partial events for {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
