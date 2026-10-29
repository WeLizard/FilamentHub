"""Issue, list, revoke and authenticate workstation keys."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_COULD_NOT_VALIDATE,
    ERR_LEGAL_ACCEPTANCE_REQUIRED,
    ERR_USER_INACTIVE,
    ERR_WORKSTATION_KEY_LIMIT,
    ERR_WORKSTATION_KEY_NOT_FOUND,
    raise_error,
)
from app.models.user import User
from app.models.workstation_key import WorkstationKey
from app.services.legal_acceptance_service import requires_current_legal_acceptance

WORKSTATION_KEY_PREFIX = "fhw_"
# Observation and report only: a workstation key never edits presets, never
# confirms an assignment and never touches the account.
WORKSTATION_SCOPES = frozenset(
    {"sync:report", "material-topology:read", "material-topology:report", "stock-alerts:read"}
)
MAX_ACTIVE_KEYS = 10
_LAST_USED_RESOLUTION = timedelta(minutes=5)


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


async def issue_workstation_key(
    db: AsyncSession, user: User, name: str
) -> tuple[WorkstationKey, str]:
    active = await db.scalar(
        select(func.count())
        .select_from(WorkstationKey)
        .where(WorkstationKey.user_id == user.id, WorkstationKey.revoked_at.is_(None))
    )
    if (active or 0) >= MAX_ACTIVE_KEYS:
        raise_error(status.HTTP_409_CONFLICT, ERR_WORKSTATION_KEY_LIMIT)
    key = WORKSTATION_KEY_PREFIX + secrets.token_urlsafe(32)
    row = WorkstationKey(user_id=user.id, name=name, key_digest=_digest(key))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row, key


async def list_workstation_keys(db: AsyncSession, user_id: int) -> list[WorkstationKey]:
    result = await db.scalars(
        select(WorkstationKey)
        .where(WorkstationKey.user_id == user_id, WorkstationKey.revoked_at.is_(None))
        .order_by(WorkstationKey.id)
    )
    return list(result)


async def revoke_workstation_key(db: AsyncSession, user_id: int, key_id: int) -> None:
    row = await db.scalar(
        select(WorkstationKey).where(WorkstationKey.id == key_id, WorkstationKey.user_id == user_id)
    )
    if row is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_WORKSTATION_KEY_NOT_FOUND)
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await db.commit()


async def authenticate_workstation_key(db: AsyncSession, key: str, required_scope: str) -> User:
    unauthorized = {
        "status_code": status.HTTP_401_UNAUTHORIZED,
        "headers": {"WWW-Authenticate": "Bearer"},
    }
    row = await db.scalar(
        select(WorkstationKey).where(
            WorkstationKey.key_digest == _digest(key), WorkstationKey.revoked_at.is_(None)
        )
    )
    if row is None:
        raise_error(
            unauthorized["status_code"], ERR_COULD_NOT_VALIDATE, headers=unauthorized["headers"]
        )
    if required_scope not in WORKSTATION_SCOPES:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    user = await db.scalar(
        select(User).options(selectinload(User.subscription)).where(User.id == row.user_id)
    )
    if user is None:
        raise_error(
            unauthorized["status_code"], ERR_COULD_NOT_VALIDATE, headers=unauthorized["headers"]
        )
    if not user.active:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_USER_INACTIVE)
    if requires_current_legal_acceptance(user):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_LEGAL_ACCEPTANCE_REQUIRED)
    now = datetime.now(timezone.utc)
    last = row.last_used_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is None or now - last >= _LAST_USED_RESOLUTION:
        await db.execute(
            update(WorkstationKey).where(WorkstationKey.id == row.id).values(last_used_at=now)
        )
    return user
