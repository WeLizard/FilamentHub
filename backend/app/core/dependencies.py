"""FastAPI dependencies for authentication."""

import logging
from typing import Annotated

from fastapi import Depends, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_AUTH_REQUIRED,
    ERR_COULD_NOT_VALIDATE,
    ERR_INVALID_API_KEY,
    ERR_NOT_ADMIN,
    ERR_NOT_BRAND_USER,
    ERR_USER_INACTIVE,
    ERR_USER_NOT_FOUND,
    raise_error,
)
from app.core.security import decode_access_token, token_fingerprint
from app.db.session import get_db
from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole
from app.schemas.user import TokenData

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _cookie_auth_enabled() -> bool:
    return settings.AUTH_WEB_MODE in {"cookie", "dual"}


def _validate_cookie_csrf(request: Request) -> None:
    """Enforce CSRF only for cookie-authenticated mutating requests."""
    if request.method.upper() not in _STATE_CHANGING_METHODS:
        return

    csrf_cookie = request.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
    csrf_header = request.headers.get(settings.AUTH_CSRF_HEADER_NAME)

    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)


async def is_token_revoked(token: str, db: AsyncSession) -> bool:
    """Check whether JWT token was explicitly revoked via logout."""
    fingerprint = token_fingerprint(token)
    result = await db.execute(
        select(RevokedToken.id).where(RevokedToken.jti == fingerprint)
    )
    return result.scalar_one_or_none() is not None


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get current authenticated user from JWT token."""
    token: str | None = None
    using_cookie_auth = False

    if credentials is not None and credentials.credentials:
        token = credentials.credentials
    elif _cookie_auth_enabled():
        token = request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
        using_cookie_auth = bool(token)

    if not token:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_AUTH_REQUIRED, headers={"WWW-Authenticate": "Bearer"})

    if using_cookie_auth:
        _validate_cookie_csrf(request)

    token_preview = token[:20] + "..." if len(token) > 20 else token
    
    payload = decode_access_token(token)
    
    if payload is None:
        logger.warning("Failed to decode JWT token (preview: %s) - token is invalid, expired, or malformed", token_preview)
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_COULD_NOT_VALIDATE, headers={"WWW-Authenticate": "Bearer"})

    if await is_token_revoked(token, db):
        logger.info("JWT token is revoked (preview: %s)", token_preview)
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
    token: str | None = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif _cookie_auth_enabled():
        token = request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)

    if not token:
        return None

    payload = decode_access_token(token)
    
    if payload is None:
        return None

    if await is_token_revoked(token, db):
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
