"""One place that writes down a spool's consumption history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_USAGE_EVENT_ALREADY_REVERTED,
    ERR_USAGE_EVENT_NOT_FOUND,
    ERR_USAGE_EVENT_NOT_REVERTIBLE,
    raise_error,
)
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.spool import SpoolUsageEventResponse


# A repeat of the same request looks exactly like this: one printer, the same
# amount, seconds apart. A print cannot spend an identical amount twice that fast.
_REPEAT_WINDOW = timedelta(seconds=60)


async def _looks_like_a_repeat(
    db: AsyncSession, *, spool_id: int, device_id: int | None, delta_weight_g: float
) -> bool:
    if device_id is None or delta_weight_g <= 0:
        return False
    since = datetime.now(timezone.utc) - _REPEAT_WINDOW
    twin = await db.scalar(
        select(PresetUsageEvent.id).where(
            PresetUsageEvent.spool_id == spool_id,
            PresetUsageEvent.device_id == device_id,
            PresetUsageEvent.delta_weight_g == delta_weight_g,
            PresetUsageEvent.created_at >= since,
        )
    )
    return twin is not None


async def record_spool_usage(
    db: AsyncSession,
    *,
    spool: UserSpool,
    event_type: PresetUsageEventType,
    delta_weight_g: float | None,
    device_id: int | None = None,
    preset_id: int | None = None,
    job_ref: str | None = None,
    meta: dict | None = None,
    reported_weight_g: float | None = None,
) -> PresetUsageEvent:
    """Note one fact about a spool's consumption next to the running total.

    The total on the spool stays the number everything reads; this only says who
    changed it, when and by how much, so a mistake can be traced and undone.

    A printer can be wrong in either direction, so what it claimed is kept next to
    what actually fit on the spool, and a request that arrived twice is marked.
    """
    notes = dict(meta or {})
    if reported_weight_g is not None and delta_weight_g is not None:
        if abs(reported_weight_g - delta_weight_g) > 0.01:
            notes["reported_weight_g"] = reported_weight_g
    if event_type == PresetUsageEventType.printer_report and delta_weight_g is not None:
        if await _looks_like_a_repeat(
            db, spool_id=spool.id, device_id=device_id, delta_weight_g=delta_weight_g
        ):
            notes["possible_repeat"] = True

    event = PresetUsageEvent(
        user_id=spool.user_id,
        device_id=device_id,
        preset_id=preset_id,
        spool_id=spool.id,
        event_type=event_type,
        delta_weight_g=delta_weight_g,
        remaining_weight_g=max(spool.initial_weight_g - spool.used_weight_g, 0.0),
        job_ref=job_ref,
        meta=notes or None,
    )
    db.add(event)
    return event


async def list_spool_usage(
    db: AsyncSession, *, user_id: int, spool_id: int
) -> list[SpoolUsageEventResponse]:
    """A spool's consumption history, newest first."""
    spool = await db.get(UserSpool, spool_id)
    if spool is None or spool.user_id != user_id:
        raise_error(404, ERR_ACCESS_DENIED)

    rows = (
        await db.execute(
            select(PresetUsageEvent)
            .where(
                PresetUsageEvent.spool_id == spool_id,
                PresetUsageEvent.user_id == user_id,
            )
            .options(selectinload(PresetUsageEvent.device))
            .order_by(PresetUsageEvent.created_at.desc(), PresetUsageEvent.id.desc())
        )
    ).scalars().all()

    return [
        SpoolUsageEventResponse(
            id=row.id,
            event_type=row.event_type.value,
            delta_weight_g=row.delta_weight_g,
            remaining_weight_g=row.remaining_weight_g,
            device_name=row.device.name if row.device is not None else None,
            job_ref=row.job_ref,
            created_at=row.created_at,
            meta=row.meta,
        )
        for row in rows
    ]


async def revert_spool_usage(
    db: AsyncSession, *, user_id: int, spool_id: int, event_id: int
) -> SpoolUsageEventResponse:
    """Give back what one record took, and say so in the history.

    The record stays: history is added to, never rewritten. A measurement is not
    reverted — it states what was actually on the spool, and pretending otherwise
    would fake the reading rather than correct a mistake.
    """
    spool = await db.get(UserSpool, spool_id)
    if spool is None or spool.user_id != user_id:
        raise_error(404, ERR_ACCESS_DENIED)

    event = await db.get(PresetUsageEvent, event_id)
    if event is None or event.spool_id != spool_id or event.user_id != user_id:
        raise_error(404, ERR_USAGE_EVENT_NOT_FOUND)
    if event.event_type == PresetUsageEventType.reconcile_adjust:
        raise_error(409, ERR_USAGE_EVENT_NOT_REVERTIBLE)

    notes = dict(event.meta or {})
    if notes.get("reverted"):
        raise_error(409, ERR_USAGE_EVENT_ALREADY_REVERTED)

    delta = event.delta_weight_g or 0.0
    restored = spool.used_weight_g - delta
    if restored < 0 or restored > spool.initial_weight_g:
        raise_error(409, ERR_USAGE_EVENT_NOT_REVERTIBLE)

    spool.used_weight_g = restored
    if spool.state == UserSpoolState.empty and spool.remaining_weight_g > 0:
        # Back on the shelf rather than into a slot: where it goes is the person's
        # call, and the slot was cleared when the spool ran out.
        spool.state = UserSpoolState.shelf

    notes["reverted"] = True
    event.meta = notes

    reversal = await record_spool_usage(
        db,
        spool=spool,
        event_type=PresetUsageEventType.manual_adjust,
        delta_weight_g=-delta,
        device_id=event.device_id,
        meta={"reverts_event_id": event.id},
    )
    await db.commit()
    await db.refresh(reversal)
    return SpoolUsageEventResponse(
        id=reversal.id,
        event_type=reversal.event_type.value,
        delta_weight_g=reversal.delta_weight_g,
        remaining_weight_g=reversal.remaining_weight_g,
        device_name=None,
        job_ref=None,
        created_at=reversal.created_at,
        meta=reversal.meta,
    )
