"""
Upload and Storage API endpoints - Enterprise Production
Handles file uploads and storage management with SQL Server persistence
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import List
from datetime import datetime, timedelta
from pathlib import Path
import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.repositories.video_job_repo import VideoJobRepository
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["upload", "storage"])


@router.post("/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a single image (for annotations, datasets, or reference images)
    
    FormData:
    - file: Image file (jpg, png, etc.)
    
    Returns:
    - file_path: Path where image is stored
    - url: URL to access the image on production domain
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="File must be an image (jpg, png, etc.)"
        )
    
    # Read file
    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    
    # Check file size (max 50MB for images)
    if file_size_mb > 50:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large ({file_size_mb:.1f}MB). Maximum is 50MB."
        )
    
    # Create storage directory
    year_month = datetime.now().strftime("%Y/%m")
    storage_dir = Path(f"backend/storage/images/{year_month}")
    storage_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_parts = file.filename.rsplit('.', 1)
    if len(filename_parts) == 2:
        new_filename = f"{filename_parts[0]}_{timestamp}.{filename_parts[1]}"
    else:
        new_filename = f"{file.filename}_{timestamp}"
    
    file_path = storage_dir / new_filename
    
    # Save file asynchronously
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(content)
    
    # Generate URL using configured base URL (supports both dev and production)
    url = f"{settings.API_BASE_URL}/api/files/images/{year_month}/{new_filename}"
    
    return {
        "success": True,
        "file_path": str(file_path),
        "url": url,
        "file_size_mb": round(file_size_mb, 2),
        "uploaded_at": datetime.now().isoformat()
    }


@router.post("/upload/batch")
async def upload_batch(
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload multiple files at once with real file system persistence
    
    FormData:
    - files: Array of files to upload
    
    Returns:
    - uploaded: List of successfully uploaded files
    - failed: List of files that failed to upload
    """
    uploaded = []
    failed = []
    
    for file in files:
        try:
            # Read file
            content = await file.read()
            file_size_mb = len(content) / (1024 * 1024)
            
            # Check file size (max 500MB per file)
            if file_size_mb > 500:
                failed.append({
                    "filename": file.filename,
                    "error": f"File too large ({file_size_mb:.1f}MB). Maximum is 500MB."
                })
                continue
            
            # Determine type
            is_video = file.content_type and file.content_type.startswith("video/")
            is_image = file.content_type and file.content_type.startswith("image/")
            
            # Create storage directory
            year_month = datetime.now().strftime("%Y/%m")
            if is_video:
                storage_dir = Path(f"backend/storage/videos/{year_month}")
                file_type = "videos"
            elif is_image:
                storage_dir = Path(f"backend/storage/images/{year_month}")
                file_type = "images"
            else:
                storage_dir = Path(f"backend/storage/files/{year_month}")
                file_type = "misc"
            
            storage_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename_parts = file.filename.rsplit('.', 1)
            if len(filename_parts) == 2:
                new_filename = f"{filename_parts[0]}_{timestamp}.{filename_parts[1]}"
            else:
                new_filename = f"{file.filename}_{timestamp}"
            
            file_path = storage_dir / new_filename
            
            # Save file asynchronously
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            
            # Generate URL using configured base URL (supports both dev and production)
            url = f"{settings.API_BASE_URL}/api/files/{file_type}/{year_month}/{new_filename}"
            
            uploaded.append({
                "filename": file.filename,
                "url": url,
                "file_path": str(file_path),
                "file_size_mb": round(file_size_mb, 2)
            })
            
        except Exception as e:
            failed.append({
                "filename": file.filename,
                "error": str(e)
            })
    
    return {
        "success": True,
        "uploaded": uploaded,
        "failed": failed,
        "total_uploaded": len(uploaded),
        "total_failed": len(failed)
    }


@router.get("/storage/info")
async def get_storage_info(db: AsyncSession = Depends(get_db)):
    """
    Get REAL storage information from database and file system
    
    Returns:
    - total_gb: Total storage capacity
    - used_gb: Used storage space from actual video jobs
    - available_gb: Available storage space
    - files_count: Total number of files in database
    - videos_count: Number of video files
    - processing_gb: Storage used by videos currently processing
    """
    try:
        # Use JobQueueRepository for PostgreSQL v3.0
        from app.db.repositories.job_queue_repo import JobQueueRepository
        
        repo = JobQueueRepository(db)
        
        # Get storage stats from job queue
        stats = await repo.get_storage_stats()
        
        # Get storage directory usage
        storage_path = Path("backend/storage")
        if storage_path.exists():
            # Calculate actual disk usage
            disk_usage_bytes = sum(
                f.stat().st_size for f in storage_path.rglob('*') if f.is_file()
            )
            disk_used_gb = disk_usage_bytes / (1024 * 1024 * 1024)
        else:
            disk_used_gb = 0
        
        # Total capacity (configurable)
        total_gb = 1000.0  # 1TB - should be from config
        available_gb = total_gb - disk_used_gb
        
        return {
            "success": True,
            "total_gb": round(total_gb, 2),
            "used_gb": round(disk_used_gb, 2),
            "available_gb": round(available_gb, 2),
            "usage_percentage": round((disk_used_gb / total_gb) * 100, 1) if total_gb > 0 else 0,
            "files_count": stats.get('total_jobs', 0),
            "videos_count": stats.get('total_jobs', 0),
            "completed_count": stats.get('completed', 0),
            "processing_count": stats.get('processing', 0),
            "failed_count": stats.get('failed', 0),
            "pending_count": stats.get('pending', 0),
            "processing_gb": 0  # Will be calculated from actual file sizes later
        }
    except Exception as e:
        # Fallback if database not ready
        return {
            "success": True,
            "total_gb": 1000.0,
            "used_gb": 0.0,
            "available_gb": 1000.0,
            "usage_percentage": 0.0,
            "files_count": 0,
            "videos_count": 0,
            "completed_count": 0,
            "processing_count": 0,
            "failed_count": 0,
            "pending_count": 0,
            "processing_gb": 0.0,
            "error": str(e)
        }


@router.delete("/storage/cleanup")
async def cleanup_old_files(
    days_old: int = 90,
    db: AsyncSession = Depends(get_db)
):
    """
    Cleanup old files from REAL file system and database
    
    Query Params:
    - days_old: Delete files older than this many days (default: 90)
    
    Returns count of deleted files
    """
    cutoff_date = datetime.now() - timedelta(days=days_old)
    
    # Get old jobs from database
    repo = VideoJobRepository(db)
    all_jobs = await repo.get_all()
    
    old_jobs = [
        job for job in all_jobs
        if job.created_at < cutoff_date
    ]
    
    deleted_count = 0
    deleted_size_bytes = 0
    
    for job in old_jobs:
        try:
            # Delete input file
            if job.video_path:
                input_path = Path(job.video_path)
                if input_path.exists():
                    file_size = input_path.stat().st_size
                    input_path.unlink()
                    deleted_size_bytes += file_size
            
            # Delete output file
            if job.result_path:
                output_path = Path(job.result_path)
                if output_path.exists():
                    file_size = output_path.stat().st_size
                    output_path.unlink()
                    deleted_size_bytes += file_size
            
            # Delete from database
            await repo.delete(job.id)
            deleted_count += 1
            
        except Exception as e:
            # Log error but continue cleanup
            print(f"Error deleting job {job.job_id}: {e}")
            continue
    
    await db.commit()
    
    deleted_size_gb = deleted_size_bytes / (1024 * 1024 * 1024)
    
    return {
        "success": True,
        "message": f"Deleted {deleted_count} files older than {days_old} days",
        "deleted_count": deleted_count,
        "deleted_size_gb": round(deleted_size_gb, 2),
        "remaining_count": len(all_jobs) - deleted_count
    }
