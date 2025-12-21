"""
Authentication and User Management API endpoints - Phase 5 Optional
Handles user authentication and authorization (dummy implementation for frontend testing)
"""
from fastapi import APIRouter, HTTPException, Header, Form
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import uuid
import hashlib

router = APIRouter(prefix="/api", tags=["authentication", "users"])


# Request models
class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str
    email: Optional[str] = None


# In-memory user storage (dummy)
_users = {
    "user_001": {
        "id": "user_001",
        "username": "admin",
        "password_hash": hashlib.sha256("admin123".encode()).hexdigest(),  # admin123
        "role": "admin",
        "email": "admin@adas.com",
        "created_at": "2025-12-01T00:00:00"
    },
    "user_002": {
        "id": "user_002",
        "username": "driver1",
        "password_hash": hashlib.sha256("driver123".encode()).hexdigest(),  # driver123
        "role": "driver",
        "email": "driver1@adas.com",
        "created_at": "2025-12-15T00:00:00"
    },
    "user_003": {
        "id": "user_003",
        "username": "analyst",
        "password_hash": hashlib.sha256("analyst123".encode()).hexdigest(),  # analyst123
        "role": "analyst",
        "email": "analyst@adas.com",
        "created_at": "2025-12-10T00:00:00"
    }
}

# Active sessions (token -> user_id)
_sessions = {}


@router.post("/auth/login")
async def login(request: LoginRequest):
    """
    User login
    
    Request body (JSON):
    - username: Username
    - password: Password
    
    Returns:
    - success: Boolean
    - token: JWT-like token for authentication
    - user: User information (without password)
    
    Test credentials:
    - admin / admin123 (admin role)
    - driver1 / driver123 (driver role)
    - analyst / analyst123 (analyst role)
    """
    # Find user by username
    user = None
    for u in _users.values():
        if u["username"] == request.username:
            user = u
            break
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )
    
    # Check password
    password_hash = hashlib.sha256(request.password.encode()).hexdigest()
    if password_hash != user["password_hash"]:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )
    
    # Generate token (dummy - in production use JWT)
    token = str(uuid.uuid4())
    
    # Store session
    _sessions[token] = {
        "user_id": user["id"],
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
    }
    
    # Return user info (without password)
    user_info = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "email": user.get("email")
    }
    
    return {
        "success": True,
        "token": token,
        "user": user_info,
        "expires_in": 86400  # 24 hours in seconds
    }


@router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """
    User logout
    
    Headers:
    - Authorization: Bearer {token}
    
    Invalidates the current session token
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header"
        )
    
    token = authorization.replace("Bearer ", "")
    
    if token not in _sessions:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    # Remove session
    _sessions.pop(token)
    
    return {
        "success": True,
        "message": "Logged out successfully"
    }


@router.get("/auth/me")
async def get_current_user(authorization: Optional[str] = Header(None)):
    """
    Get current authenticated user
    
    Headers:
    - Authorization: Bearer {token}
    
    Returns user information for the authenticated user
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header"
        )
    
    token = authorization.replace("Bearer ", "")
    
    if token not in _sessions:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    # Get user from session
    session = _sessions[token]
    user_id = session["user_id"]
    
    if user_id not in _users:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    
    user = _users[user_id]
    
    # Return user info (without password)
    user_info = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "email": user.get("email"),
        "created_at": user.get("created_at")
    }
    
    return {
        "success": True,
        "user": user_info
    }


@router.get("/users/list")
async def list_users(authorization: Optional[str] = Header(None)):
    """
    List all users (admin only)
    
    Headers:
    - Authorization: Bearer {token}
    
    Returns list of all users (without passwords)
    """
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header"
        )
    
    token = authorization.replace("Bearer ", "")
    
    if token not in _sessions:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    # Get user from session
    session = _sessions[token]
    user_id = session["user_id"]
    current_user = _users.get(user_id)
    
    # Check if admin
    if not current_user or current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    
    # Return all users (without passwords)
    users_list = []
    for user in _users.values():
        users_list.append({
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "email": user.get("email"),
            "created_at": user.get("created_at")
        })
    
    return {
        "success": True,
        "users": users_list,
        "total": len(users_list)
    }


@router.post("/users/create")
async def create_user(
    request: CreateUserRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Create a new user (admin only)
    
    Headers:
    - Authorization: Bearer {token}
    
    Request body (JSON):
    - username: Username (must be unique)
    - password: Password
    - role: User role (admin/driver/analyst)
    - email: Optional email address
    """
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header"
        )
    
    token = authorization.replace("Bearer ", "")
    
    if token not in _sessions:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    # Get user from session
    session = _sessions[token]
    user_id = session["user_id"]
    current_user = _users.get(user_id)
    
    # Check if admin
    if not current_user or current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    
    # Check if username exists
    for user in _users.values():
        if user["username"] == request.username:
            raise HTTPException(
                status_code=400,
                detail=f"Username '{request.username}' already exists"
            )
    
    # Validate role
    if request.role not in ["admin", "driver", "analyst", "viewer"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid role. Must be: admin, driver, analyst, or viewer"
        )
    
    # Create new user
    new_user_id = f"user_{str(uuid.uuid4())[:8]}"
    password_hash = hashlib.sha256(request.password.encode()).hexdigest()
    
    new_user = {
        "id": new_user_id,
        "username": request.username,
        "password_hash": password_hash,
        "role": request.role,
        "email": request.email,
        "created_at": datetime.now().isoformat()
    }
    
    _users[new_user_id] = new_user
    
    # Return user info (without password)
    user_info = {
        "id": new_user["id"],
        "username": new_user["username"],
        "role": new_user["role"],
        "email": new_user.get("email"),
        "created_at": new_user.get("created_at")
    }
    
    return {
        "success": True,
        "message": f"User '{request.username}' created successfully",
        "user": user_info
    }
