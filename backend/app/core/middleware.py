"""
Request ID Middleware for Distributed Tracing
==============================================
Adds unique request_id to each HTTP request for logging and debugging.

Usage in main.py:
    from .core.middleware import RequestIDMiddleware
    app.add_middleware(RequestIDMiddleware)

Access request_id in endpoints:
    from ..core.middleware import get_request_id
    request_id = get_request_id()
    logger.info(f"[{request_id}] Processing request...")
"""
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)

# Context variable for request ID (thread-safe)
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject unique request_id into each request.
    
    Request ID is extracted from:
    1. X-Request-ID header (if present)
    2. Generated UUID (if not present)
    
    The request_id is:
    - Stored in context variable (accessible anywhere)
    - Added to request.state
    - Added to response headers (X-Request-ID)
    - Logged for every request
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get('X-Request-ID')
        
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Store in context variable (accessible in sync/async functions)
        request_id_var.set(request_id)
        
        # Add to request state (accessible in route handlers)
        request.state.request_id = request_id
        
        # Log incoming request
        logger.info(
            f"[{request_id}] {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else None
            }
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Add request ID to response headers
            response.headers['X-Request-ID'] = request_id
            
            # Log response
            logger.info(
                f"[{request_id}] Response: {response.status_code}",
                extra={
                    "request_id": request_id,
                    "status_code": response.status_code
                }
            )
            
            return response
            
        except Exception as e:
            logger.error(
                f"[{request_id}] Request failed: {e}",
                exc_info=True,
                extra={"request_id": request_id}
            )
            raise
        
        finally:
            # Clean up context variable
            request_id_var.set(None)


def get_request_id() -> Optional[str]:
    """
    Get current request ID from context.
    
    Returns:
        Request ID string or None if not in request context
    
    Example:
        request_id = get_request_id()
        logger.info(f"[{request_id}] Processing...")
    """
    return request_id_var.get()
