"""
JWT AUTHENTICATION AND RBAC MIDDLEWARE
=======================================
Phase 8: Production-grade authentication and authorization.

PURPOSE:
Secure all protected endpoints with JWT tokens and role-based access control.

FEATURES:
- JWT token generation and validation
- Password hashing with bcrypt
- Role-based access control (RBAC)
- Token expiration and refresh
- Protected route decorators

SECURITY:
- Tokens signed with SECRET_KEY
- Passwords hashed with bcrypt (cost factor 12)
- Token expiration: 24 hours
- Refresh token: 7 days

ROLES:
- admin: Full system access
- operator: Video processing and analysis
- viewer: Read-only access
- driver: Personal data only

Author: Senior ADAS Engineer
Date: 2025-12-26 (Phase 8)
"""

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = "adas-secret-key-change-in-production-2025"  # TODO: Move to environment variable
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Security scheme
security = HTTPBearer()


class UserRole(str, Enum):
    """User roles for RBAC."""
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    DRIVER = "driver"


class TokenData(BaseModel):
    """JWT token payload."""
    user_id: str
    username: str
    role: UserRole
    exp: datetime


class User(BaseModel):
    """User model."""
    id: str
    username: str
    email: Optional[str] = None
    role: UserRole
    is_active: bool = True
    created_at: datetime


class Token(BaseModel):
    """Authentication token response."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


def hash_password(password: str) -> str:
    """
    Hash password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password
    """
    # Convert password to bytes
    password_bytes = password.encode('utf-8')
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    # Return as string
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash.
    
    Args:
        plain_password: Plain text password
        hashed_password: Bcrypt hash
        
    Returns:
        True if password matches
    """
    # Convert to bytes
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    # Verify
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(
    user_id: str,
    username: str,
    role: UserRole,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token.
    
    Args:
        user_id: User ID
        username: Username
        role: User role
        expires_delta: Token lifetime (default: 24 hours)
        
    Returns:
        JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    expire = datetime.utcnow() + expires_delta
    
    payload = {
        "sub": user_id,
        "username": username,
        "role": role.value,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    }
    
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def create_refresh_token(user_id: str) -> str:
    """
    Create JWT refresh token.
    
    Args:
        user_id: User ID
        
    Returns:
        JWT refresh token string
    """
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    }
    
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def decode_token(token: str) -> TokenData:
    """
    Decode and validate JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        TokenData with user information
        
    Raises:
        HTTPException: If token invalid or expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        role: str = payload.get("role")
        exp: float = payload.get("exp")
        
        if user_id is None or username is None or role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing claims"
            )
        
        # Check token type
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        return TokenData(
            user_id=user_id,
            username=username,
            role=UserRole(role),
            exp=datetime.fromtimestamp(exp)
        )
        
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData:
    """
    Dependency to get current authenticated user.
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: TokenData = Depends(get_current_user)):
            return {"user": user.username}
    
    Args:
        credentials: HTTP Bearer token from Authorization header
        
    Returns:
        TokenData with user information
    """
    token = credentials.credentials
    return decode_token(token)


def require_role(allowed_roles: List[UserRole]):
    """
    Dependency factory for role-based access control.
    
    Usage:
        @router.delete("/admin/delete")
        async def admin_only(user: TokenData = Depends(require_role([UserRole.ADMIN]))):
            return {"message": "Admin action performed"}
    
    Args:
        allowed_roles: List of roles allowed to access the endpoint
        
    Returns:
        Dependency function that checks role
    """
    async def check_role(user: TokenData = Depends(get_current_user)) -> TokenData:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in allowed_roles]}"
            )
        return user
    
    return check_role


# Convenience role dependencies
async def require_admin(user: TokenData = Depends(get_current_user)) -> TokenData:
    """Require admin role."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


async def require_operator(user: TokenData = Depends(get_current_user)) -> TokenData:
    """Require operator or admin role."""
    if user.role not in [UserRole.ADMIN, UserRole.OPERATOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator access required"
        )
    return user


async def require_viewer(user: TokenData = Depends(get_current_user)) -> TokenData:
    """Require any authenticated user."""
    return user  # All roles can view


if __name__ == "__main__":
    # Test authentication system
    print("JWT Authentication & RBAC Test")
    print("=" * 50)
    
    # Test password hashing
    password = "test123"
    hashed = hash_password(password)
    print(f"Password: {password}")
    print(f"Hash: {hashed}")
    print(f"Verify: {verify_password(password, hashed)}")
    
    # Test token creation
    print("\nToken Creation:")
    token = create_access_token(
        user_id="user_001",
        username="admin",
        role=UserRole.ADMIN
    )
    print(f"Access Token: {token[:50]}...")
    
    # Test token decoding
    print("\nToken Decoding:")
    token_data = decode_token(token)
    print(f"User ID: {token_data.user_id}")
    print(f"Username: {token_data.username}")
    print(f"Role: {token_data.role}")
    print(f"Expires: {token_data.exp}")
    
    # Test refresh token
    refresh = create_refresh_token("user_001")
    print(f"\nRefresh Token: {refresh[:50]}...")
    
    print("\n✓ Authentication system working")
