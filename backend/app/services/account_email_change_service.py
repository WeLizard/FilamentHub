"""Two-address proof flow for changing a regular account email."""

import asyncio
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_EMAIL_CHANGE_ATTEMPTS_EXCEEDED,
    ERR_EMAIL_CHANGE_CURRENT_EMAIL_REQUIRED,
    ERR_EMAIL_CHANGE_DELIVERY_FAILED,
    ERR_EMAIL_CHANGE_EXPIRED,
    ERR_EMAIL_CHANGE_INVALID,
    ERR_EMAIL_CHANGE_RATE_LIMITED,
    ERR_EMAIL_CHANGE_REQUIRED,
    ERR_EMAIL_CHANGE_SESSION_REQUIRED,
    ERR_EMAIL_EXISTS,
    ERR_USER_NOT_FOUND,
    raise_error,
)
from app.core.i18n import resolve_language
from app.core.utils import normalize_email
from app.models.account_email_change_confirmation import AccountEmailChangeConfirmation
from app.models.refresh_session import RefreshSession
from app.models.user import User, UserRole
from app.schemas.account_email_change import (
    AccountEmailChangeChallengeRequest,
    AccountEmailChangeChallengeResponse,
    AccountEmailChangeProof,
)
from app.services.account_auth_service import lock_user_auth_state
from app.services.auth_confirmation_primitives import (
    as_utc,
    confirmation_digest,
    email_digest,
    require_current_refresh_family,
)
from app.services.email_service import send_account_email_change_code

CONFIRMATION_SCOPE = "account-email-change"
CODE_LIFETIME = timedelta(minutes=10)
LINK_LIFETIME = timedelta(hours=24)
MAX_ATTEMPTS = 5


def _digest(purpose: str, value: str) -> str:
    return confirmation_digest(CONFIRMATION_SCOPE, purpose, value)


def _email_digest(email: str) -> str:
    return email_digest(CONFIRMATION_SCOPE, email)


async def _require_available_email(
    db: AsyncSession, *, user_id: int, current_email: str, new_email: str
) -> str:
    requested_email = normalize_email(new_email)
    if requested_email == normalize_email(current_email):
        raise_error(400, ERR_EMAIL_EXISTS)
    existing = await db.scalar(
        select(User.id).where(
            func.lower(User.email) == requested_email,
            User.id != user_id,
        )
    )
    if existing is not None:
        raise_error(400, ERR_EMAIL_EXISTS)
    return requested_email


async def issue_account_email_change_challenge(
    db: AsyncSession,
    *,
    request: Request,
    user_id: int,
    data: AccountEmailChangeChallengeRequest,
    now: datetime | None = None,
) -> AccountEmailChangeChallengeResponse:
    issued_at = as_utc(now or datetime.now(timezone.utc))
    user = await lock_user_auth_state(db, user_id)
    if user is None or not user.active:
        raise_error(404, ERR_USER_NOT_FOUND)
    if user.role == UserRole.ADMIN:
        raise_error(403, ERR_ACCESS_DENIED)
    sid = await require_current_refresh_family(
        db,
        request=request,
        user=user,
        now=issued_at,
        session_error=ERR_EMAIL_CHANGE_SESSION_REQUIRED,
        verified_email_error=ERR_EMAIL_CHANGE_CURRENT_EMAIL_REQUIRED,
    )
    requested_email = await _require_available_email(
        db, user_id=user.id, current_email=user.email, new_email=str(data.new_email)
    )
    for window, maximum in ((timedelta(minutes=15), 10), (timedelta(days=1), 100)):
        count = await db.scalar(
            select(func.count())
            .select_from(AccountEmailChangeConfirmation)
            .where(
                AccountEmailChangeConfirmation.user_id == user.id,
                AccountEmailChangeConfirmation.created_at > issued_at - window,
            )
        )
        if count >= maximum:
            raise_error(429, ERR_EMAIL_CHANGE_RATE_LIMITED)
    await db.execute(
        update(AccountEmailChangeConfirmation)
        .where(
            AccountEmailChangeConfirmation.user_id == user.id,
            AccountEmailChangeConfirmation.session_id == sid,
            AccountEmailChangeConfirmation.consumed_at.is_(None),
        )
        .values(consumed_at=issued_at, delivered_at=None)
    )
    challenge_id = secrets.token_urlsafe(24)
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = AccountEmailChangeConfirmation(
        id=challenge_id,
        user_id=user.id,
        session_id=sid,
        auth_version=user.auth_version,
        current_email_digest=_email_digest(user.email),
        new_email_digest=_email_digest(requested_email),
        code_digest=_digest("code", f"{challenge_id}:{code}"),
        attempts=0,
        created_at=issued_at,
        expires_at=issued_at + CODE_LIFETIME,
    )
    recipient = user.email
    language = resolve_language(data.language, user.legal_acceptance_language)
    db.add(challenge)
    await db.commit()
    sent = await asyncio.to_thread(
        send_account_email_change_code,
        to=recipient,
        code=code,
        new_email=requested_email,
        language=language,
    )
    if not sent:
        raise_error(503, ERR_EMAIL_CHANGE_DELIVERY_FAILED)
    delivered = await db.execute(
        update(AccountEmailChangeConfirmation)
        .where(
            AccountEmailChangeConfirmation.id == challenge_id,
            AccountEmailChangeConfirmation.consumed_at.is_(None),
        )
        .values(delivered_at=datetime.now(timezone.utc))
    )
    await db.commit()
    if delivered.rowcount != 1:
        raise_error(400, ERR_EMAIL_CHANGE_INVALID)
    local, domain = recipient.rsplit("@", 1)
    return AccountEmailChangeChallengeResponse(
        challenge_id=challenge_id,
        expires_at=as_utc(challenge.expires_at),
        masked_email=f"{local[:1]}***@{domain}",
    )


async def consume_account_email_change_proof(
    db: AsyncSession,
    *,
    request: Request,
    user_id: int,
    proof: AccountEmailChangeProof | None,
    new_email: str,
    now: datetime | None = None,
) -> tuple[User, AccountEmailChangeConfirmation, str]:
    if proof is None:
        raise_error(403, ERR_EMAIL_CHANGE_REQUIRED)
    consumed_at = as_utc(now or datetime.now(timezone.utc))
    user = await lock_user_auth_state(db, user_id)
    if user is None or not user.active:
        raise_error(404, ERR_USER_NOT_FOUND)
    if user.role == UserRole.ADMIN:
        raise_error(403, ERR_ACCESS_DENIED)
    sid = await require_current_refresh_family(
        db,
        request=request,
        user=user,
        now=consumed_at,
        session_error=ERR_EMAIL_CHANGE_SESSION_REQUIRED,
        verified_email_error=ERR_EMAIL_CHANGE_CURRENT_EMAIL_REQUIRED,
    )
    requested_email = await _require_available_email(
        db, user_id=user.id, current_email=user.email, new_email=new_email
    )
    challenge = await db.scalar(
        select(AccountEmailChangeConfirmation)
        .where(AccountEmailChangeConfirmation.id == proof.challenge_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        challenge is None
        or challenge.user_id != user.id
        or challenge.session_id != sid
        or challenge.auth_version != user.auth_version
        or challenge.current_email_digest != _email_digest(user.email)
        or challenge.new_email_digest != _email_digest(requested_email)
        or challenge.consumed_at is not None
        or challenge.delivered_at is None
    ):
        raise_error(400, ERR_EMAIL_CHANGE_INVALID)
    if as_utc(challenge.expires_at) <= consumed_at:
        raise_error(400, ERR_EMAIL_CHANGE_EXPIRED)
    if challenge.attempts >= MAX_ATTEMPTS:
        raise_error(429, ERR_EMAIL_CHANGE_ATTEMPTS_EXCEEDED)
    if not hmac.compare_digest(
        challenge.code_digest, _digest("code", f"{challenge.id}:{proof.code}")
    ):
        challenge.attempts += 1
        exhausted = challenge.attempts >= MAX_ATTEMPTS
        await db.commit()
        raise_error(
            429 if exhausted else 400,
            ERR_EMAIL_CHANGE_ATTEMPTS_EXCEEDED if exhausted else ERR_EMAIL_CHANGE_INVALID,
        )
    challenge.consumed_at = consumed_at
    await db.flush()
    return user, challenge, requested_email


async def mark_account_email_change_link_delivered(
    db: AsyncSession, *, challenge_id: str
) -> None:
    delivered = await db.execute(
        update(AccountEmailChangeConfirmation)
        .where(
            AccountEmailChangeConfirmation.id == challenge_id,
            AccountEmailChangeConfirmation.consumed_at.is_not(None),
            AccountEmailChangeConfirmation.email_changed_at.is_(None),
        )
        .values(link_delivered_at=datetime.now(timezone.utc))
    )
    if delivered.rowcount != 1:
        raise_error(400, ERR_EMAIL_CHANGE_INVALID)


async def consume_account_email_change_link(
    db: AsyncSession,
    *,
    user: User,
    payload: dict,
    now: datetime | None = None,
) -> None:
    confirmed_at = as_utc(now or datetime.now(timezone.utc))
    challenge_id = payload.get("account_confirmation_id")
    challenge = (
        await db.scalar(
            select(AccountEmailChangeConfirmation)
            .where(AccountEmailChangeConfirmation.id == challenge_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if isinstance(challenge_id, str)
        else None
    )
    new_email = payload.get("new_email")
    if (
        challenge is None
        or not isinstance(new_email, str)
        or challenge.user_id != user.id
        or challenge.auth_version != user.auth_version
        or challenge.current_email_digest != _email_digest(user.email)
        or challenge.new_email_digest != _email_digest(new_email)
        or not user.email_verified
        or challenge.consumed_at is None
        or challenge.delivered_at is None
        or challenge.link_delivered_at is None
        or challenge.email_changed_at is not None
        or as_utc(challenge.consumed_at) + LINK_LIFETIME <= confirmed_at
    ):
        raise_error(400, ERR_EMAIL_CHANGE_INVALID)
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
        raise_error(400, ERR_EMAIL_CHANGE_INVALID)
    challenge.email_changed_at = confirmed_at
    await db.flush()


async def invalidate_account_email_change_confirmations(
    db: AsyncSession, *, user_id: int, session_id: object
) -> None:
    if not isinstance(session_id, str) or not 1 <= len(session_id) <= 43:
        return
    await db.execute(
        update(AccountEmailChangeConfirmation)
        .where(
            AccountEmailChangeConfirmation.user_id == user_id,
            AccountEmailChangeConfirmation.session_id == session_id,
            AccountEmailChangeConfirmation.email_changed_at.is_(None),
        )
        .values(
            delivered_at=None,
            link_delivered_at=None,
            consumed_at=func.coalesce(
                AccountEmailChangeConfirmation.consumed_at, datetime.now(timezone.utc)
            ),
        )
    )
