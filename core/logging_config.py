# ASCII-safe logging configuration for Windows Server
# NO Unicode characters - cp1252 compatible only

import logging
import sys
import os
from datetime import datetime


def setup_logging():
    """
    Configure production-safe logging for Windows Server.
    All log messages are ASCII-only (cp1252 compatible).
    NO emojis or Unicode characters.
    """
    
    # Create logs directory if it doesn't exist
    try:
        os.makedirs("logs", exist_ok=True)
    except Exception:
        pass
    
    # ASCII-only formatter (NO Unicode)
    formatter = logging.Formatter(
        fmt='{"time":"%(asctime)s","level":"%(levelname)s","module":"%(module)s","message":"%(message)s"}',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler with explicit UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # File handler with explicit UTF-8 encoding
    log_filename = f"logs/adas_backend_{datetime.now().strftime('%Y%m%d')}.log"
    try:
        file_handler = logging.FileHandler(
            log_filename,
            mode='a',
            encoding='utf-8',
            errors='replace'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
    except Exception:
        file_handler = None
    
    # Configure root logger
    logger = logging.getLogger("adas-backend")
    logger.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    if file_handler:
        logger.addHandler(file_handler)
    
    # Prevent duplicate logs
    logger.propagate = False
    
    return logger
