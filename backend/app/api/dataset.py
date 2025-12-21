"""
Dataset API endpoints - Phase 1 Critical
Handles video/image dataset management for ADAS
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional, List
from datetime import datetime
import os

from ..models import storage, DatasetItem, VideoStatus

router = APIRouter(prefix="/api/dataset", tags=["dataset"])


@router.get("")
async def get_datasets(
    limit: int = 50,
    page: int = 1,
    status: Optional[str] = None,
    type: Optional[str] = None
):
    """
    Get list of datasets/videos uploaded
    
    Query Params:
    - limit: Number of items per page (default: 50)
    - page: Page number (default: 1)
    - status: Filter by status (uploaded/processing/ready/error)
    - type: Filter by type (video/image)
    """
    datasets = list(storage.datasets.values())
    
    # Apply filters
    if status:
        datasets = [d for d in datasets if d.status.value == status]
    
    # Calculate pagination
    total = len(datasets)
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_datasets = datasets[start_idx:end_idx]
    
    return {
        "success": True,
        "data": [d.model_dump() for d in paginated_datasets],
        "total": total,
        "page": page,
        "limit": limit
    }


@router.post("")
async def upload_dataset(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    type: Optional[str] = Form("video"),
    tags: Optional[str] = Form(None)
):
    """
    Upload file to dataset (video/image)
    
    FormData:
    - file: Video or image file
    - description: Optional description
    - type: "video" or "image" (default: video)
    - tags: Optional comma-separated tags
    """
    # Get file size
    file_size_bytes = 0
    content = await file.read()
    file_size_bytes = len(content)
    file_size_mb = file_size_bytes / (1024 * 1024)
    
    # Create dataset item
    dataset_id = storage.dataset_counter
    storage.dataset_counter += 1
    
    # Mock file path
    year_month = datetime.now().strftime("%Y/%m")
    file_path = f"/storage/videos/{year_month}/{file.filename}"
    
    # Determine duration for videos (dummy value)
    duration_seconds = None
    if type == "video":
        duration_seconds = 120.0  # Dummy duration
    
    dataset_item = DatasetItem(
        id=dataset_id,
        filename=file.filename,
        file_path=file_path,
        video_url=f"/api/video/download/{dataset_id}/{file.filename}",
        file_url=f"/api/dataset/{dataset_id}/download",
        description=description,
        file_size_mb=round(file_size_mb, 2),
        duration_seconds=duration_seconds,
        uploaded_at=datetime.now().isoformat(),
        status=VideoStatus.UPLOADED,
        ready_for_training=False,
        metadata={
            "type": type,
            "tags": tags.split(",") if tags else [],
            "original_filename": file.filename
        }
    )
    
    # Store in memory
    storage.datasets[dataset_id] = dataset_item
    
    # Also add to videos storage if it's a video
    if type == "video":
        from ..models import Video
        video = Video(
            id=dataset_id,
            filename=file.filename,
            file_path=file_path,
            video_url=f"/api/video/download/{dataset_id}/{file.filename}",
            file_size_mb=round(file_size_mb, 2),
            uploaded_at=datetime.now().isoformat(),
            status=VideoStatus.UPLOADED
        )
        storage.videos[dataset_id] = video
        storage.video_counter = max(storage.video_counter, dataset_id + 1)
    
    return {
        "success": True,
        "message": "File uploaded successfully",
        "data": {
            "id": dataset_item.id,
            "filename": dataset_item.filename,
            "file_path": dataset_item.file_path,
            "file_size_mb": dataset_item.file_size_mb,
            "uploaded_at": dataset_item.uploaded_at
        }
    }


@router.get("/{id}")
async def get_dataset_item(id: int):
    """
    Get detailed information about a dataset item
    
    Path Params:
    - id: Dataset item ID
    """
    if id not in storage.datasets:
        raise HTTPException(status_code=404, detail=f"Dataset item {id} not found")
    
    dataset_item = storage.datasets[id]
    
    # Add detections count if available
    detections_count = len([d for d in storage.detections if d.video_id == id])
    
    response_data = dataset_item.model_dump()
    response_data["detections_count"] = detections_count
    
    return {
        "success": True,
        "data": response_data
    }


@router.delete("/{id}")
async def delete_dataset(id: int):
    """
    Delete a dataset item
    
    Path Params:
    - id: Dataset item ID
    """
    if id not in storage.datasets:
        raise HTTPException(status_code=404, detail=f"Dataset item {id} not found")
    
    # Remove from storage
    dataset_item = storage.datasets.pop(id)
    
    # Also remove from videos if exists
    if id in storage.videos:
        storage.videos.pop(id)
    
    # Remove associated detections
    storage.detections = [d for d in storage.detections if d.video_id != id]
    
    return {
        "success": True,
        "message": f"Dataset item '{dataset_item.filename}' deleted successfully"
    }
