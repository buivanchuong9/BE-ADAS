"""
Custom exceptions for the application with request_id tracking
"""

from typing import Any, Optional


class AdasException(Exception):
    """Base exception for ADAS application with request_id tracking"""
    
    def __init__(
        self,
        message: str,
        code: str = "ADAS_ERROR",
        details: Optional[dict[str, Any]] = None,
        request_id: Optional[str] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        self.request_id = request_id
        super().__init__(self.message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert exception to JSON-serializable dict for API response"""
        return {
            "error": {
                "message": self.message,
                "code": self.code,
                "details": self.details,
                "request_id": self.request_id
            }
        }


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


class GPUOutOfMemoryError(AdasException):
    """GPU out of memory error"""
    
    def __init__(self, details: Optional[dict[str, Any]] = None, request_id: Optional[str] = None):
        super().__init__(
            "GPU out of memory. Try reducing batch size or video resolution.",
            code="GPU_OOM",
            details=details,
            request_id=request_id
        )


class VideoCorruptedError(AdasException):
    """Video file corrupted or unsupported format"""
    
    def __init__(self, video_path: str, request_id: Optional[str] = None):
        super().__init__(
            f"Video file corrupted or format not supported: {video_path}",
            code="VIDEO_CORRUPTED",
            details={"video_path": video_path},
            request_id=request_id
        )


class ModelNotFoundError(AdasException):
    """AI model not found or not loaded"""
    
    def __init__(self, model_name: str, request_id: Optional[str] = None):
        super().__init__(
            f"Model '{model_name}' not found or not downloaded",
            code="MODEL_NOT_FOUND",
            details={"model_name": model_name},
            request_id=request_id
        )
