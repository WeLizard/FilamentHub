"""Owner-scoped session management without revoking independent capabilities."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_SESSION_NOT_FOUND, ERR_SESSION_REQUIRED, raise_error
from app.models.admin_action_confirmation import AdminActionConfirmation
from app.models.audit_event import AuditAction, AuditReason
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.schemas.session import (
    AccountSessionListResponse,
    AccountSessionResponse,
    AccountSessionRevokeResponse,
    OtherSessionsRevokeResponse,
)
from app.services.account_auth_service import lock_user_auth_state
from app.services.admin_confirmation_service import invalidate_admin_confirmations
from app.services.audit_service import record_audit_event

logger = logging.getLogger(__name__)
ACTIVITY_INTERVAL = timedelta(minutes=5)
_PENDING_ACTIVITY = "account_session_activity"


def as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def normalized_session_metadata(user_agent: str) -> dict[str, str]:
    """Discard the source immediately; labels never establish authorization."""
    source = user_agent[:512].lower()
    browser = next(
        (
            label
            for needle, label in (
                ("edg/", "edge"),
                ("edga/", "edge"),
                ("edgios/", "edge"),
                ("opr/", "opera"),
                ("firefox/", "firefox"),
                ("fxios/", "firefox"),
                ("chrome/", "chrome"),
                ("crios/", "chrome"),
                ("safari/", "safari"),
            )
            if needle in source
        ),
        "unknown",
    )
    os = next(
        (
            label
            for needle, label in (
                ("android", "android"),
                ("iphone", "ios"),
                ("ipad", "ios"),
                ("windows", "windows"),
                ("macintosh", "macos"),
                ("linux", "linux"),
            )
            if needle in source
        ),
        "unknown",
    )
    device_type = (
        "tablet"
        if "ipad" in source or (os == "android" and "mobile" not in source)
        else "mobile"
        if os in {"android", "ios"}
        else "desktop"
        if os in {"windows", "macos", "linux"}
        else "unknown"
    )
    return {"browser": browser, "os": os, "device_type": device_type}


async def validate_access_family(
    db: AsyncSession,
    *,
    payload: dict,
    user: User,
    request: Request,
) -> bool:
    """Validate every bound access token; legacy access ends at an explicit revoke."""
    sid = payload.get("sid")
    if sid is None:
        return user.legacy_access_revoked_at is None
    if not isinstance(sid, str) or not 1 <= len(sid) <= 43:
        return False
    row = (
        await db.execute(
            select(
                RefreshSession.user_id,
                RefreshSession.revoked_at,
                RefreshSession.expires_at,
                RefreshSession.last_seen_at,
            ).where(RefreshSession.id == sid)
        )
    ).one_or_none()
    now = datetime.now(timezone.utc)
    if (
        row is None
        or row.user_id != user.id
        or row.revoked_at is not None
        or as_utc(row.expires_at) <= now
    ):
        return False
    request.state.account_session_id = sid
    if row.last_seen_at is None or as_utc(row.last_seen_at) <= now - ACTIVITY_INTERVAL:
        db.info.setdefault(_PENDING_ACTIVITY, {})[sid] = (user.id, now)
    return True


async def persist_session_activity(db: AsyncSession) -> None:
    """Run after the business transaction, avoiding family→account lock inversion."""
    pending = db.info.pop(_PENDING_ACTIVITY, {})
    if not pending:
        return
    try:
        for sid, (user_id, seen_at) in pending.items():
            await db.execute(
                update(RefreshSession)
                .where(
                    RefreshSession.id == sid,
                    RefreshSession.user_id == user_id,
                    RefreshSession.revoked_at.is_(None),
                    RefreshSession.expires_at > seen_at,
                    or_(
                        RefreshSession.last_seen_at.is_(None),
                        RefreshSession.last_seen_at <= seen_at - ACTIVITY_INTERVAL,
                    ),
                )
                .values(last_seen_at=seen_at)
                .execution_options(synchronize_session=False)
            )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("Failed to record sampled session activity", exc_info=True)


def current_session_id(request: Request) -> str:
    sid = getattr(request.state, "account_session_id", None)
    if not isinstance(sid, str):
        raise_error(401, ERR_SESSION_REQUIRED, headers={"WWW-Authenticate": "Bearer"})
    return sid


async def _lock_current_session(
    db: AsyncSession, request: Request, user_id: int
) -> tuple[User, str]:
    sid = current_session_id(request)
    user = await lock_user_auth_state(db, user_id)
    if user is None or not user.active:
        raise_error(401, ERR_SESSION_REQUIRED, headers={"WWW-Authenticate": "Bearer"})
    family = await db.scalar(
        select(RefreshSession)
        .where(
            RefreshSession.id == sid,
            RefreshSession.user_id == user.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        family is None
        or family.revoked_at is not None
        or as_utc(family.expires_at) <= datetime.now(timezone.utc)
    ):
        raise_error(401, ERR_SESSION_REQUIRED, headers={"WWW-Authenticate": "Bearer"})
    return user, sid


async def list_account_sessions(
    db: AsyncSession,
    *,
    request: Request,
    user_id: int,
    page: int,
    size: int,
) -> AccountSessionListResponse:
    sid = current_session_id(request)
    filters = (
        RefreshSession.user_id == user_id,
        RefreshSession.revoked_at.is_(None),
        RefreshSession.expires_at > datetime.now(timezone.utc),
    )
    total = await db.scalar(select(func.count()).select_from(RefreshSession).where(*filters)) or 0
    rows = (
        await db.scalars(
            select(RefreshSession)
            .where(*filters)
            .order_by(
                case((RefreshSession.id == sid, 0), else_=1),
                RefreshSession.created_at.desc(),
                RefreshSession.id,
            )
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    return AccountSessionListResponse(
        items=[
            AccountSessionResponse(
                id=row.id,
                is_current=row.id == sid,
                created_at=as_utc(row.created_at),
                last_seen_at=as_utc(row.last_seen_at or row.rotated_at or row.created_at),
                expires_at=as_utc(row.expires_at),
                browser=row.browser,
                os=row.os,
                device_type=row.device_type,
            )
            for row in rows
        ],
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size,
        current_session_id=sid,
    )


async def revoke_account_session(
    db: AsyncSession,
    *,
    request: Request,
    user_id: int,
    session_id: str,
) -> AccountSessionRevokeResponse:
    user, sid = await _lock_current_session(db, request, user_id)
    target = await db.scalar(
        select(RefreshSession)
        .where(
            RefreshSession.id == session_id,
            RefreshSession.user_id == user.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if target is None:
        raise_error(404, ERR_SESSION_NOT_FOUND)
    changed = target.revoked_at is None
    if changed:
        now = datetime.now(timezone.utc)
        target.revoked_at = now
        user.legacy_access_revoked_at = user.legacy_access_revoked_at or now
        await invalidate_admin_confirmations(db, actor_id=user.id, session_id=target.id)
        await record_audit_event(
            db,
            action=AuditAction.AUTH_REVOKED,
            actor_user_id=user.id,
            target_user_id=user.id,
            reason=AuditReason.SESSION_REVOKE,
        )
    await db.commit()
    return AccountSessionRevokeResponse(revoked=changed, current_session_revoked=target.id == sid)


async def revoke_other_account_sessions(
    db: AsyncSession,
    *,
    request: Request,
    user_id: int,
) -> OtherSessionsRevokeResponse:
    user, sid = await _lock_current_session(db, request, user_id)
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(RefreshSession)
        .where(
            RefreshSession.user_id == user.id,
            RefreshSession.id != sid,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    revoked_count = max(result.rowcount or 0, 0)
    legacy_changed = user.legacy_refresh_disabled_at is None
    user.legacy_access_revoked_at = user.legacy_access_revoked_at or now
    user.legacy_refresh_disabled_at = user.legacy_refresh_disabled_at or now
    await db.execute(
        update(AdminActionConfirmation)
        .where(
            AdminActionConfirmation.actor_user_id == user.id,
            AdminActionConfirmation.session_id != sid,
        )
        .values(
            delivered_at=None, consumed_at=func.coalesce(AdminActionConfirmation.consumed_at, now)
        )
    )
    if revoked_count or legacy_changed:
        from app.services.printer_contact_events import queue_other_sessions_revoked

        queue_other_sessions_revoked(db.sync_session, user.id, sid)
        await record_audit_event(
            db,
            action=AuditAction.AUTH_REVOKED,
            actor_user_id=user.id,
            target_user_id=user.id,
            reason=AuditReason.OTHER_SESSIONS_REVOKE,
        )
    await db.commit()
    return OtherSessionsRevokeResponse(revoked_count=revoked_count)
