from fastapi import APIRouter, Depends
from typing import Optional
from pydantic import BaseModel

from app.core.supabase_auth import get_current_user, get_optional_user, SupabaseUser

router = APIRouter(prefix="/api", tags=["authentication"])


# Response models
class UserResponse(BaseModel):
    """User information response with Hybrid ID."""
    id: int  # Integer ID from database (for legacy controllers)
    auth_id: str  # UUID from Supabase Auth
    email: Optional[str] = None
    role: Optional[str] = None


class AuthMeResponse(BaseModel):
    """Authentication status response."""
    success: bool
    user: UserResponse


@router.get("/auth/me", response_model=AuthMeResponse)
async def get_current_user_info(user: SupabaseUser = Depends(get_current_user)):
    """
    Get current authenticated user information with Hybrid ID.
    
    **Authentication:** Required (Bearer token)
    
    **Headers:**
    - Authorization: Bearer {supabase_jwt_token}
    
    **Returns:**
    - success: True if authenticated
    - user: User information from Supabase JWT + Database
        - id: Integer ID from database (for legacy controllers)
        - auth_id: UUID from Supabase Auth
        - email: User email address
        - role: User role from database
    
    **Hybrid ID System:**
    This endpoint bridges Supabase Auth (UUID) with legacy integer IDs.
    The integer `id` can be used directly in existing controllers without changes.
    
    **Example:**
    ```bash
    curl -X GET "http://localhost:52000/api/auth/me" \\
      -H "Authorization: Bearer YOUR_SUPABASE_JWT_TOKEN"
    ```
    
    **Response:**
    ```json
    {
      "success": true,
      "user": {
        "id": 123,
        "auth_id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "user@example.com",
        "role": "admin"
      }
    }
    ```
    
    **Errors:**
    - 401: Invalid or expired token
    - 401: User not synced with database
    - 503: Database unavailable
    """
    return AuthMeResponse(
        success=True,
        user=UserResponse(
            id=user.id,  # Integer ID from database
            auth_id=user.user_id,  # UUID from Supabase
            email=user.email,
            role=user.role
        )
    )


@router.get("/auth/status")
async def check_auth_status(user: Optional[SupabaseUser] = Depends(get_optional_user)):
    """
    Check authentication status without requiring authentication.
    
    **Authentication:** Optional
    
    **Headers:**
    - Authorization: Bearer {supabase_jwt_token} (optional)
    
    **Returns:**
    - authenticated: True if valid token provided, False otherwise
    - user: User information if authenticated (with Hybrid ID), null otherwise
    
    **Use case:**
    Use this endpoint to check if a user is authenticated without
    triggering a 401 error for unauthenticated requests.
    
    **Example:**
    ```bash
    # With token
    curl -X GET "http://localhost:52000/api/auth/status" \\
      -H "Authorization: Bearer YOUR_SUPABASE_JWT_TOKEN"
    
    # Without token
    curl -X GET "http://localhost:52000/api/auth/status"
    ```
    
    **Response (authenticated):**
    ```json
    {
      "authenticated": true,
      "user": {
        "id": 123,
        "auth_id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "user@example.com",
        "role": "admin"
      }
    }
    ```
    
    **Response (not authenticated):**
    ```json
    {
      "authenticated": false,
      "user": null
    }
    ```
    """
    if user:
        return {
            "authenticated": True,
            "user": {
                "id": user.id,  # Integer ID
                "auth_id": user.user_id,  # UUID
                "email": user.email,
                "role": user.role
            }
        }
    else:
        return {
            "authenticated": False,
            "user": None
        }


# Example protected endpoint demonstrating integer ID usage
@router.get("/auth/protected")
async def protected_example(user: SupabaseUser = Depends(get_current_user)):
    """
    Example protected endpoint demonstrating Hybrid ID usage.
    
    **Authentication:** Required (Bearer token)
    
    **Headers:**
    - Authorization: Bearer {supabase_jwt_token}
    
    **Returns:**
    Personalized message with both integer ID and UUID for demonstration.
    
    **Legacy Controller Compatibility:**
    Use `user.id` (integer) in your existing database queries and
    foreign key relationships without any code changes.
    
    **Example:**
    ```python
    # In your legacy controller
    @router.get("/videos/my-uploads")
    async def get_my_videos(user: SupabaseUser = Depends(get_current_user)):
        # user.id is the integer ID - works with existing foreign keys
        videos = await db.query(Video).filter(Video.uploader_id == user.id).all()
        return videos
    ```
    
    **Example:**
    ```bash
    curl -X GET "http://localhost:52000/api/auth/protected" \\
      -H "Authorization: Bearer YOUR_SUPABASE_JWT_TOKEN"
    ```
    """
    return {
        "message": f"Hello {user.email or f'User {user.id}'}! This is a protected endpoint.",
        "hybrid_id": {
            "database_id": user.id,  # Use this for legacy controllers
            "supabase_auth_id": user.user_id,  # UUID from Supabase
        },
        "user_info": {
            "id": user.id,
            "auth_id": user.user_id,
            "email": user.email,
            "role": user.role
        },
        "metadata": {
            "issued_at": user.metadata.get("iat"),
            "expires_at": user.metadata.get("exp")
        }
    }
