"""
User Repository
===============
Data access layer for users.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from .base import BaseRepository
from ..models.user import User, UserRole


class UserRepository(BaseRepository[User]):
    """Repository for user operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        role: UserRole,
        **kwargs
    ) -> User:
        """Create a new user"""
        return await self.create(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=1,
            **kwargs
        )
    
    async def update_last_login(self, user_id: int) -> Optional[User]:
        """Update user's last login timestamp"""
        return await self.update(user_id, last_login=datetime.utcnow())
    
    async def deactivate_user(self, user_id: int) -> Optional[User]:
        """Deactivate a user"""
        return await self.update(user_id, is_active=0)
    
    async def activate_user(self, user_id: int) -> Optional[User]:
        """Activate a user"""
        return await self.update(user_id, is_active=1)
