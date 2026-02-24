"""FastAPI dependencies for authentication."""

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_COULD_NOT_VALIDATE,
    ERR_INVALID_API_KEY,
    ERR_NOT_ADMIN,
    ERR_NOT_BRAND_USER,
    ERR_USER_INACTIVE,
    ERR_USER_NOT_FOUND,
    raise_error,
)
from app.core.security import decode_access_token, verify_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.user import TokenData

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get current authenticated user from JWT token."""
    token = credentials.credentials
    token_preview = token[:20] + "..." if len(token) > 20 else token
    
    payload = decode_access_token(token)
    
    if payload is None:
        logger.warning("Failed to decode JWT token (preview: %s) - token is invalid, expired, or malformed", token_preview)
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_COULD_NOT_VALIDATE, headers={"WWW-Authenticate": "Bearer"})

    email: str | None = payload.get("sub")
    if email is None:
        logger.warning("JWT token payload missing 'sub' field (preview: %s)", token_preview)
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_COULD_NOT_VALIDATE, headers={"WWW-Authenticate": "Bearer"})
    
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if user is None:
        logger.warning("User not found for email: %s (from JWT token)", email)
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_USER_NOT_FOUND, headers={"WWW-Authenticate": "Bearer"})
    
    if not user.active:
        logger.warning("User account is inactive: %s (id: %d)", email, user.id)
        raise_error(status.HTTP_403_FORBIDDEN, ERR_USER_INACTIVE)
    
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current active user."""
    return current_user


async def get_current_active_user_optional(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Get current active user if authenticated, otherwise return None."""
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    
    if payload is None:
        return None
    
    email: str | None = payload.get("sub")
    if email is None:
        return None
    
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if user is None or not user.active:
        return None
    
    return user


async def get_current_brand_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current user linked to a brand (by brand_id, not role)."""
    # Проверяем наличие brand_id, а не роль (админ может быть привязан к бренду, но оставаться админом)
    if not current_user.brand_id:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_NOT_BRAND_USER)
    return current_user


async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current user with admin role."""
    if current_user.role != UserRole.ADMIN:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_NOT_ADMIN)
    return current_user


async def get_user_by_api_key(
    api_key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Get user by API key (for OrcaSlicer integration)."""
    result = await db.execute(select(User).where(User.api_key == api_key))
    user = result.scalar_one_or_none()
    return user


async def get_current_user_by_api_key(
    api_key: Annotated[str, Header(alias="X-API-Key")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Validate API key from header and return active user for OrcaSlicer integration."""
    user = await get_user_by_api_key(api_key, db)
    if user is None:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_API_KEY)
    if not user.active:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_USER_INACTIVE)
    return user

