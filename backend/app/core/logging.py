"""
Structured logging configuration
"""

import logging
import sys
import json
from datetime import datetime
from typing import Any
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "job_id"):
            log_data["job_id"] = record.job_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_logging(log_level: str = "INFO", log_file: str = None):
    """
    Setup application logging
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
    """
    # Create formatters
    json_formatter = JSONFormatter()
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    
    # File handler if specified
    handlers = [console_handler]
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(json_formatter)
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        handlers=handlers
    )
    
    # Reduce noise from some libraries
    # Reduce noise from some libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get logger instance"""
    return logging.getLogger(name)


# ============================================================================
# SUPABASE LOG HANDLER
# ============================================================================

try:
    from supabase import create_client
    SUPABASE_CLIENT_AVAILABLE = True
except ImportError:
    SUPABASE_CLIENT_AVAILABLE = False

import threading
import queue
import atexit

class SupabaseLogHandler(logging.Handler):
    """
    Asynchronous handler to push logs to Supabase 'logs' table.
    Uses a background worker thread to prevent blocking the main app.
    """
    def __init__(self, url: str, key: str):
        super().__init__()
        self.url = url
        self.key = key
        self.client = None
        self.queue = queue.Queue(maxsize=1000)  # Drop oldest if full to save memory
        self.running = False
        self.worker_thread = None
        
        if SUPABASE_CLIENT_AVAILABLE and url and key:
            try:
                self.client = create_client(url, key)
                self.running = True
                self.worker_thread = threading.Thread(target=self._worker, name="SupabaseLogWorker", daemon=True)
                self.worker_thread.start()
                atexit.register(self.shutdown)
            except Exception as e:
                # Should not break app startup if Supabase fails
                sys.stderr.write(f"WARNING: Failed to initialize Supabase Log Handler: {e}\n")

    def _worker(self):
        """Background worker to consume logs from queue"""
        batch = []
        while self.running:
            try:
                # Try to get log from queue with timeout
                try:
                    record = self.queue.get(timeout=2.0)
                    batch.append(record)
                except queue.Empty:
                    pass
                
                # Send batch if we have items (immediate send for realtime feel, or batch if high volume)
                # For Realtime functionality, we prefer low latency, so send immediately or small batches
                if batch:
                    # Take up to 10 items at once if they piled up
                    while len(batch) < 10 and not self.queue.empty():
                        try:
                            batch.append(self.queue.get_nowait())
                        except queue.Empty:
                            break
                    
                    try:
                        # Insert into Supabase
                        self.client.table("logs").insert(batch).execute()
                    except Exception as e:
                        # Silent fail or stderr to avoid loop
                        # sys.stderr.write(f"Supabase log insert failed: {e}\n")
                        pass
                    finally:
                        for _ in batch:
                            self.queue.task_done()
                        batch = []
                        
            except Exception:
                # Catch all to keep worker alive
                pass

    def emit(self, record: logging.LogRecord):
        """Emit a log record"""
        if not self.running or not self.client:
            return
            
        try:
            # Anti-recursion: Don't log messages from supabase/httpx interactions
            if "supabase" in record.name or "httpx" in record.name or "httpcore" in record.name:
                return

            msg = record.getMessage()
            
            # Construct payload matching the 'logs' table schema
            log_entry = {
                "level": record.levelname,
                "message": msg,
                "created_at": datetime.utcnow().isoformat(),
                "metadata": {
                    "logger": record.name,
                    "module": record.module,
                    "func": record.funcName,
                    "line": record.lineno,
                    "path": record.pathname,
                    # Optional: Add context info if present in record
                    "request_id": getattr(record, "request_id", None)
                }
            }
            
            # Put in queue (non-blocking if not full)
            try:
                self.queue.put_nowait(log_entry)
            except queue.Full:
                pass # Drop log if queue is full to protect memory
                
        except Exception:
            self.handleError(record)

    def shutdown(self):
        """Cleanup handler"""
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)


# Update setup_logging to include Supabase handler
def setup_logging(log_level: str = "INFO", log_file: str = None):
    """
    Setup application logging
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
    """
    from app.core.config import settings
    
    # Create formatters
    json_formatter = JSONFormatter()
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    
    handlers = [console_handler]
    
    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(json_formatter)
        handlers.append(file_handler)
    
    # Supabase Handler (New)
    # Check if we have Service Role Key (preferred) or Anon Key (fallback but RLS might block INSERT)
    sb_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
    if sb_key and settings.SUPABASE_PROJECT_URL:
        try:
            sb_handler = SupabaseLogHandler(settings.SUPABASE_PROJECT_URL, sb_key)
            # Only send INFO and above to Supabase to save quota/noise
            sb_handler.setLevel(logging.INFO)
            handlers.append(sb_handler)
            # print(f"Supabase logging enabled for {settings.SUPABASE_PROJECT_URL}")
        except Exception as e:
            print(f"Failed to setup Supabase logging: {e}")

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        handlers=handlers,
        force=True # Ensure we override previous configs
    )
    
    # Reduce noise from some libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("supabase").setLevel(logging.WARNING)

