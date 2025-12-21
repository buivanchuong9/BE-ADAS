"""
Models API endpoints - Phase 1 Critical
Handles AI model management and downloads
"""
from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime

from ..models import storage, ModelInfo

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/available")
async def get_available_models():
    """
    List all available models
    
    Returns list of models with download status, specs, and metadata
    """
    models = list(storage.models_catalog.values())
    
    return {
        "success": True,
        "models": [m.model_dump() for m in models],
        "total_models": len(models)
    }


@router.post("/download/{id}")
async def download_model(id: str):
    """
    Download a model to the server
    
    Path Params:
    - id: Model ID (e.g., yolo11s, yolo11m, depth-anything)
    
    Note: This is a dummy implementation. In production, this would
    actually download the model file from the download_url.
    """
    if id not in storage.models_catalog:
        raise HTTPException(status_code=404, detail=f"Model '{id}' not found in catalog")
    
    model = storage.models_catalog[id]
    
    if model.downloaded:
        return {
            "success": True,
            "message": f"Model '{model.name}' is already downloaded",
            "model": model.model_dump()
        }
    
    # Simulate download by updating the model
    model.downloaded = True
    model.file_path = f"/models/{id}.pt"
    
    return {
        "success": True,
        "message": f"Model '{model.name}' downloaded successfully",
        "model": {
            "id": model.id,
            "name": model.name,
            "file_path": model.file_path,
            "size_mb": model.size_mb,
            "downloaded": True
        }
    }


@router.get("/info/{id}")
async def get_model_info(id: str):
    """
    Get detailed information about a specific model
    
    Path Params:
    - id: Model ID
    """
    if id not in storage.models_catalog:
        raise HTTPException(status_code=404, detail=f"Model '{id}' not found")
    
    model = storage.models_catalog[id]
    
    return {
        "success": True,
        "model": model.model_dump()
    }


@router.delete("/delete/{id}")
async def delete_model(id: str):
    """
    Delete a model from the server
    
    Path Params:
    - id: Model ID
    
    Note: This doesn't actually delete the model file, just marks it as not downloaded
    """
    if id not in storage.models_catalog:
        raise HTTPException(status_code=404, detail=f"Model '{id}' not found")
    
    model = storage.models_catalog[id]
    
    if not model.downloaded:
        return {
            "success": False,
            "message": f"Model '{model.name}' is not downloaded"
        }
    
    # Mark as not downloaded
    model.downloaded = False
    model.file_path = None
    
    return {
        "success": True,
        "message": f"Model '{model.name}' deleted successfully"
    }


@router.post("/download-all")
async def download_all_models():
    """
    Download all essential models
    
    Downloads all models marked as essential for ADAS operation
    """
    essential_models = ["yolo11n", "mediapipe-face"]
    downloaded = []
    failed = []
    
    for model_id in essential_models:
        if model_id in storage.models_catalog:
            model = storage.models_catalog[model_id]
            if not model.downloaded:
                # Simulate download
                model.downloaded = True
                model.file_path = f"/models/{model_id}.pt"
                downloaded.append(model_id)
            else:
                downloaded.append(model_id)  # Already downloaded
        else:
            failed.append(model_id)
    
    return {
        "success": True,
        "downloaded": downloaded,
        "failed": failed,
        "message": f"Downloaded {len(downloaded)} models, {len(failed)} failed"
    }
