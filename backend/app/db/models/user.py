"""
User Model
==========
Represents system users (drivers, analysts, admins).
"""

from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from ..base import Base


class UserRole(str, enum.Enum):
    """User roles"""
    ADMIN = "admin"
    ANALYST = "analyst"
    DRIVER = "driver"
    VIEWER = "viewer"


class User(Base):
    """User table"""
    __tablename__ = "users"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User details
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.DRIVER)
    
    # Profile
    full_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    
    # Status
    is_active = Column(Integer, default=1, nullable=False)  # Use Integer for SQL Server
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login = Column(DateTime, nullable=True)
    
    # Relationships
    vehicles = relationship("Vehicle", back_populates="owner", cascade="all, delete-orphan")
    trips = relationship("Trip", back_populates="driver", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
