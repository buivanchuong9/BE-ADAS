"""
VIDEO PROGRESS WEBSOCKET API
=============================
Real-time video processing progress streaming via WebSocket.

Endpoint: ws://domain/ws/video/progress/{job_id}

Usage (Frontend):
```javascript
const ws = new WebSocket(`wss://adas-api.aiotlab.edu.vn/ws/video/progress/${jobId}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // data = {
  //   job_id: "uuid",
  //   status: "processing",
  //   progress_percent: 45,
  //   current_frame: 567,
  //   total_frames: 1260,
  //   fps: 23.5,
  //   eta_seconds: 29,
  //   events_count: 113
  // }
  updateProgressBar(data.progress_percent);
  updateStatus(data.status);
};

ws.onerror = (error) => console.error('WS Error:', error);
ws.onclose = () => console.log('WS closed');
```

Author: ADAS Backend Team
Date: 2026-01-11
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Set
import asyncio
import logging
import json

from ..db.session import get_db
from ..db.repositories.job_queue_repo import JobQueueRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws/video", tags=["WebSocket-Video"])


class VideoProgressManager:
    """
    Manages WebSocket connections for video progress streaming.
    Singleton pattern to share across app.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.active_connections: Dict[str, Set[WebSocket]] = {}
        return cls._instance
    
    async def connect(self, job_id: str, websocket: WebSocket):
        """Accept and register new WebSocket for job_id."""
        await websocket.accept()
        
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        
        self.active_connections[job_id].add(websocket)
        logger.info(f"WebSocket connected for job {job_id}. Total: {len(self.active_connections[job_id])}")
    
    def disconnect(self, job_id: str, websocket: WebSocket):
        """Unregister WebSocket connection."""
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            
            # Clean up empty sets
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
            
            logger.info(f"WebSocket disconnected for job {job_id}")
    
    async def broadcast_progress(self, job_id: str, progress_data: Dict):
        """Broadcast progress to all connected clients for this job."""
        if job_id not in self.active_connections:
            return
        
        dead_connections = set()
        
        for websocket in self.active_connections[job_id]:
            try:
                await websocket.send_json(progress_data)
            except Exception as e:
                logger.warning(f"Failed to send to {websocket}: {e}")
                dead_connections.add(websocket)
        
        # Remove dead connections
        for ws in dead_connections:
            self.disconnect(job_id, ws)
    
    def get_connection_count(self, job_id: str = None) -> int:
        """Get active connection count."""
        if job_id:
            return len(self.active_connections.get(job_id, set()))
        return sum(len(conns) for conns in self.active_connections.values())


# Global manager instance
manager = VideoProgressManager()


@router.websocket("/progress/{job_id}")
async def video_progress_websocket(
    job_id: str,
    websocket: WebSocket
):
    """
    WebSocket endpoint for real-time video processing progress.
    
    Sends progress updates every time job status/progress changes.
    
    Example:
        ws://localhost:52000/ws/video/progress/9ad14689-4039-4798-bd0a-480ad5511044
    """
    await manager.connect(job_id, websocket)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "job_id": job_id,
            "message": "WebSocket connected. Listening for progress updates..."
        })
        
        # Keep connection alive and listen for progress updates
        while True:
            try:
                # Poll job status from DB every 1 second
                from ..db.session import AsyncSessionLocal
                
                async with AsyncSessionLocal() as db:
                    repo = JobQueueRepository(db)
                    job = await repo.get_by_job_id(job_id)
                    
                    if not job:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Job {job_id} not found"
                        })
                        break
                    
                    # Send progress update
                    progress_data = {
                        "type": "progress",
                        "job_id": str(job.job_id),
                        "status": job.status,
                        "progress_percent": job.progress_percent,
                        "result_path": job.result_path,
                        "error_message": job.error_message,
                        "processing_time_seconds": job.processing_time_seconds
                    }
                    
                    await websocket.send_json(progress_data)
                    
                    # If job completed or failed, close connection
                    if job.status in ['completed', 'failed', 'cancelled']:
                        await websocket.send_json({
                            "type": "finished",
                            "status": job.status,
                            "message": f"Job {job_id} {job.status}"
                        })
                        break
                
                # Wait 1 second before next poll
                await asyncio.sleep(1.0)
                
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": asyncio.get_event_loop().time()
                })
            except Exception as e:
                logger.error(f"Error in progress loop: {e}")
                break
    
    except WebSocketDisconnect:
        manager.disconnect(job_id, websocket)
        logger.info(f"Client disconnected from job {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {e}")
        manager.disconnect(job_id, websocket)


@router.get("/stats")
async def get_websocket_stats():
    """Get WebSocket connection statistics."""
    return {
        "total_connections": manager.get_connection_count(),
        "connections_by_job": {
            job_id: manager.get_connection_count(job_id)
            for job_id in manager.active_connections.keys()
        }
    }


if __name__ == "__main__":
    print("Video Progress WebSocket Module")
    print("=" * 60)
    print("\nFrontend Usage:")
    print("""
const jobId = 'your-job-id';
const ws = new WebSocket(`wss://adas-api.aiotlab.edu.vn/ws/video/progress/${jobId}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'progress') {
    progressBar.value = data.progress_percent;
    statusText.innerText = data.status;
  }
  
  if (data.type === 'finished') {
    ws.close();
    showResult(jobId);
  }
};
    """)
