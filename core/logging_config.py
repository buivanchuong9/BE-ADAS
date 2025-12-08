"""
ADAS Backend - Logging Configuration
Centralized logging setup with file rotation and structured logging
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
from typing import Optional

from core.config import settings


# ============ Logging Formatters ============

class ColoredFormatter(logging.Formatter):
    """Colored console formatter"""
    
    COLORS = {
        'DEBUG': '\033[36m',  # Cyan
        'INFO': '\033[32m',   # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',  # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


class StructuredFormatter(logging.Formatter):
    """JSON-like structured formatter for file logging"""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        
        # Format as compact JSON-like string
        return ' | '.join(f"{k}={v}" for k, v in log_data.items())


# ============ Logger Setup ============

def setup_logging(
    log_level: Optional[str] = None,
    log_dir: Optional[Path] = None,
    enable_console: bool = True,
    enable_file: bool = True
):
    """
    Setup application logging
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        enable_console: Enable console logging
        enable_file: Enable file logging
    """
    
    log_level = log_level or settings.LOG_LEVEL
    log_dir = log_dir or settings.LOG_DIR
    
    # Create log directory
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # ============ Console Handler ============
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # ============ File Handlers ============
    if enable_file:
        # General application log (rotating by size)
        app_log_file = log_dir / "adas_backend.log"
        app_file_handler = RotatingFileHandler(
            app_log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        app_file_handler.setLevel(logging.INFO)
        app_file_formatter = StructuredFormatter()
        app_file_handler.setFormatter(app_file_formatter)
        root_logger.addHandler(app_file_handler)
        
        # Error log (rotating daily)
        error_log_file = log_dir / "errors.log"
        error_file_handler = TimedRotatingFileHandler(
            error_log_file,
            when='midnight',
            interval=1,
            backupCount=30
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(app_file_formatter)
        root_logger.addHandler(error_file_handler)
        
        # Detection/Inference log
        detection_log_file = log_dir / "detections.log"
        detection_handler = RotatingFileHandler(
            detection_log_file,
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=3
        )
        detection_handler.setLevel(logging.DEBUG)
        detection_handler.setFormatter(app_file_formatter)
        
        # Add detection handler to specific logger
        detection_logger = logging.getLogger('adas.detection')
        detection_logger.addHandler(detection_handler)
        detection_logger.setLevel(logging.DEBUG)
        detection_logger.propagate = False
    
    # Suppress noisy third-party loggers
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.error').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
    
    logging.info(f"Logging configured - Level: {log_level}, Dir: {log_dir}")


# ============ Specialized Loggers ============

def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name"""
    return logging.getLogger(name)


def log_detection(
    model_name: str,
    frame_id: int,
    detections_count: int,
    processing_time_ms: float,
    warnings: list = None
):
    """Log detection event"""
    logger = logging.getLogger('adas.detection')
    logger.info(
        f"Detection: model={model_name}, frame={frame_id}, "
        f"count={detections_count}, time={processing_time_ms:.2f}ms, "
        f"warnings={warnings or []}"
    )


def log_alert(alert_type: str, severity: str, message: str, details: dict = None):
    """Log alert event"""
    logger = logging.getLogger('adas.alerts')
    logger.warning(
        f"Alert: type={alert_type}, severity={severity}, "
        f"message={message}, details={details or {}}"
    )


def log_training(training_id: str, epoch: int, loss: float, metrics: dict):
    """Log training progress"""
    logger = logging.getLogger('adas.training')
    logger.info(
        f"Training: id={training_id}, epoch={epoch}, "
        f"loss={loss:.4f}, metrics={metrics}"
    )


def log_api_call(method: str, endpoint: str, status_code: int, duration_ms: float):
    """Log API call"""
    logger = logging.getLogger('adas.api')
    logger.info(
        f"API: {method} {endpoint} - {status_code} ({duration_ms:.2f}ms)"
    )


# ============ Request ID Middleware Support ============

class RequestIDFilter(logging.Filter):
    """Add request ID to log records"""
    
    def __init__(self, request_id: Optional[str] = None):
        super().__init__()
        self.request_id = request_id
    
    def filter(self, record):
        record.request_id = self.request_id or 'N/A'
        return True


# ============ Performance Logging ============

class PerformanceLogger:
    """Context manager for logging performance metrics"""
    
    def __init__(self, operation: str, logger: Optional[logging.Logger] = None):
        self.operation = operation
        self.logger = logger or logging.getLogger('adas.performance')
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (datetime.now() - self.start_time).total_seconds() * 1000
        if exc_type is None:
            self.logger.info(f"Performance: {self.operation} completed in {duration_ms:.2f}ms")
        else:
            self.logger.error(
                f"Performance: {self.operation} failed after {duration_ms:.2f}ms - "
                f"{exc_type.__name__}: {exc_val}"
            )


# ============ Utility Functions ============

def log_startup_info():
    """Log application startup information"""
    logger = logging.getLogger('adas.startup')
    logger.info("=" * 80)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info("=" * 80)
    logger.info(f"Environment: {'Production' if not settings.DEBUG else 'Development'}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info(f"Server: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"Models Dir: {settings.MODELS_DIR}")
    logger.info(f"Dataset Dir: {settings.DATASET_DIR}")
    logger.info("=" * 80)


def log_shutdown_info():
    """Log application shutdown information"""
    logger = logging.getLogger('adas.shutdown')
    logger.info("=" * 80)
    logger.info("🛑 ADAS Backend shutting down...")
    logger.info("=" * 80)
