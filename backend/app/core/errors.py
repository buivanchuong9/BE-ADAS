"""
STRUCTURED ERROR HANDLING SYSTEM
=================================
Phase 8: Standardized error codes and responses.

PURPOSE:
Provide consistent, informative error responses across all API endpoints.

FEATURES:
- Error code taxonomy
- HTTP status code mapping
- Vietnamese/English error messages
- Structured error responses
- Error logging and tracking

ERROR CATEGORIES:
- 1xxx: Authentication/Authorization errors
- 2xxx: Validation errors
- 3xxx: Database errors
- 4xxx: Processing errors
- 5xxx: System errors

Author: Senior ADAS Engineer
Date: 2025-12-26 (Phase 8)
"""

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
import logging
import traceback

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """Standardized error codes."""
    
    # Authentication (1xxx)
    AUTH_INVALID_CREDENTIALS = "AUTH_1001"
    AUTH_TOKEN_EXPIRED = "AUTH_1002"
    AUTH_TOKEN_INVALID = "AUTH_1003"
    AUTH_INSUFFICIENT_PERMISSIONS = "AUTH_1004"
    AUTH_USER_NOT_FOUND = "AUTH_1005"
    AUTH_USER_INACTIVE = "AUTH_1006"
    
    # Validation (2xxx)
    VALIDATION_INVALID_INPUT = "VAL_2001"
    VALIDATION_MISSING_FIELD = "VAL_2002"
    VALIDATION_INVALID_FORMAT = "VAL_2003"
    VALIDATION_VALUE_OUT_OF_RANGE = "VAL_2004"
    VALIDATION_FILE_TOO_LARGE = "VAL_2005"
    VALIDATION_UNSUPPORTED_FILE_TYPE = "VAL_2006"
    
    # Database (3xxx)
    DB_CONNECTION_ERROR = "DB_3001"
    DB_QUERY_ERROR = "DB_3002"
    DB_CONSTRAINT_VIOLATION = "DB_3003"
    DB_RECORD_NOT_FOUND = "DB_3004"
    DB_DUPLICATE_ENTRY = "DB_3005"
    
    # Processing (4xxx)
    PROC_VIDEO_PROCESSING_FAILED = "PROC_4001"
    PROC_MODEL_LOAD_FAILED = "PROC_4002"
    PROC_INFERENCE_FAILED = "PROC_4003"
    PROC_JOB_NOT_FOUND = "PROC_4004"
    PROC_JOB_ALREADY_RUNNING = "PROC_4005"
    PROC_QUEUE_FULL = "PROC_4006"
    
    # System (5xxx)
    SYS_INTERNAL_ERROR = "SYS_5001"
    SYS_SERVICE_UNAVAILABLE = "SYS_5002"
    SYS_RESOURCE_EXHAUSTED = "SYS_5003"
    SYS_TIMEOUT = "SYS_5004"
    SYS_STORAGE_ERROR = "SYS_5005"


class ErrorMessage:
    """Error messages in English and Vietnamese."""
    
    MESSAGES = {
        # Authentication
        ErrorCode.AUTH_INVALID_CREDENTIALS: {
            "en": "Invalid username or password",
            "vi": "Tên đăng nhập hoặc mật khẩu không đúng"
        },
        ErrorCode.AUTH_TOKEN_EXPIRED: {
            "en": "Authentication token has expired",
            "vi": "Token xác thực đã hết hạn"
        },
        ErrorCode.AUTH_TOKEN_INVALID: {
            "en": "Invalid authentication token",
            "vi": "Token xác thực không hợp lệ"
        },
        ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS: {
            "en": "Insufficient permissions for this action",
            "vi": "Không đủ quyền để thực hiện hành động này"
        },
        
        # Validation
        ErrorCode.VALIDATION_INVALID_INPUT: {
            "en": "Invalid input data",
            "vi": "Dữ liệu đầu vào không hợp lệ"
        },
        ErrorCode.VALIDATION_FILE_TOO_LARGE: {
            "en": "File size exceeds maximum limit",
            "vi": "Kích thước tệp vượt quá giới hạn"
        },
        ErrorCode.VALIDATION_UNSUPPORTED_FILE_TYPE: {
            "en": "Unsupported file type",
            "vi": "Loại tệp không được hỗ trợ"
        },
        
        # Database
        ErrorCode.DB_CONNECTION_ERROR: {
            "en": "Database connection error",
            "vi": "Lỗi kết nối cơ sở dữ liệu"
        },
        ErrorCode.DB_RECORD_NOT_FOUND: {
            "en": "Record not found",
            "vi": "Không tìm thấy bản ghi"
        },
        
        # Processing
        ErrorCode.PROC_VIDEO_PROCESSING_FAILED: {
            "en": "Video processing failed",
            "vi": "Xử lý video thất bại"
        },
        ErrorCode.PROC_MODEL_LOAD_FAILED: {
            "en": "Failed to load AI model",
            "vi": "Không thể tải mô hình AI"
        },
        ErrorCode.PROC_JOB_NOT_FOUND: {
            "en": "Job not found",
            "vi": "Không tìm thấy công việc"
        },
        
        # System
        ErrorCode.SYS_INTERNAL_ERROR: {
            "en": "Internal server error",
            "vi": "Lỗi máy chủ nội bộ"
        },
        ErrorCode.SYS_SERVICE_UNAVAILABLE: {
            "en": "Service temporarily unavailable",
            "vi": "Dịch vụ tạm thời không khả dụng"
        },
    }
    
    @classmethod
    def get(cls, code: ErrorCode, lang: str = "en") -> str:
        """Get error message for code and language."""
        return cls.MESSAGES.get(code, {}).get(lang, "Unknown error")


class AdasException(Exception):
    """
    Custom exception for ADAS system.
    
    Usage:
        raise AdasException(
            code=ErrorCode.PROC_VIDEO_PROCESSING_FAILED,
            message="Frame extraction failed",
            status_code=500,
            details={"frame": 123}
        )
    """
    
    def __init__(
        self,
        code: ErrorCode,
        message: Optional[str] = None,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.code = code
        self.message = message or ErrorMessage.get(code, "en")
        self.message_vi = ErrorMessage.get(code, "vi")
        self.status_code = status_code
        self.details = details or {}
        
        super().__init__(self.message)


def create_error_response(
    code: ErrorCode,
    message: Optional[str] = None,
    status_code: int = 500,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create standardized error response.
    
    Args:
        code: Error code
        message: Optional custom message
        status_code: HTTP status code
        details: Additional error details
        request_id: Request ID for tracking
        
    Returns:
        Standardized error response dict
    """
    return {
        "success": False,
        "error": {
            "code": code.value,
            "message": message or ErrorMessage.get(code, "en"),
            "message_vi": ErrorMessage.get(code, "vi"),
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id
        }
    }


async def adas_exception_handler(request: Request, exc: AdasException) -> JSONResponse:
    """
    Exception handler for AdasException.
    
    Register in main.py:
        app.add_exception_handler(AdasException, adas_exception_handler)
    """
    request_id = getattr(request.state, "request_id", None)
    
    # Log error
    logger.error(
        f"AdasException: {exc.code.value} - {exc.message}",
        extra={
            "request_id": request_id,
            "error_code": exc.code.value,
            "details": exc.details
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
            request_id=request_id
        )
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Exception handler for FastAPI HTTPException.
    
    Register in main.py:
        app.add_exception_handler(HTTPException, http_exception_handler)
    """
    request_id = getattr(request.state, "request_id", None)
    
    # Map HTTP status to error code
    code_mapping = {
        401: ErrorCode.AUTH_TOKEN_INVALID,
        403: ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS,
        404: ErrorCode.DB_RECORD_NOT_FOUND,
        422: ErrorCode.VALIDATION_INVALID_INPUT,
        500: ErrorCode.SYS_INTERNAL_ERROR,
        503: ErrorCode.SYS_SERVICE_UNAVAILABLE
    }
    
    error_code = code_mapping.get(exc.status_code, ErrorCode.SYS_INTERNAL_ERROR)
    
    logger.warning(
        f"HTTPException: {exc.status_code} - {exc.detail}",
        extra={"request_id": request_id}
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            code=error_code,
            message=str(exc.detail),
            status_code=exc.status_code,
            request_id=request_id
        )
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    Exception handler for request validation errors.
    
    Register in main.py:
        app.add_exception_handler(RequestValidationError, validation_exception_handler)
    """
    request_id = getattr(request.state, "request_id", None)
    
    # Extract validation errors
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    logger.warning(
        f"Validation error: {len(errors)} fields",
        extra={"request_id": request_id, "errors": errors}
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=create_error_response(
            code=ErrorCode.VALIDATION_INVALID_INPUT,
            status_code=422,
            details={"validation_errors": errors},
            request_id=request_id
        )
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all exception handler for unhandled exceptions.
    
    Register in main.py:
        app.add_exception_handler(Exception, unhandled_exception_handler)
    """
    request_id = getattr(request.state, "request_id", None)
    
    # Log with full traceback
    logger.error(
        f"Unhandled exception: {type(exc).__name__} - {str(exc)}",
        extra={
            "request_id": request_id,
            "exception_type": type(exc).__name__,
            "traceback": traceback.format_exc()
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            code=ErrorCode.SYS_INTERNAL_ERROR,
            message="An unexpected error occurred",
            status_code=500,
            details={"exception_type": type(exc).__name__} if logger.level == logging.DEBUG else {},
            request_id=request_id
        )
    )


if __name__ == "__main__":
    # Test error handling
    print("Structured Error Handling Test")
    print("=" * 50)
    
    # Test error creation
    print("\nError Response:")
    error = create_error_response(
        code=ErrorCode.PROC_VIDEO_PROCESSING_FAILED,
        details={"video_id": "vid_001", "frame": 123},
        request_id="req_123"
    )
    
    import json
    print(json.dumps(error, indent=2))
    
    # Test exception
    print("\nAdasException:")
    try:
        raise AdasException(
            code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            status_code=401
        )
    except AdasException as e:
        print(f"Code: {e.code.value}")
        print(f"Message (EN): {e.message}")
        print(f"Message (VI): {e.message_vi}")
        print(f"Status: {e.status_code}")
    
    print("\n✓ Error handling system working")
