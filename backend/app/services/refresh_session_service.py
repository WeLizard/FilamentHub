"""Rotation, reuse containment, and retention for refresh-token sessions."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.security import create_refresh_token, token_fingerprint
from app.models.refresh_session import RefreshSession
from app.models.revoked_token import RevokedToken

logger = logging.getLogger(__name__)

REFRESH_RETRY_GRACE_SECONDS = 10
AUTH_STATE_SWEEP_INTERVAL_SECONDS = 60 * 60
AUTH_STATE_CLEANUP_BATCH_SIZE = 200
TOKEN_CLOCK_SKEW_SECONDS = 60


class InvalidRefreshSessionError(Exception):
    """The refresh token cannot continue its claimed server-side session."""


class RefreshTokenReuseError(InvalidRefreshSessionError):
    """A rotated token was replayed outside the bounded retry window."""


@dataclass(frozen=True)
class AuthCleanupResult:
    revoked_tokens: int
    refresh_sessions: int


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _payload_expiry(payload: dict) -> datetime:
    try:
        expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise InvalidRefreshSessionError from exc
    return expires_at


def _subject_claims(payload: dict) -> dict[str, object]:
    """Keep the signed identity stable so an idempotent retry is byte-identical."""
    claims: dict[str, object] = {}
    for name in ("sub", "user_id", "role"):
        value = payload.get(name)
        if value is not None:
            claims[name] = value
    return claims


def _derived_value(label: str, value: str) -> str:
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"{label}:{value}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _legacy_session_id(refresh_token: str) -> str:
    return _derived_value("legacy-refresh-session", token_fingerprint(refresh_token))


def _successor_token_id(refresh_token: str) -> str:
    return _derived_value("refresh-successor", token_fingerprint(refresh_token))


def _session_id(payload: dict, refresh_token: str) -> tuple[str, bool]:
    claimed = payload.get("sid")
    if claimed is None:
        return _legacy_session_id(refresh_token), True
    if not isinstance(claimed, str) or not (1 <= len(claimed) <= 43):
        raise InvalidRefreshSessionError
    return claimed, False


def _successor_token(refresh_token: str, payload: dict, session_id: str) -> str:
    return create_refresh_token(
        _subject_claims(payload),
        expires_at=_payload_expiry(payload),
        session_id=session_id,
        token_id=_successor_token_id(refresh_token),
    )


async def issue_refresh_session(
    db: AsyncSession,
    *,
    user_id: int,
    token_data: dict[str, object],
    now: datetime | None = None,
) -> str:
    """Issue a distinct fixed-lifetime refresh family for one login."""
    issued_at = _as_utc(now or datetime.now(timezone.utc))
    expires_at = issued_at + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session_id = secrets.token_urlsafe(24)
    token = create_refresh_token(
        token_data,
        expires_at=expires_at,
        session_id=session_id,
        token_id=secrets.token_urlsafe(24),
    )
    db.add(
        RefreshSession(
            id=session_id,
            user_id=user_id,
            current_token_fingerprint=token_fingerprint(token),
            expires_at=expires_at,
            rotated_at=issued_at,
            created_at=issued_at,
        )
    )
    await db.flush()
    return token


async def rotate_refresh_session(
    db: AsyncSession,
    *,
    refresh_token: str,
    payload: dict,
    user_id: int,
    now: datetime | None = None,
) -> str:
    """Consume one token and return its deterministic, fixed-expiry successor."""
    rotated_at = _as_utc(now or datetime.now(timezone.utc))
    expires_at = _payload_expiry(payload)
    if expires_at <= rotated_at:
        raise InvalidRefreshSessionError

    session_id, is_legacy = _session_id(payload, refresh_token)
    presented_fingerprint = token_fingerprint(refresh_token)
    successor = _successor_token(refresh_token, payload, session_id)
    successor_fingerprint = token_fingerprint(successor)

    session = await db.scalar(
        select(RefreshSession)
        .where(RefreshSession.id == session_id)
        .with_for_update()
    )

    if session is None and is_legacy:
        candidate = RefreshSession(
            id=session_id,
            user_id=user_id,
            current_token_fingerprint=successor_fingerprint,
            previous_token_fingerprint=presented_fingerprint,
            expires_at=expires_at,
            rotated_at=rotated_at,
            created_at=rotated_at,
        )
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
        except IntegrityError:
            # Another worker upgraded the same legacy token first.  Its commit
            # resolves the unique-key wait; then the normal retry path decides.
            session = await db.scalar(
                select(RefreshSession)
                .where(RefreshSession.id == session_id)
                .with_for_update()
            )
        else:
            await db.commit()
            return successor

    if session is None or session.user_id != user_id:
        raise InvalidRefreshSessionError

    session_expiry = _as_utc(session.expires_at)
    if session.revoked_at is not None or session_expiry <= rotated_at:
        raise InvalidRefreshSessionError

    last_rotation = _as_utc(session.rotated_at)
    inside_retry_window = rotated_at - last_rotation <= timedelta(
        seconds=REFRESH_RETRY_GRACE_SECONDS
    )

    if presented_fingerprint == session.current_token_fingerprint:
        # Once a predecessor has been consumed, keep the returned successor
        # stable for the whole retry window.  Otherwise two tabs can advance
        # T0 -> T1 -> T2 before a delayed, legitimate T0 retry arrives; with
        # only one predecessor slot that retry would look like token theft and
        # revoke the family.  Returning the current token still renews the
        # access token while bounding refresh-token reuse to this short window.
        if session.previous_token_fingerprint is not None and inside_retry_window:
            return refresh_token
        session.previous_token_fingerprint = presented_fingerprint
        session.current_token_fingerprint = successor_fingerprint
        session.rotated_at = rotated_at
        await db.commit()
        return successor

    is_idempotent_retry = (
        presented_fingerprint == session.previous_token_fingerprint
        and successor_fingerprint == session.current_token_fingerprint
        and inside_retry_window
    )
    if is_idempotent_retry:
        return successor

    session.revoked_at = rotated_at
    await db.commit()
    logger.warning(
        "Refresh-token reuse revoked session family: user_id=%s session_id=%s",
        user_id,
        session_id,
    )
    raise RefreshTokenReuseError


async def revoke_refresh_session(
    db: AsyncSession,
    *,
    refresh_token: str,
    payload: dict,
    user_id: int,
    now: datetime | None = None,
) -> bool:
    """Revoke one refresh family, including when given its legacy predecessor."""
    revoked_at = _as_utc(now or datetime.now(timezone.utc))
    session_id, _is_legacy = _session_id(payload, refresh_token)
    session = await db.scalar(
        select(RefreshSession)
        .where(RefreshSession.id == session_id)
        .with_for_update()
    )
    if session is None:
        return False
    if session.user_id != user_id:
        raise InvalidRefreshSessionError
    if session.revoked_at is None:
        session.revoked_at = revoked_at
        await db.commit()
    return True


async def cleanup_expired_auth_state(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    batch_size: int = AUTH_STATE_CLEANUP_BATCH_SIZE,
) -> AuthCleanupResult:
    """Delete at most one bounded batch from each expired auth-state table."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    cutoff = _as_utc(now or datetime.now(timezone.utc)) - timedelta(
        seconds=TOKEN_CLOCK_SKEW_SECONDS
    )
    revoked_ids = (
        select(RevokedToken.id)
        .where(RevokedToken.expires_at < cutoff)
        .order_by(RevokedToken.expires_at, RevokedToken.id)
        .limit(batch_size)
    )
    refresh_ids = (
        select(RefreshSession.id)
        .where(RefreshSession.expires_at < cutoff)
        .order_by(RefreshSession.expires_at, RefreshSession.id)
        .limit(batch_size)
    )
    revoked_result = await db.execute(
        delete(RevokedToken).where(RevokedToken.id.in_(revoked_ids))
    )
    refresh_result = await db.execute(
        delete(RefreshSession).where(RefreshSession.id.in_(refresh_ids))
    )
    return AuthCleanupResult(
        revoked_tokens=max(revoked_result.rowcount or 0, 0),
        refresh_sessions=max(refresh_result.rowcount or 0, 0),
    )


async def run_auth_state_sweeper(
    session_factory: async_sessionmaker[AsyncSession],
    interval_seconds: float = AUTH_STATE_SWEEP_INTERVAL_SECONDS,
) -> None:
    """Periodically remove bounded expired auth state without delaying startup."""
    while True:
        try:
            async with session_factory() as db:
                removed = await cleanup_expired_auth_state(db)
                await db.commit()
            if removed.revoked_tokens or removed.refresh_sessions:
                logger.info(
                    "Removed expired auth state: revoked_tokens=%s refresh_sessions=%s",
                    removed.revoked_tokens,
                    removed.refresh_sessions,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Failed to sweep expired auth state", exc_info=True)
        await asyncio.sleep(interval_seconds)
