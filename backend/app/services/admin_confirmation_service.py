"""One-time email confirmation, bound to an administrator's exact operation."""

import asyncio
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_ADMIN_CONFIRMATION_ATTEMPTS_EXCEEDED,
    ERR_ADMIN_CONFIRMATION_DELIVERY_FAILED,
    ERR_ADMIN_CONFIRMATION_EMAIL_REQUIRED,
    ERR_ADMIN_CONFIRMATION_EXPIRED,
    ERR_ADMIN_CONFIRMATION_INVALID,
    ERR_ADMIN_CONFIRMATION_RATE_LIMITED,
    ERR_ADMIN_CONFIRMATION_REQUIRED,
    ERR_ADMIN_CONFIRMATION_SESSION_REQUIRED,
    ERR_USER_NOT_FOUND,
    raise_error,
)
from app.core.i18n import resolve_language
from app.core.security import decode_access_token, token_auth_version_matches, token_fingerprint
from app.core.utils import normalize_email
from app.models.admin_action_confirmation import AdminActionConfirmation, AdminConfirmationAction
from app.models.refresh_session import RefreshSession
from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole
from app.schemas.admin_confirmation import (
    AdminConfirmationProof,
    AdminConfirmationRequest,
    AdminConfirmationResponse,
)
from app.services.email_service import send_admin_confirmation_email

CONFIRMATION_LIFETIME = timedelta(minutes=10)
EMAIL_CHANGE_LIFETIME = timedelta(hours=24)
MAX_CONFIRMATION_ATTEMPTS = 5


def as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def confirmation_digest(purpose: str, value: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"admin-confirmation:{purpose}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


def email_digest(email: str) -> str:
    return confirmation_digest("email", normalize_email(email))


def parameters_digest(
    action: AdminConfirmationAction, *, delete_reviews: bool = False, new_email: str | None = None
) -> str:
    parameters: dict[str, object] = {}
    if action == AdminConfirmationAction.DELETE_USER:
        parameters["delete_reviews"] = delete_reviews
    elif action == AdminConfirmationAction.CHANGE_ADMIN_EMAIL:
        parameters["new_email"] = normalize_email(new_email or "")
    return confirmation_digest("parameters", json.dumps(parameters, sort_keys=True))


async def lock_confirmation_users(
    db: AsyncSession, actor_id: int, target_id: int
) -> tuple[User, User]:
    # A→B and B→A take the same ordered account locks before any family/grant lock.
    users = (
        await db.scalars(
            select(User)
            .where(User.id.in_({actor_id, target_id}))
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    by_id = {user.id: user for user in users}
    actor, target = by_id.get(actor_id), by_id.get(target_id)
    if actor is None or not actor.active or actor.role != UserRole.ADMIN:
        raise_error(403, ERR_ACCESS_DENIED)
    if target is None:
        raise_error(404, ERR_USER_NOT_FOUND)
    return actor, target


async def require_confirmation_session(
    db: AsyncSession, request: Request, actor: User, now: datetime
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
        or payload.get("user_id") != actor.id
        or payload.get("sub") != actor.email
        or not token_auth_version_matches(payload, actor.auth_version)
    ):
        raise_error(403, ERR_ADMIN_CONFIRMATION_SESSION_REQUIRED)
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
        or family.user_id != actor.id
        or family.revoked_at is not None
        or as_utc(family.expires_at) <= now
        or revoked_access is not None
    ):
        raise_error(403, ERR_ADMIN_CONFIRMATION_SESSION_REQUIRED)
    if not actor.email_verified:
        raise_error(403, ERR_ADMIN_CONFIRMATION_EMAIL_REQUIRED)
    return sid


async def issue_admin_confirmation(
    db: AsyncSession,
    *,
    request: Request,
    actor_id: int,
    data: AdminConfirmationRequest,
    now: datetime | None = None,
) -> AdminConfirmationResponse:
    issued_at = as_utc(now or datetime.now(timezone.utc))
    actor, target = await lock_confirmation_users(db, actor_id, data.target_user_id)
    sid = await require_confirmation_session(db, request, actor, issued_at)
    if data.action == AdminConfirmationAction.CHANGE_ADMIN_EMAIL and target.id != actor.id:
        raise_error(403, ERR_ACCESS_DENIED)
    if data.action == AdminConfirmationAction.DELETE_USER and (
        target.id == actor.id or target.role == UserRole.ADMIN
    ):
        raise_error(400, ERR_ACCESS_DENIED)
    for window, maximum in ((timedelta(minutes=15), 10), (timedelta(days=1), 100)):
        count = await db.scalar(
            select(func.count())
            .select_from(AdminActionConfirmation)
            .where(
                AdminActionConfirmation.actor_user_id == actor.id,
                AdminActionConfirmation.created_at > issued_at - window,
            )
        )
        if count >= maximum:
            raise_error(429, ERR_ADMIN_CONFIRMATION_RATE_LIMITED)
    await db.execute(
        update(AdminActionConfirmation)
        .where(
            AdminActionConfirmation.actor_user_id == actor.id,
            AdminActionConfirmation.session_id == sid,
            AdminActionConfirmation.action == data.action.value,
            AdminActionConfirmation.target_user_id == target.id,
            AdminActionConfirmation.consumed_at.is_(None),
        )
        .values(consumed_at=issued_at, delivered_at=None)
    )
    challenge_id = secrets.token_urlsafe(24)
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = AdminActionConfirmation(
        id=challenge_id,
        actor_user_id=actor.id,
        target_user_id=target.id,
        session_id=sid,
        auth_version=actor.auth_version,
        action=data.action.value,
        email_digest=email_digest(actor.email),
        parameters_digest=parameters_digest(
            data.action, delete_reviews=data.delete_reviews, new_email=data.new_email
        ),
        code_digest=confirmation_digest("code", f"{challenge_id}:{code}"),
        created_at=issued_at,
        expires_at=issued_at + CONFIRMATION_LIFETIME,
        attempts=0,
    )
    recipient = actor.email
    language = resolve_language(data.language, actor.legal_acceptance_language)
    db.add(challenge)
    await db.commit()
    # SMTP never holds an account/family lock; an undelivered code cannot authorize anything.
    sent = await asyncio.to_thread(
        send_admin_confirmation_email,
        to=recipient,
        code=code,
        action=data.action.value,
        target_user_id=data.target_user_id,
        new_email=data.new_email,
        language=language,
    )
    if not sent:
        raise_error(503, ERR_ADMIN_CONFIRMATION_DELIVERY_FAILED)
    delivered = await db.execute(
        update(AdminActionConfirmation)
        .where(
            AdminActionConfirmation.id == challenge_id,
            AdminActionConfirmation.consumed_at.is_(None),
        )
        .values(delivered_at=datetime.now(timezone.utc))
    )
    await db.commit()
    if delivered.rowcount != 1:
        raise_error(400, ERR_ADMIN_CONFIRMATION_INVALID)
    local, domain = recipient.rsplit("@", 1)
    return AdminConfirmationResponse(
        challenge_id=challenge_id,
        expires_at=as_utc(challenge.expires_at),
        masked_email=f"{local[:1]}***@{domain}",
    )


async def consume_admin_confirmation(
    db: AsyncSession,
    *,
    request: Request,
    actor_id: int,
    target_id: int,
    action: AdminConfirmationAction,
    proof: AdminConfirmationProof | None,
    delete_reviews: bool = False,
    new_email: str | None = None,
    now: datetime | None = None,
) -> tuple[User, User, AdminActionConfirmation]:
    if proof is None:
        raise_error(403, ERR_ADMIN_CONFIRMATION_REQUIRED)
    confirmed_at = as_utc(now or datetime.now(timezone.utc))
    actor, target = await lock_confirmation_users(db, actor_id, target_id)
    sid = await require_confirmation_session(db, request, actor, confirmed_at)
    challenge = await db.scalar(
        select(AdminActionConfirmation)
        .where(AdminActionConfirmation.id == proof.challenge_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        challenge is None
        or challenge.actor_user_id != actor.id
        or challenge.target_user_id != target.id
        or challenge.session_id != sid
        or challenge.auth_version != actor.auth_version
        or challenge.action != action.value
        or challenge.email_digest != email_digest(actor.email)
        or challenge.parameters_digest
        != parameters_digest(action, delete_reviews=delete_reviews, new_email=new_email)
        or challenge.consumed_at is not None
        or challenge.delivered_at is None
    ):
        raise_error(400, ERR_ADMIN_CONFIRMATION_INVALID)
    if as_utc(challenge.expires_at) <= confirmed_at:
        raise_error(400, ERR_ADMIN_CONFIRMATION_EXPIRED)
    if challenge.attempts >= MAX_CONFIRMATION_ATTEMPTS:
        raise_error(429, ERR_ADMIN_CONFIRMATION_ATTEMPTS_EXCEEDED)
    if not hmac.compare_digest(
        challenge.code_digest, confirmation_digest("code", f"{challenge.id}:{proof.code}")
    ):
        challenge.attempts += 1
        exhausted = challenge.attempts >= MAX_CONFIRMATION_ATTEMPTS
        # This path precedes every mutation. Persist only the failed-attempt budget.
        await db.commit()
        raise_error(
            429 if exhausted else 400,
            (
                ERR_ADMIN_CONFIRMATION_ATTEMPTS_EXCEEDED
                if exhausted
                else ERR_ADMIN_CONFIRMATION_INVALID
            ),
        )
    challenge.consumed_at = confirmed_at
    await db.flush()
    return actor, target, challenge


async def consume_admin_email_change_link(
    db: AsyncSession,
    *,
    user: User,
    payload: dict,
    now: datetime | None = None,
) -> None:
    """Check protected links even after demotion; legacy admin links never bypass proof."""
    confirmed_at = as_utc(now or datetime.now(timezone.utc))
    challenge_id = payload.get("admin_confirmation_id")
    challenge = (
        await db.scalar(
            select(AdminActionConfirmation)
            .where(AdminActionConfirmation.id == challenge_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if isinstance(challenge_id, str)
        else None
    )
    if (
        challenge is None
        or challenge.actor_user_id != user.id
        or challenge.target_user_id != user.id
        or challenge.action != AdminConfirmationAction.CHANGE_ADMIN_EMAIL.value
        or challenge.auth_version != user.auth_version
        or challenge.email_digest != email_digest(user.email)
        or not user.email_verified
        or challenge.parameters_digest
        != parameters_digest(
            AdminConfirmationAction.CHANGE_ADMIN_EMAIL, new_email=payload.get("new_email")
        )
        or challenge.consumed_at is None
        or challenge.delivered_at is None
        or challenge.email_changed_at is not None
        or as_utc(challenge.consumed_at) + EMAIL_CHANGE_LIFETIME <= confirmed_at
    ):
        raise_error(400, ERR_ADMIN_CONFIRMATION_INVALID)
    family = await db.scalar(
        select(RefreshSession)
        .where(RefreshSession.id == challenge.session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        family is None
        or family.user_id != user.id
        or family.revoked_at is not None
        or as_utc(family.expires_at) <= confirmed_at
    ):
        raise_error(400, ERR_ADMIN_CONFIRMATION_INVALID)
    challenge.email_changed_at = confirmed_at
    await db.flush()


async def invalidate_admin_confirmations(
    db: AsyncSession, *, actor_id: int, session_id: object
) -> None:
    """Logout invalidates both unused codes and pending email links from this family."""
    if not isinstance(session_id, str) or not 1 <= len(session_id) <= 43:
        return
    await db.execute(
        update(AdminActionConfirmation)
        .where(
            AdminActionConfirmation.actor_user_id == actor_id,
            AdminActionConfirmation.session_id == session_id,
        )
        .values(
            delivered_at=None,
            consumed_at=func.coalesce(
                AdminActionConfirmation.consumed_at, datetime.now(timezone.utc)
            ),
        )
    )
