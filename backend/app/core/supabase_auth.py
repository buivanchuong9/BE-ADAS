"""
Supabase JWT Authentication Module - Hybrid ID System
======================================================
Verifies Supabase JWT tokens using RS256 signature verification
and bridges Supabase Auth UUIDs with legacy integer IDs.

PURPOSE:
- Verify JWT tokens issued by Supabase Auth
- Extract UUID from 'sub' claim
- Query database to get integer ID for legacy compatibility
- Provide FastAPI dependencies for protected routes

HYBRID ID SYSTEM:
- Supabase Auth uses UUID (auth_id)
- Legacy database uses integer (id)
- This module bridges both systems seamlessly

SECURITY:
- RS256 signature verification using JWKS
- No API keys required for JWT verification
- Validates aud claim equals "authenticated"
- Checks token expiration

Author: Senior ADAS Engineer
Date: 2026-01-04
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, jwk, JWTError
from typing import Optional, Dict, Any
import httpx
import logging
from functools import lru_cache
from datetime import datetime
import asyncio

from app.core.config import settings

# Initialize Supabase client for database queries
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None  # Type placeholder when supabase not installed

logger = logging.getLogger(__name__)

if not SUPABASE_AVAILABLE:
    logger.warning("supabase-py not installed. Database lookups will be disabled.")

# Security scheme
security = HTTPBearer()


class SupabaseUser:
    """Represents an authenticated Supabase user with hybrid ID system."""
    
    def __init__(
        self, 
        id: int,  # Integer ID from database (for legacy compatibility)
        user_id: str,  # UUID from Supabase (auth_id)
        email: Optional[str] = None,
        role: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.id = id  # Primary: Integer ID for legacy controllers
        self.user_id = user_id  # Secondary: UUID from Supabase Auth
        self.email = email
        self.role = role
        self.metadata = metadata or {}
    
    def __repr__(self):
        return f"SupabaseUser(id={self.id}, user_id={self.user_id}, email={self.email}, role={self.role})"


class JWKSClient:
    """Client for fetching and caching JWKS keys from Supabase."""
    
    def __init__(self, jwks_url: str):
        self.jwks_url = jwks_url
        self._keys_cache: Optional[Dict[str, Any]] = None
    
    async def get_signing_keys(self) -> Dict[str, Any]:
        """
        Fetch JWKS keys from Supabase.
        
        Returns:
            Dictionary of signing keys indexed by kid (key ID)
        """
        if self._keys_cache is not None:
            return self._keys_cache
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.jwks_url, timeout=10.0)
                response.raise_for_status()
                jwks_data = response.json()
            
            # Parse keys
            keys = {}
            for key_data in jwks_data.get("keys", []):
                kid = key_data.get("kid")
                if kid:
                    keys[kid] = key_data
            
            # Cache the keys
            self._keys_cache = keys
            logger.info(f"Fetched {len(keys)} JWKS keys from Supabase")
            
            return keys
            
        except Exception as e:
            logger.error(f"Failed to fetch JWKS keys: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to verify tokens at this time"
            )


@lru_cache()
def get_jwks_client() -> JWKSClient:
    """Get singleton JWKS client instance."""
    return JWKSClient(settings.SUPABASE_JWKS_URL)


@lru_cache()
def get_supabase_client():
    """
    Get Supabase client for database queries.
    
    Returns:
        Supabase client or None if not configured
    """
    if not SUPABASE_AVAILABLE:
        logger.warning("Supabase client not available - install supabase-py")
        return None
    
    if not settings.SUPABASE_ANON_KEY:
        logger.warning("SUPABASE_ANON_KEY not configured - database lookups disabled")
        return None
    
    try:
        client = create_client(
            settings.SUPABASE_PROJECT_URL,
            settings.SUPABASE_ANON_KEY
        )
        logger.info("Supabase client initialized successfully")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None


async def get_user_from_database(auth_id: str, retry_count: int = 3) -> Optional[Dict[str, Any]]:
    """
    Query database to get user by auth_id (UUID).
    
    Handles cases where database trigger hasn't finished creating the user yet
    by implementing retry logic with exponential backoff.
    
    Args:
        auth_id: UUID from Supabase JWT
        retry_count: Number of retries for delayed triggers
        
    Returns:
        Dictionary with {id, role} or None if not found
    """
    supabase = get_supabase_client()
    
    if not supabase:
        logger.error("Supabase client not available for database lookup")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database lookup unavailable"
        )
    
    for attempt in range(retry_count):
        try:
            # Query users table for the auth_id
            response = supabase.table("users").select("id, role").eq("auth_id", auth_id).execute()
            
            if response.data and len(response.data) > 0:
                user_data = response.data[0]
                logger.info(f"Found user in database: id={user_data.get('id')}, auth_id={auth_id}")
                return user_data
            
            # User not found, might be delayed trigger
            if attempt < retry_count - 1:
                wait_time = 0.5 * (2 ** attempt)  # Exponential backoff: 0.5s, 1s, 2s
                logger.warning(
                    f"User not found for auth_id={auth_id}, "
                    f"retrying in {wait_time}s (attempt {attempt + 1}/{retry_count})"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"User not found after {retry_count} attempts: auth_id={auth_id}")
                return None
                
        except Exception as e:
            logger.error(f"Database query error (attempt {attempt + 1}): {e}")
            if attempt == retry_count - 1:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Database unavailable"
                )
            await asyncio.sleep(0.5 * (2 ** attempt))
    
    return None


async def verify_supabase_token(token: str) -> SupabaseUser:
    """
    Verify Supabase JWT token using RS256 signature verification
    and retrieve integer ID from database.
    
    HYBRID ID FLOW:
    1. Verify JWT signature (RS256)
    2. Extract UUID from 'sub' claim
    3. Query database: SELECT id, role FROM users WHERE auth_id = <uuid>
    4. Return SupabaseUser with both integer ID and UUID
    
    Args:
        token: JWT token string from Authorization header
        
    Returns:
        SupabaseUser object with integer id and UUID user_id
        
    Raises:
        HTTPException: If token is invalid, expired, or user not found in database
    """
    try:
        # Decode header to get the key ID (kid)
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing key ID"
            )
        
        # Get signing keys from JWKS
        jwks_client = get_jwks_client()
        signing_keys = await jwks_client.get_signing_keys()
        
        if kid not in signing_keys:
            # Clear cache and retry once
            jwks_client._keys_cache = None
            signing_keys = await jwks_client.get_signing_keys()
            
            if kid not in signing_keys:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: unknown key ID"
                )
        
        # Get the public key
        key_data = signing_keys[kid]
        public_key = jwk.construct(key_data)
        
        # Verify and decode the token
        payload = jwt.decode(
            token,
            public_key.to_pem().decode('utf-8'),
            algorithms=[settings.SUPABASE_JWT_ALGORITHM],
            audience=settings.SUPABASE_JWT_AUDIENCE,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
            }
        )
        
        # Extract UUID from token
        auth_id = payload.get("sub")  # UUID from Supabase
        email = payload.get("email")
        
        if not auth_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        # Query database to get integer ID
        user_data = await get_user_from_database(auth_id, retry_count=3)
        
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not synced with database. Please contact administrator."
            )
        
        # Extract metadata from token
        metadata = {
            "aud": payload.get("aud"),
            "exp": payload.get("exp"),
            "iat": payload.get("iat"),
        }
        
        logger.info(
            f"Successfully verified token: id={user_data['id']}, "
            f"auth_id={auth_id}, email={email}"
        )
        
        return SupabaseUser(
            id=user_data["id"],  # Integer ID from database
            user_id=auth_id,  # UUID from Supabase
            email=email,
            role=user_data.get("role"),
            metadata=metadata
        )
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token verification failed: token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTClaimsError as e:
        logger.warning(f"Token verification failed: invalid claims - {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims"
        )
    except JWTError as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    except HTTPException:
        # Re-raise HTTP exceptions (from database lookup)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token verification error"
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> SupabaseUser:
    """
    FastAPI dependency to get current authenticated user from Supabase JWT.
    
    Returns user with HYBRID ID:
    - user.id: Integer ID (for legacy controllers)
    - user.user_id: UUID (from Supabase Auth)
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: SupabaseUser = Depends(get_current_user)):
            # Use integer ID for database queries
            return {"id": user.id, "auth_id": user.user_id}
    
    Args:
        credentials: HTTP Bearer token from Authorization header
        
    Returns:
        SupabaseUser object with integer id and UUID user_id
        
    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials
    return await verify_supabase_token(token)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[SupabaseUser]:
    """
    FastAPI dependency to get current user if authenticated, None otherwise.
    
    Useful for endpoints that have different behavior for authenticated vs anonymous users.
    
    Args:
        credentials: Optional HTTP Bearer token
        
    Returns:
        SupabaseUser if authenticated, None otherwise
    """
    if credentials is None:
        return None
    
    try:
        token = credentials.credentials
        return await verify_supabase_token(token)
    except HTTPException:
        return None
