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
    model_name = Column(String(100), nullable=False, index=True)
    model_type = Column(String(50), nullable=False)  # YOLO, MEDIAPIPE, LANE, etc.
    version = Column(String(50), nullable=False)
    
    # File info
    file_path = Column(String(500), nullable=False)
    file_size_mb = Column(Float, nullable=True)
    
    # Performance
    accuracy = Column(Float, nullable=True)
    
    # Status
    is_active = Column(Integer, default=1, nullable=False)  # BIT in SQL Server
    
    # Description
    description = Column(Text, nullable=True)
    
    # Description
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<ModelVersion(id={self.id}, name='{self.model_name}', version='{self.version}')>"
