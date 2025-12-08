"""
ADAS Backend - Exception Handlers
Centralized exception handling with proper error responses
"""

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from typing import Union
import logging
import traceback
from datetime import datetime

from core.responses import (
    APIResponse,
    ErrorCode,
    ResponseStatus,
    error_response,
    validation_error_response
)

logger = logging.getLogger(__name__)


# ============ Custom Exceptions ============

class ADASBaseException(Exception):
    """Base exception for ADAS application"""
    def __init__(self, message: str, error_code: ErrorCode = ErrorCode.INTERNAL_ERROR):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DatabaseException(ADASBaseException):
    """Database related errors"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCode.DATABASE_ERROR)


class ModelException(ADASBaseException):
    """AI Model related errors"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCode.MODEL_ERROR)


class ValidationException(ADASBaseException):
    """Business validation errors"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCode.VALIDATION_ERROR)


class NotFoundException(ADASBaseException):
    """Resource not found errors"""
    def __init__(self, resource: str, id: Union[int, str]):
        message = f"{resource} with id '{id}' not found"
        super().__init__(message, ErrorCode.NOT_FOUND)


class InsufficientDataException(ADASBaseException):
    """Insufficient data for operation"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCode.INSUFFICIENT_DATA)


class ProcessingException(ADASBaseException):
    """Processing/computation errors"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCode.PROCESSING_FAILED)


# ============ Exception Handlers ============

async def adas_exception_handler(request: Request, exc: ADASBaseException):
    """Handle custom ADAS exceptions"""
    logger.error(f"ADAS Exception: {exc.message}", exc_info=True)
    
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    if exc.error_code == ErrorCode.NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.error_code == ErrorCode.VALIDATION_ERROR:
        status_code = status.HTTP_400_BAD_REQUEST
    elif exc.error_code == ErrorCode.CONFLICT:
        status_code = status.HTTP_409_CONFLICT
    
    response = error_response(
        error=exc.message,
        error_code=exc.error_code
    )
    
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode='json')
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions"""
    logger.warning(f"HTTP Exception: {exc.detail}")
    
    error_code = ErrorCode.INTERNAL_ERROR
    if exc.status_code == 404:
        error_code = ErrorCode.NOT_FOUND
    elif exc.status_code == 401:
        error_code = ErrorCode.UNAUTHORIZED
    elif exc.status_code == 403:
        error_code = ErrorCode.FORBIDDEN
    elif exc.status_code == 400:
        error_code = ErrorCode.BAD_REQUEST
    elif exc.status_code == 409:
        error_code = ErrorCode.CONFLICT
    
    response = error_response(
        error=str(exc.detail),
        error_code=error_code
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(mode='json')
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    logger.warning(f"Validation Error: {exc.errors()}")
    
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    response = validation_error_response(errors)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=response.model_dump(mode='json')
    )


async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle database exceptions"""
    logger.error(f"Database Error: {str(exc)}", exc_info=True)
    
    response = error_response(
        error="Database operation failed. Please try again later.",
        error_code=ErrorCode.DATABASE_ERROR
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(mode='json')
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    logger.error(f"Unhandled Exception: {str(exc)}", exc_info=True)
    logger.error(traceback.format_exc())
    
    response = error_response(
        error="An unexpected error occurred. Please contact support if this persists.",
        error_code=ErrorCode.INTERNAL_ERROR,
        data={"error_type": type(exc).__name__} if logger.isEnabledFor(logging.DEBUG) else None
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(mode='json')
    )


# ============ Exception Handler Registration ============

def register_exception_handlers(app):
    """Register all exception handlers with FastAPI app"""
    
    # Custom exceptions
    app.add_exception_handler(ADASBaseException, adas_exception_handler)
    
    # HTTP exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)
    
    # Validation exceptions
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # Database exceptions
    app.add_exception_handler(SQLAlchemyError, database_exception_handler)
    
    # General exceptions
    app.add_exception_handler(Exception, general_exception_handler)
    
    logger.info("Exception handlers registered successfully")


# ============ Helper Functions ============

def raise_not_found(resource: str, id: Union[int, str]):
    """Raise NotFoundException"""
    raise NotFoundException(resource, id)


def raise_validation_error(message: str):
    """Raise ValidationException"""
    raise ValidationException(message)


def raise_model_error(message: str):
    """Raise ModelException"""
    raise ModelException(message)


def raise_database_error(message: str):
    """Raise DatabaseException"""
    raise DatabaseException(message)
