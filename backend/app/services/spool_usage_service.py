"""One place that writes down a spool's consumption history."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ERR_ACCESS_DENIED, raise_error
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user_spool import UserSpool
from app.schemas.spool import SpoolUsageEventResponse


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
) -> PresetUsageEvent:
    """Note one fact about a spool's consumption next to the running total.

    The total on the spool stays the number everything reads; this only says who
    changed it, when and by how much, so a mistake can be traced and undone.
    """
    event = PresetUsageEvent(
        user_id=spool.user_id,
        device_id=device_id,
        preset_id=preset_id,
        spool_id=spool.id,
        event_type=event_type,
        delta_weight_g=delta_weight_g,
        remaining_weight_g=max(spool.initial_weight_g - spool.used_weight_g, 0.0),
        job_ref=job_ref,
        meta=meta,
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
        )
        for row in rows
    ]
