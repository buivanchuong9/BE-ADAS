"""
ADAS Backend - Core Module
Production-ready core infrastructure components
"""

from core.config import settings, get_settings, is_production, get_device, print_startup_info
from core.responses import (
    APIResponse,
    PaginatedResponse,
    HealthResponse,
    StatusResponse,
    success_response,
    error_response,
    validation_error_response,
    ErrorCode,
    ResponseStatus,
)
from core.exceptions import (
    ADASBaseException,
    DatabaseException,
    ModelException,
    ValidationException,
    NotFoundException,
    InsufficientDataException,
    ProcessingException,
    raise_not_found,
    raise_validation_error,
    raise_model_error,
    raise_database_error,
    register_exception_handlers,
)
from core.logging_config import (
    setup_logging,
    get_logger,
    log_detection,
    log_alert,
    log_training,
    log_api_call,
    log_startup_info,
    log_shutdown_info,
    PerformanceLogger,
)

__all__ = [
    # Config
    'settings',
    'get_settings',
    'is_production',
    'get_device',
    'print_startup_info',
    
    # Responses
    'APIResponse',
    'PaginatedResponse',
    'HealthResponse',
    'StatusResponse',
    'success_response',
    'error_response',
    'validation_error_response',
    'ErrorCode',
    'ResponseStatus',
    
    # Exceptions
    'ADASBaseException',
    'DatabaseException',
    'ModelException',
    'ValidationException',
    'NotFoundException',
    'InsufficientDataException',
    'ProcessingException',
    'raise_not_found',
    'raise_validation_error',
    'raise_model_error',
    'raise_database_error',
    'register_exception_handlers',
    
    # Logging
    'setup_logging',
    'get_logger',
    'log_detection',
    'log_alert',
    'log_training',
    'log_api_call',
    'log_startup_info',
    'log_shutdown_info',
    'PerformanceLogger',
]
