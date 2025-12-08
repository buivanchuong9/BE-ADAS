"""
Data Collection API Endpoints for ADAS System
Handles dataset collection with bounding box annotations
"""

from fastapi import UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import json
import shutil
from pathlib import Path
import uuid
from PIL import Image

# Dataset directories
DATASET_BASE_DIR = Path(__file__).parent.parent / "dataset"
DATASET_RAW_DIR = DATASET_BASE_DIR / "raw"
DATASET_IMAGES_DIR = DATASET_BASE_DIR / "images"
DATASET_LABELS_DIR = DATASET_BASE_DIR / "labels"

# Create directories
for directory in [DATASET_RAW_DIR, DATASET_IMAGES_DIR, DATASET_LABELS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# In-memory storage (replace with MongoDB/SQL in production)
dataset_storage = []

# YOLO class mapping
YOLO_CLASS_MAP = {
    "car": 0,
    "motorcycle": 1,
    "pedestrian": 2,
    "bicycle": 3,
    "traffic_light": 4,
    "traffic_sign": 5,
    "truck": 6,
    "bus": 7
}

# Pydantic models
class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float
    label: str

class DatasetMetadata(BaseModel):
    labels: List[str]
    boundingBoxes: List[BoundingBox]
    weather: str
    roadType: str
    description: Optional[str] = ""

class DatasetItem(BaseModel):
    id: str
    filePath: str
    labels: List[str]
    boundingBoxes: List[BoundingBox]
    weather: str
    roadType: str
    description: str
    timestamp: str

def create_yolo_labels(item_id: str, image_path: Path, metadata: DatasetMetadata):
    """
    Create YOLO format label files
    Format: class x_center y_center width height (all normalized 0-1)
    """
    try:
        # Get image dimensions
        with Image.open(image_path) as img:
            img_width, img_height = img.size
        
        # Create label file
        label_path = DATASET_LABELS_DIR / f"{item_id}.txt"
        
        with open(label_path, 'w') as f:
            for box in metadata.boundingBoxes:
                # Get class ID
                class_id = YOLO_CLASS_MAP.get(box.label, 0)
                
                # Convert to YOLO format (normalized center x, y, width, height)
                x_center = (box.x + box.width / 2) / img_width
                y_center = (box.y + box.height / 2) / img_height
                norm_width = box.width / img_width
                norm_height = box.height / img_height
                
                # Write YOLO format: class x_center y_center width height
                f.write(f"{class_id} {x_center:.6f} {y_center:.6f} {norm_width:.6f} {norm_height:.6f}\n")
                
    except Exception as e:
        print(f"Error creating YOLO labels: {e}")
        raise

def register_dataset_routes(app):
    """Register dataset collection routes to FastAPI app"""
    
    @app.post("/api/dataset")
    async def create_dataset_item(
        file: UploadFile = File(...),
        metadata: str = Form(...)
    ):
        """
        Create new dataset item with file and metadata
        Accepts images or videos with bounding box annotations
        Compatible with YOLO dataset format
        """
        try:
            # Parse metadata
            metadata_obj = json.loads(metadata)
            metadata_parsed = DatasetMetadata(**metadata_obj)
            
            # Generate unique ID
            item_id = str(uuid.uuid4())
            
            # Save file
            file_extension = Path(file.filename).suffix
            filename = f"{item_id}{file_extension}"
            file_path = DATASET_RAW_DIR / filename
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # For images, create YOLO format labels
            if file_extension.lower() in ['.jpg', '.jpeg', '.png', '.bmp']:
                # Copy image to images directory
                dest_image_path = DATASET_IMAGES_DIR / f"{item_id}.jpg"
                
                # Convert to JPG if needed
                with Image.open(file_path) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.save(dest_image_path, 'JPEG', quality=95)
                
                # Create YOLO labels
                create_yolo_labels(item_id, dest_image_path, metadata_parsed)
            
            # Create dataset item
            dataset_item = {
                "id": item_id,
                "filePath": str(file_path.relative_to(DATASET_BASE_DIR)),
                "labels": metadata_parsed.labels,
                "boundingBoxes": [box.dict() for box in metadata_parsed.boundingBoxes],
                "weather": metadata_parsed.weather,
                "roadType": metadata_parsed.roadType,
                "description": metadata_parsed.description,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            dataset_storage.append(dataset_item)
            
            return {
                "success": True,
                "id": item_id,
                "message": "Dataset item created successfully",
                "yolo_format": file_extension.lower() in ['.jpg', '.jpeg', '.png', '.bmp']
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/dataset")
    async def get_dataset_items():
        """Get all dataset items"""
        return dataset_storage

    @app.delete("/api/dataset/{item_id}")
    async def delete_dataset_item(item_id: str):
        """Delete dataset item and associated files"""
        global dataset_storage
        
        # Find item
        item = next((item for item in dataset_storage if item["id"] == item_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Dataset item not found")
        
        # Delete files
        try:
            file_path = DATASET_BASE_DIR / item["filePath"]
            if file_path.exists():
                file_path.unlink()
            
            # Delete image and label if exist
            image_path = DATASET_IMAGES_DIR / f"{item_id}.jpg"
            label_path = DATASET_LABELS_DIR / f"{item_id}.txt"
            
            if image_path.exists():
                image_path.unlink()
            if label_path.exists():
                label_path.unlink()
        except Exception as e:
            print(f"Error deleting files: {e}")
        
        # Remove from storage
        dataset_storage = [item for item in dataset_storage if item["id"] != item_id]
        
        return {"success": True, "message": "Dataset item deleted"}

    @app.post("/api/dataset/export-yolo")
    async def export_yolo_dataset():
        """
        Export collected dataset to YOLO training format
        Creates a data.yaml file for YOLOv11 training
        """
        try:
            # Create data.yaml
            data_yaml_content = f"""# ADAS Dataset for YOLOv11 Training
path: {DATASET_BASE_DIR.absolute()}
train: images
val: images
test: images

# Classes
nc: {len(YOLO_CLASS_MAP)}
names: {list(YOLO_CLASS_MAP.keys())}
"""
            
            data_yaml_path = DATASET_BASE_DIR / "data.yaml"
            with open(data_yaml_path, 'w') as f:
                f.write(data_yaml_content)
            
            # Count items
            image_count = len(list(DATASET_IMAGES_DIR.glob("*.jpg")))
            label_count = len(list(DATASET_LABELS_DIR.glob("*.txt")))
            
            return {
                "success": True,
                "message": "YOLO dataset exported successfully",
                "dataset_path": str(DATASET_BASE_DIR),
                "data_yaml": str(data_yaml_path),
                "images": image_count,
                "labels": label_count,
                "classes": list(YOLO_CLASS_MAP.keys()),
                "ready_for_training": image_count > 0 and label_count > 0
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/dataset/stats")
    async def get_dataset_stats():
        """Get dataset statistics"""
        image_count = len(list(DATASET_IMAGES_DIR.glob("*.jpg")))
        label_count = len(list(DATASET_LABELS_DIR.glob("*.txt")))
        
        # Count by class
        class_counts = {cls: 0 for cls in YOLO_CLASS_MAP.keys()}
        for label_file in DATASET_LABELS_DIR.glob("*.txt"):
            with open(label_file, 'r') as f:
                for line in f:
                    class_id = int(line.split()[0])
                    for cls_name, cls_id in YOLO_CLASS_MAP.items():
                        if cls_id == class_id:
                            class_counts[cls_name] += 1
                            break
        
        return {
            "total_items": len(dataset_storage),
            "total_images": image_count,
            "total_labels": label_count,
            "class_distribution": class_counts,
            "weather_distribution": {},
            "road_type_distribution": {}
        }
