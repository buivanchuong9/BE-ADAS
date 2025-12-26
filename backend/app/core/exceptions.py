"""
Custom exceptions for the application
"""

from typing import Any, Optional


class AdasException(Exception):
    """Base exception for ADAS application"""
    
    def __init__(
        self,
        message: str,
        code: str = "ADAS_ERROR",
        details: Optional[dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class DatabaseError(AdasException):
    """Database-related errors"""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code="DATABASE_ERROR", details=details)


class NotFoundError(AdasException):
    """Resource not found"""
    
    def __init__(self, resource: str, identifier: Any):
        message = f"{resource} with id '{identifier}' not found"
        super().__init__(message, code="NOT_FOUND", details={"resource": resource, "id": identifier})


class ValidationError(AdasException):
    """Validation errors"""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class AuthenticationError(AdasException):
    """Authentication errors"""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code="AUTHENTICATION_ERROR")


class AuthorizationError(AdasException):
    """Authorization errors"""
    
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, code="AUTHORIZATION_ERROR")


class VideoProcessingError(AdasException):
    """Video processing errors"""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code="VIDEO_PROCESSING_ERROR", details=details)


class JobNotFoundError(NotFoundError):
    """Job not found error"""
    
    def __init__(self, job_id: str):
        super().__init__("Job", job_id)
