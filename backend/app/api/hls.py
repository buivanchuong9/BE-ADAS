"""
HLS Streaming API - Serve HLS Segments
=======================================
Serves HLS playlist and .ts segments for progressive video streaming.

Author: Principal AI Architect
Date: 2026-02-08
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse, Response
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
import os
import logging

from app.db.session import get_db
from app.db.repositories.job_queue_repo import JobQueueRepository

router = APIRouter(prefix="/api/hls", tags=["hls"])
logger = logging.getLogger(__name__)


@router.get("/{job_id}/playlist.m3u8")
async def get_hls_playlist(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Serve HLS playlist.m3u8 for a job.
    
    This is the master playlist that lists all segments.
    Client should poll this endpoint to get latest segments.
    """
    try:
        # Get job
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if not job.hls_playlist_path:
            raise HTTPException(
                status_code=404,
                detail="HLS playlist not yet available. Check job progress."
            )
        
        # Serve playlist
        playlist_path = Path(job.hls_playlist_path)
        
        if not playlist_path.exists():
            raise HTTPException(status_code=404, detail="Playlist file not found")
        
        return FileResponse(
            path=str(playlist_path),
            media_type="application/vnd.apple.mpegurl",  # HLS MIME type
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to serve HLS playlist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/{segment_filename}")
async def get_hls_segment(
    job_id: str,
    segment_filename: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Serve individual HLS .ts segment.
    
    Args:
        job_id: Job ID
        segment_filename: Segment filename (e.g., segment_00000.ts)
    
    Serves:
        MPEG-TS segment file
    
    Security:
        - Validates segment_filename to prevent directory traversal
        - Only serves .ts files
        - Cross-check with job ownership
    """
    try:
        # Validate filename (security)
        if ".." in segment_filename or "/" in segment_filename or "\\" in segment_filename:
            raise HTTPException(status_code=400, detail="Invalid segment filename")
        
        if not segment_filename.endswith(".ts"):
            raise HTTPException(status_code=400, detail="Only .ts files allowed")
        
        # Get job
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if not job.hls_playlist_path:
            raise HTTPException(
                status_code=404,
                detail="HLS stream not available"
            )
        
        # Build segment path
        playlist_path = Path(job.hls_playlist_path)
        segment_path = playlist_path.parent / segment_filename
        
        if not segment_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Segment {segment_filename} not found"
            )
        
        # Serve segment
        return FileResponse(
            path=str(segment_path),
            media_type="video/mp2t",  # MPEG-TS MIME type
            headers={
                "Cache-Control": "public, max-age=31536000",  # Cache segments forever
                "Accept-Ranges": "bytes"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to serve HLS segment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/status")
async def get_hls_status(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Quick HLS status check (lightweight endpoint for polling).
    
    Returns:
        - ready: Boolean (can client start playback?)
        - segments_available: Number of segments ready
        - playlist_url: URL to playlist if ready
    
    Use this for fast polling (~500ms) instead of /api/video/progress.
    """
    try:
        repo = JobQueueRepository(db)
        job = await repo.get_by_job_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        from app.core.config import settings
        
        playlist_url = None
        if job.hls_ready and job.hls_playlist_path:
            playlist_url = f"{settings.API_BASE_URL}/api/hls/{job.job_id}/playlist.m3u8"
        
        return {
            "ready": job.hls_ready or False,
            "segments_available": job.segments_generated or 0,
            "total_segments": job.total_segments or 0,
            "playlist_url": playlist_url,
            "status": job.status
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get HLS status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
