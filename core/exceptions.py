# Custom exceptions

class ADASException(Exception):
    """Base exception"""
    pass

class VideoProcessingError(ADASException):
    """Video processing error"""
    pass

class ModelLoadError(ADASException):
    """Model load error"""
    pass

class DatabaseError(ADASException):
    """Database error"""
    pass

class ValidationError(ADASException):
    """Validation error"""
    pass
