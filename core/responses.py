# Standardized API responses
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict


class SuccessResponse(BaseModel):
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None
    model_config = ConfigDict()


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    model_config = ConfigDict()


def success_response(message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"success": True, "message": message, "data": data}


def error_response(error: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"success": False, "error": error, "message": message, "details": details}
