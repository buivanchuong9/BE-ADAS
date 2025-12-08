"""
Models Management API Router
Download, install, and manage AI models (YOLOv8, YOLOP, MiDaS)
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import os
from pathlib import Path
import urllib.request
import json

router = APIRouter(prefix="/api/models", tags=["Models"])

# Model configurations
MODELS_CONFIG = {
    "yolov8n": {
        "name": "YOLOv8 Nano",
        "description": "Fastest YOLO model for real-time detection",
        "url": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt",
        "size_mb": 6.2,
        "accuracy": 37.3,
        "speed_ms": 1.5,
        "type": "detection",
        "file": "yolov8n.pt"
    },
    "yolov8s": {
        "name": "YOLOv8 Small",
        "description": "Balanced speed and accuracy",
        "url": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8s.pt",
        "size_mb": 22.5,
        "accuracy": 44.9,
        "speed_ms": 2.5,
        "type": "detection",
        "file": "yolov8s.pt"
    },
    "yolov8m": {
        "name": "YOLOv8 Medium",
        "description": "Good accuracy, moderate speed",
        "url": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8m.pt",
        "size_mb": 49.7,
        "accuracy": 50.2,
        "speed_ms": 4.5,
        "type": "detection",
        "file": "yolov8m.pt"
    },
    "yolov8l": {
        "name": "YOLOv8 Large",
        "description": "High accuracy detection",
        "url": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8l.pt",
        "size_mb": 83.7,
        "accuracy": 52.9,
        "speed_ms": 6.5,
        "type": "detection",
        "file": "yolov8l.pt"
    },
    "yolov8x": {
        "name": "YOLOv8 Extra Large",
        "description": "Best accuracy, slower speed",
        "url": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8x.pt",
        "size_mb": 130.5,
        "accuracy": 53.9,
        "speed_ms": 10.5,
        "type": "detection",
        "file": "yolov8x.pt"
    },
    "yolop": {
        "name": "YOLOP",
        "description": "Lane detection and drivable area",
        "url": "https://github.com/hustvl/YOLOP/releases/download/v1.0/yolop.pt",
        "size_mb": 30.0,
        "accuracy": 89.5,
        "speed_ms": 15.0,
        "type": "lane_detection",
        "file": "yolop.pt"
    },
    "midas_small": {
        "name": "MiDaS Small",
        "description": "Depth estimation - Fast",
        "url": "https://github.com/isl-org/MiDaS/releases/download/v3_1/midas_v3_1_small.pt",
        "size_mb": 45.0,
        "accuracy": 85.0,
        "speed_ms": 20.0,
        "type": "depth",
        "file": "midas_small.pt"
    }
}

MODELS_DIR = Path("ai_models/weights")
MODELS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/available")
async def get_available_models() -> Dict[str, Any]:
    """
    Lấy danh sách tất cả models có thể download
    """
    models_status = []
    
    for model_id, config in MODELS_CONFIG.items():
        model_path = MODELS_DIR / config["file"]
        is_downloaded = model_path.exists()
        
        models_status.append({
            "id": model_id,
            "name": config["name"],
            "description": config["description"],
            "type": config["type"],
            "size_mb": config["size_mb"],
            "accuracy": config["accuracy"],
            "speed_ms": config["speed_ms"],
            "downloaded": is_downloaded,
            "file_path": str(model_path) if is_downloaded else None
        })
    
    return {
        "success": True,
        "models": models_status,
        "total_models": len(models_status),
        "downloaded_count": sum(1 for m in models_status if m["downloaded"])
    }


@router.post("/download/{model_id}")
async def download_model(model_id: str) -> Dict[str, Any]:
    """
    Download một AI model
    """
    if model_id not in MODELS_CONFIG:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    config = MODELS_CONFIG[model_id]
    model_path = MODELS_DIR / config["file"]
    
    # Check if already downloaded
    if model_path.exists():
        return {
            "success": True,
            "message": f"Model {config['name']} already downloaded",
            "model_id": model_id,
            "file_path": str(model_path)
        }
    
    try:
        # Download model
        print(f"Downloading {config['name']} from {config['url']}...")
        urllib.request.urlretrieve(config['url'], model_path)
        
        # Verify download
        if model_path.exists():
            file_size_mb = model_path.stat().st_size / (1024 * 1024)
            return {
                "success": True,
                "message": f"Model {config['name']} downloaded successfully",
                "model_id": model_id,
                "file_path": str(model_path),
                "size_mb": round(file_size_mb, 2)
            }
        else:
            raise Exception("Download failed - file not found")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.delete("/delete/{model_id}")
async def delete_model(model_id: str) -> Dict[str, Any]:
    """
    Xóa một model đã download
    """
    if model_id not in MODELS_CONFIG:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    config = MODELS_CONFIG[model_id]
    model_path = MODELS_DIR / config["file"]
    
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model {config['name']} not downloaded")
    
    try:
        model_path.unlink()
        return {
            "success": True,
            "message": f"Model {config['name']} deleted successfully",
            "model_id": model_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/info/{model_id}")
async def get_model_info(model_id: str) -> Dict[str, Any]:
    """
    Lấy thông tin chi tiết của một model
    """
    if model_id not in MODELS_CONFIG:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    config = MODELS_CONFIG[model_id]
    model_path = MODELS_DIR / config["file"]
    
    info = {
        "id": model_id,
        "name": config["name"],
        "description": config["description"],
        "type": config["type"],
        "size_mb": config["size_mb"],
        "accuracy": config["accuracy"],
        "speed_ms": config["speed_ms"],
        "downloaded": model_path.exists(),
        "file_path": str(model_path) if model_path.exists() else None,
        "download_url": config["url"]
    }
    
    if model_path.exists():
        info["actual_size_mb"] = round(model_path.stat().st_size / (1024 * 1024), 2)
    
    return info


@router.post("/download-all")
async def download_all_essential_models() -> Dict[str, Any]:
    """
    Download tất cả models cần thiết (YOLOv8n, YOLOP, MiDaS)
    """
    essential_models = ["yolov8n", "yolop", "midas_small"]
    results = []
    
    for model_id in essential_models:
        try:
            result = await download_model(model_id)
            results.append(result)
        except Exception as e:
            results.append({
                "success": False,
                "model_id": model_id,
                "error": str(e)
            })
    
    success_count = sum(1 for r in results if r.get("success"))
    
    return {
        "success": success_count == len(essential_models),
        "message": f"Downloaded {success_count}/{len(essential_models)} models",
        "results": results
    }
