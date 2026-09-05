"""Atomic account credential changes and durable recovery grants."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    decode_password_reset_token,
    generate_password_reset_token,
    token_auth_version_matches,
    token_fingerprint,
)
from app.models.audit_event import AuditAction, AuditReason
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.audit_service import record_audit_event
from app.services.refresh_session_service import revoke_all_refresh_sessions

PASSWORD_RESET_LIFETIME = timedelta(hours=1)


class InvalidPasswordResetError(Exception):
    """The supplied recovery grant cannot authorize a password replacement."""


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def token_data_for_user(user: User) -> dict[str, object]:
    """Claims shared by access and refresh tokens for one account state."""
    return {
        "sub": user.email,
        "user_id": user.id,
        "role": user.role.value,
        "auth_version": user.auth_version,
    }


async def issue_password_reset_grant(
    db: AsyncSession,
    *,
    user: User,
    now: datetime | None = None,
) -> str:
    """Persist a fingerprint before returning the corresponding reset token."""
    issued_at = _as_utc(now or datetime.now(timezone.utc))
    expires_at = issued_at + PASSWORD_RESET_LIFETIME
    token = generate_password_reset_token(
        user.id,
        user.email,
        auth_version=user.auth_version,
        expires_at=expires_at,
    )
    db.add(
        PasswordResetToken(
            grant_hash=token_fingerprint(token),
            user_id=user.id,
            expires_at=expires_at,
            created_at=issued_at,
        )
    )
    await db.flush()
    return token


async def lock_user_auth_state(db: AsyncSession, user_id: int) -> User | None:
    """Serialize every operation that can invalidate an account credential."""
    return await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def revoke_all_account_auth(
    db: AsyncSession,
    *,
    user: User,
    now: datetime | None = None,
) -> None:
    """Invalidate all user-session and recovery credentials in one transaction."""
    revoked_at = _as_utc(now or datetime.now(timezone.utc))
    user.auth_version += 1
    await revoke_all_refresh_sessions(db, user_id=user.id, now=revoked_at)
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.consumed_at.is_(None),
        )
        .values(consumed_at=revoked_at)
    )


async def replace_password_and_revoke_auth(
    db: AsyncSession,
    *,
    user: User,
    password_hash: str,
    now: datetime | None = None,
) -> None:
    """Replace a password and invalidate every credential minted before it."""
    user.password_hash = password_hash
    await revoke_all_account_auth(db, user=user, now=now)
    await db.flush()


async def reset_password_with_grant(
    db: AsyncSession,
    *,
    token: str,
    password_hash: str,
    now: datetime | None = None,
) -> User:
    """Consume one reset grant and invalidate every sibling grant and session."""
    reset_at = _as_utc(now or datetime.now(timezone.utc))
    payload = decode_password_reset_token(token)
    if payload is None:
        raise InvalidPasswordResetError

    user_id = payload.get("user_id")
    email = payload.get("email")
    if type(user_id) is not int or not isinstance(email, str):
        raise InvalidPasswordResetError

    user = await lock_user_auth_state(db, user_id)
    if (
        user is None
        or not user.active
        or user.email != email
        or not token_auth_version_matches(payload, user.auth_version)
    ):
        raise InvalidPasswordResetError

    grant = await db.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.grant_hash == token_fingerprint(token),
            PasswordResetToken.user_id == user.id,
        )
        .with_for_update()
    )
    if (
        grant is None
        or grant.consumed_at is not None
        or _as_utc(grant.expires_at) <= reset_at
    ):
        raise InvalidPasswordResetError

    await replace_password_and_revoke_auth(
        db,
        user=user,
        password_hash=password_hash,
        now=reset_at,
    )
    await record_audit_event(
        db,
        action=AuditAction.PASSWORD_RESET,
        actor_user_id=None,
        target_user_id=user.id,
        reason=AuditReason.RECOVERY_GRANT,
        occurred_at=reset_at,
    )
    return user
