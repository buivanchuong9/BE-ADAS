"""
ModelVersion Model
==================
Tracks AI model versions for traceability and reproducibility.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from sqlalchemy.sql import func

from ..base import Base


class ModelVersion(Base):
    """AI model version tracking table"""
    __tablename__ = "model_versions"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Model identification
    model_name = Column(String(100), nullable=False, index=True)  # e.g., "yolo11n", "lane_detector"
    version = Column(String(50), nullable=False)  # e.g., "1.0.0", "v11"
    model_type = Column(String(50), nullable=False)  # detection, segmentation, classification
    
    # Model details
    framework = Column(String(50), nullable=True)  # pytorch, tensorflow, onnx
    architecture = Column(String(100), nullable=True)  # YOLOv11, ResNet50, etc.
    
    # File info
    file_path = Column(String(500), nullable=True)
    file_size_mb = Column(Float, nullable=True)
    checksum = Column(String(64), nullable=True)  # MD5 or SHA256
    
    # Performance metrics
    accuracy = Column(Float, nullable=True)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    inference_time_ms = Column(Float, nullable=True)  # Average inference time
    
    # Training info
    training_dataset = Column(String(200), nullable=True)
    training_date = Column(DateTime, nullable=True)
    epochs = Column(Integer, nullable=True)
    
    # Status
    is_active = Column(Integer, default=1, nullable=False)  # Boolean as Integer
    is_production = Column(Integer, default=0, nullable=False)  # Boolean as Integer
    
    # Description
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<ModelVersion(id={self.id}, name='{self.model_name}', version='{self.version}')>"
