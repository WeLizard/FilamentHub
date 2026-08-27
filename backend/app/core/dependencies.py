"""FastAPI dependencies for authentication."""

import logging
from typing import Annotated

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_AUTH_REQUIRED,
    ERR_CALCULATOR_ACCESS_REQUIRED,
    ERR_COULD_NOT_VALIDATE,
    ERR_EMAIL_NOT_VERIFIED,
    ERR_LEGAL_ACCEPTANCE_REQUIRED,
    ERR_NOT_ADMIN,
    ERR_NOT_BRAND_USER,
    ERR_USER_INACTIVE,
    ERR_USER_NOT_FOUND,
    raise_error,
)
from app.core.security import (
    decode_access_token,
    decode_plugin_token,
    get_unverified_token_type,
    token_fingerprint,
)
from app.db.session import get_db
from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole
from app.services.legal_acceptance_service import requires_current_legal_acceptance

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


async def get_current_user_for_legal_onboarding(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Authenticate an active account without requiring legal onboarding.

    This dependency is intentionally restricted to the onboarding allow-list:
    current-user information, legal acceptance, and logout.
    """
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

    result = await db.execute(
        select(User).options(selectinload(User.subscription)).where(User.email == email)
    )
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning("Token names an account that no longer exists")
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_USER_NOT_FOUND, headers={"WWW-Authenticate": "Bearer"})

    if not user.active:
        logger.warning("Inactive account tried to authenticate: user_id=%d", user.id)
        raise_error(status.HTTP_403_FORBIDDEN, ERR_USER_INACTIVE)

    return user


async def get_current_user(
    current_user: Annotated[User, Depends(get_current_user_for_legal_onboarding)],
) -> User:
    """Get an authenticated user who accepted the current legal documents."""
    if requires_current_legal_acceptance(current_user):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_LEGAL_ACCEPTANCE_REQUIRED)
    return current_user


async def _get_current_user_or_plugin_scope(
    *,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
    required_scope: str,
) -> User:
    """Authenticate a normal web session or a narrowly scoped plugin token."""
    token: str | None = None
    using_cookie_auth = False
    if credentials is not None and credentials.credentials:
        token = credentials.credentials
    elif _cookie_auth_enabled():
        token = request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
        using_cookie_auth = bool(token)

    if not token:
        raise_error(
            status.HTTP_401_UNAUTHORIZED,
            ERR_AUTH_REQUIRED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if using_cookie_auth:
        _validate_cookie_csrf(request)

    token_type = get_unverified_token_type(token)
    if token_type == "access":
        payload = decode_access_token(token)
    elif token_type == "plugin" and not using_cookie_auth:
        payload = decode_plugin_token(token)
        scopes = payload.get("scopes", []) if payload else []
        if payload is not None and required_scope not in scopes:
            raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    else:
        payload = None

    if payload is None or await is_token_revoked(token, db):
        raise_error(
            status.HTTP_401_UNAUTHORIZED,
            ERR_COULD_NOT_VALIDATE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    email = payload.get("sub")
    if not isinstance(user_id, int) and not isinstance(email, str):
        raise_error(
            status.HTTP_401_UNAUTHORIZED,
            ERR_COULD_NOT_VALIDATE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    query = select(User).options(selectinload(User.subscription))
    query = (
        query.where(User.id == user_id)
        if isinstance(user_id, int)
        else query.where(User.email == email)
    )
    user = (await db.execute(query)).scalar_one_or_none()
    if user is None:
        raise_error(
            status.HTTP_401_UNAUTHORIZED,
            ERR_USER_NOT_FOUND,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.active:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_USER_INACTIVE)
    if requires_current_legal_acceptance(user):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_LEGAL_ACCEPTANCE_REQUIRED)
    return user


async def require_preset_read(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    return await _get_current_user_or_plugin_scope(
        request=request,
        credentials=credentials,
        db=db,
        required_scope="presets:read",
    )


async def require_preset_write(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    return await _get_current_user_or_plugin_scope(
        request=request,
        credentials=credentials,
        db=db,
        required_scope="presets:write",
    )


async def require_sync_report(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Allow a browser session or the plugin to report device-scoped sync facts."""
    return await _get_current_user_or_plugin_scope(
        request=request,
        credentials=credentials,
        db=db,
        required_scope="sync:report",
    )


async def require_printer_bundle_read(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Allow a browser session or the plugin to read one owned printer bundle."""
    return await _get_current_user_or_plugin_scope(
        request=request,
        credentials=credentials,
        db=db,
        required_scope="printer-bundles:read",
    )


async def require_material_topology_read(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Read the owned printer/slot binding needed by a local adapter."""
    return await _get_current_user_or_plugin_scope(
        request=request,
        credentials=credentials,
        db=db,
        required_scope="material-topology:read",
    )


async def require_material_topology_report(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Accept an owned material-topology observation from a local adapter."""
    return await _get_current_user_or_plugin_scope(
        request=request,
        credentials=credentials,
        db=db,
        required_scope="material-topology:report",
    )


async def require_material_topology_write(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Apply a user-confirmed material assignment through the local plugin."""
    return await _get_current_user_or_plugin_scope(
        request=request,
        credentials=credentials,
        db=db,
        required_scope="material-topology:write",
    )


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Compatibility dependency for endpoints requiring an active user."""
    return current_user


async def get_current_verified_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """An action that reaches other people needs a confirmed address.

    Reading and syncing stay open to everyone: confirmation guards what affects
    others — a brand claim nobody could answer, a rating on someone's material,
    a trial that a throwaway mailbox could take again and again.
    """
    from app.services.account_trust_service import account_is_trusted

    if not account_is_trusted(current_user):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_EMAIL_NOT_VERIFIED)
    return current_user


async def get_current_active_user_optional(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Get current active user if authenticated, otherwise return None."""
    authorization = request.headers.get("Authorization")
    token: str | None = None
    using_cookie_auth = False

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif _cookie_auth_enabled():
        token = request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
        using_cookie_auth = bool(token)

    if not token:
        return None

    # Cookie-authenticated mutating requests must carry a valid CSRF token, same
    # as in get_current_user. A real anonymous caller has no cookie and returns
    # above; only a forged cross-site request (cookie present, header missing)
    # is rejected here.
    if using_cookie_auth:
        _validate_cookie_csrf(request)

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

    if (
        user is None
        or not user.active
        or requires_current_legal_acceptance(user)
    ):
        return None

    return user


async def get_current_brand_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get a user with an authorized active brand workspace."""
    if not current_user.brand_id:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_NOT_BRAND_USER)
    from app.services.organization_access import get_active_workspace_membership

    membership = await get_active_workspace_membership(
        db, current_user, current_user.brand_id
    )
    if membership is None:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_NOT_BRAND_USER)
    return current_user


async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Get current user with admin role."""
    if current_user.role != UserRole.ADMIN:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_NOT_ADMIN)
    return current_user


async def require_calculator_access(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Require effective calculator (Pro) access — see subscription_service.pro_active."""
    from app.services.subscription_service import pro_active

    if not pro_active(current_user):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_CALCULATOR_ACCESS_REQUIRED)
    return current_user


# Account-level API-key dependencies were retired; device credentials remain
# scoped to their adapter endpoints.
