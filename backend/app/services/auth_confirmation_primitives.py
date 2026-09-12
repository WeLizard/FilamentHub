"""Shared cryptographic and session bindings for email-delivered proofs."""

import hashlib
import hmac
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import raise_error
from app.core.security import decode_access_token, token_auth_version_matches, token_fingerprint
from app.core.utils import normalize_email
from app.models.refresh_session import RefreshSession
from app.models.revoked_token import RevokedToken
from app.models.user import User


def as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def confirmation_digest(scope: str, purpose: str, value: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"{scope}:{purpose}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


def email_digest(scope: str, email: str) -> str:
    return confirmation_digest(scope, "email", normalize_email(email))


async def require_current_refresh_family(
    db: AsyncSession,
    *,
    request: Request,
    user: User,
    now: datetime,
    session_error: str,
    verified_email_error: str,
) -> str:
    authorization = request.headers.get("Authorization", "")
    token = authorization.split(" ", 1)[1] if authorization.lower().startswith("bearer ") else None
    if not token and settings.AUTH_WEB_MODE in {"cookie", "dual"}:
        token = request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
    payload = decode_access_token(token) if token else None
    sid = payload.get("sid") if payload else None
    if (
        not payload
        or not isinstance(sid, str)
        or not 1 <= len(sid) <= 43
        or payload.get("user_id") != user.id
        or payload.get("sub") != user.email
        or not token_auth_version_matches(payload, user.auth_version)
    ):
        raise_error(403, session_error)
    family = await db.scalar(
        select(RefreshSession)
        .where(RefreshSession.id == sid)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    revoked_access = await db.scalar(
        select(RevokedToken.id).where(RevokedToken.jti == token_fingerprint(token))
    )
    if (
        family is None
        or family.user_id != user.id
        or family.revoked_at is not None
        or as_utc(family.expires_at) <= now
        or revoked_access is not None
    ):
        raise_error(403, session_error)
    if not user.email_verified:
        raise_error(403, verified_email_error)
    return sid
