"""
Upload and Storage API endpoints - Phase 4 Low Priority
Handles file uploads and storage management
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List
from datetime import datetime
import os

from ..models import storage

router = APIRouter(prefix="/api", tags=["upload", "storage"])


@router.post("/upload/image")
async def upload_image(file: UploadFile = File(...)):
    """
    Upload a single image (not part of dataset)
    
    FormData:
    - file: Image file (jpg, png, etc.)
    
    Returns:
    - file_path: Path where image is stored
    - url: URL to access the image
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
    
    # Mock storage path
    year_month = datetime.now().strftime("%Y/%m")
    file_path = f"/storage/images/{year_month}/{file.filename}"
    url = f"/api/files/images/{year_month}/{file.filename}"
    
    return {
        "success": True,
        "file_path": file_path,
        "url": url,
        "file_size_mb": round(file_size_mb, 2),
        "uploaded_at": datetime.now().isoformat()
    }


@router.post("/upload/batch")
async def upload_batch(files: List[UploadFile] = File(...)):
    """
    Upload multiple files at once
    
    FormData:
    - files: Array of files to upload
    
    Returns:
    - uploaded: List of successfully uploaded files
    - failed: List of files that failed to upload
    """
    uploaded = []
    failed = []
    
    for idx, file in enumerate(files):
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
            
            # Mock storage
            year_month = datetime.now().strftime("%Y/%m")
            
            # Determine type
            is_video = file.content_type and file.content_type.startswith("video/")
            is_image = file.content_type and file.content_type.startswith("image/")
            
            if is_video:
                file_path = f"/storage/videos/{year_month}/{file.filename}"
                url = f"/api/files/videos/{year_month}/{file.filename}"
            elif is_image:
                file_path = f"/storage/images/{year_month}/{file.filename}"
                url = f"/api/files/images/{year_month}/{file.filename}"
            else:
                file_path = f"/storage/files/{year_month}/{file.filename}"
                url = f"/api/files/misc/{year_month}/{file.filename}"
            
            # Create ID
            file_id = storage.dataset_counter
            storage.dataset_counter += 1
            
            uploaded.append({
                "filename": file.filename,
                "url": url,
                "id": file_id,
                "file_path": file_path,
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
async def get_storage_info():
    """
    Get storage information
    
    Returns:
    - total_gb: Total storage capacity
    - used_gb: Used storage space
    - available_gb: Available storage space
    - files_count: Total number of files
    - videos_count: Number of video files
    - images_count: Number of image files
    """
    # Calculate storage from existing data
    total_videos_size = sum(v.file_size_mb for v in storage.videos.values()) / 1024
    total_datasets_size = sum(d.file_size_mb for d in storage.datasets.values()) / 1024
    
    used_gb = total_videos_size + total_datasets_size
    
    # Mock total capacity
    total_gb = 1000.0  # 1TB
    available_gb = total_gb - used_gb
    
    # Count files
    videos_count = len(storage.videos)
    images_count = len([d for d in storage.datasets.values() 
                       if d.metadata and d.metadata.get("type") == "image"])
    files_count = len(storage.datasets)
    
    return {
        "success": True,
        "total_gb": round(total_gb, 2),
        "used_gb": round(used_gb, 2),
        "available_gb": round(available_gb, 2),
        "usage_percentage": round((used_gb / total_gb) * 100, 1),
        "files_count": files_count,
        "videos_count": videos_count,
        "images_count": images_count
    }


@router.delete("/storage/cleanup")
async def cleanup_old_files(days_old: int = 90):
    """
    Cleanup old files (dummy implementation)
    
    Query Params:
    - days_old: Delete files older than this many days (default: 90)
    
    Returns count of deleted files
    """
    from datetime import timedelta
    
    cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
    
    # Mock cleanup - in real implementation, would delete actual files
    initial_count = len(storage.datasets)
    
    # Remove old datasets
    old_datasets = [
        d_id for d_id, d in storage.datasets.items()
        if d.uploaded_at < cutoff_date
    ]
    
    for d_id in old_datasets:
        storage.datasets.pop(d_id)
    
    deleted_count = len(old_datasets)
    
    return {
        "success": True,
        "message": f"Deleted {deleted_count} files older than {days_old} days",
        "deleted_count": deleted_count,
        "remaining_count": len(storage.datasets)
    }
