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
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, MaterialSystem
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.spool import SpoolUsageEventResponse

_OCTOPRINT_IDEMPOTENCY_PREFIX = "octoprint:"
_RETRY_REPLAY_WINDOW = timedelta(seconds=15)


def octoprint_job_ref(idempotency_key: str) -> str:
    """Namespace a transport key before storing it in the shared job reference."""
    return f"{_OCTOPRINT_IDEMPOTENCY_PREFIX}{idempotency_key}"


def _reported_weight(event: PresetUsageEvent) -> float | None:
    value = (event.meta or {}).get("reported_weight_g")
    if isinstance(value, (int, float)):
        return float(value)
    return event.delta_weight_g


async def find_printer_report_replay(
    db: AsyncSession,
    *,
    spool_id: int,
    device_id: int | None,
    provider: str | None,
    reported_weight_g: float,
    idempotency_key: str | None = None,
) -> tuple[PresetUsageEvent | None, bool, str | None]:
    """Find a committed report replay.

    An explicit key is durable and exact. The time-bounded fallback exists for
    the official OctoPrint Spoolman plugin, which retries PUT after response
    loss but currently sends no request identifier.
    """
    if idempotency_key is not None:
        job_ref = octoprint_job_ref(idempotency_key)
        existing = await db.scalar(
            select(PresetUsageEvent).where(
                PresetUsageEvent.spool_id == spool_id,
                PresetUsageEvent.device_id == device_id,
                PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
                PresetUsageEvent.job_ref == job_ref,
            )
        )
        if existing is not None:
            existing_weight = _reported_weight(existing)
            conflict = existing_weight is None or abs(existing_weight - reported_weight_g) > 1e-9
            return existing, conflict, "idempotency_key"
        return None, False, None

    if device_id is None or provider != "octoprint" or reported_weight_g <= 0:
        return None, False, None

    since = datetime.now(timezone.utc) - _RETRY_REPLAY_WINDOW
    recent = (
        await db.execute(
            select(PresetUsageEvent)
            .where(
                PresetUsageEvent.spool_id == spool_id,
                PresetUsageEvent.device_id == device_id,
                PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
                PresetUsageEvent.created_at >= since,
            )
            .order_by(PresetUsageEvent.created_at.desc(), PresetUsageEvent.id.desc())
            .limit(4)
        )
    ).scalars()
    for event in recent:
        previous_weight = _reported_weight(event)
        if previous_weight is not None and abs(previous_weight - reported_weight_g) <= 1e-9:
            return event, False, "octoprint_retry_window"

    return None, False, None


def mark_printer_report_replay(event: PresetUsageEvent, *, reason: str) -> None:
    """Record suppressed transport retries without creating fake consumption."""
    notes = dict(event.meta or {})
    notes["suppressed_replay_count"] = int(notes.get("suppressed_replay_count", 0)) + 1
    notes["last_suppressed_replay_at"] = datetime.now(timezone.utc).isoformat()
    notes["replay_protection"] = reason
    event.meta = notes


async def resolve_assigned_preset_id(
    db: AsyncSession,
    *,
    user_id: int,
    spool_id: int,
    physical_printer_id: int,
    material_system_id: int | None = None,
    slot_index: int | None = None,
) -> int | None:
    """Return only one exact current preset assignment for a printer report."""
    conditions = [
        MaterialSlotAssignment.user_id == user_id,
        MaterialSlotAssignment.spool_id == spool_id,
        MaterialSlotAssignment.preset_id.is_not(None),
        MaterialSlotAssignment.active.is_(True),
        MaterialSlot.user_id == user_id,
        MaterialSlot.active.is_(True),
        MaterialSystem.user_id == user_id,
        MaterialSystem.physical_printer_id == physical_printer_id,
        MaterialSystem.active.is_(True),
    ]
    if material_system_id is not None:
        conditions.append(MaterialSystem.id == material_system_id)
    if slot_index is not None:
        conditions.append(MaterialSlot.provider_index == slot_index)

    preset_ids = list(
        await db.scalars(
            select(MaterialSlotAssignment.preset_id)
            .join(
                MaterialSlot,
                MaterialSlot.id == MaterialSlotAssignment.material_slot_id,
            )
            .join(
                MaterialSystem,
                MaterialSystem.id == MaterialSlot.material_system_id,
            )
            .where(*conditions)
            .order_by(MaterialSlotAssignment.id)
            .limit(2)
        )
    )
    return int(preset_ids[0]) if len(preset_ids) == 1 else None


async def record_spool_usage(
    db: AsyncSession,
    *,
    spool: UserSpool,
    event_type: PresetUsageEventType,
    delta_weight_g: float | None,
    device_id: int | None = None,
    preset_id: int | None = None,
    print_job_id: int | None = None,
    job_ref: str | None = None,
    meta: dict | None = None,
    reported_weight_g: float | None = None,
) -> PresetUsageEvent:
    """Note one fact about a spool's consumption next to the running total.

    The total on the spool stays the number everything reads; this only says who
    changed it, when and by how much, so a mistake can be traced and undone.

    A printer can be wrong in either direction, so what it claimed is kept next
    to what actually fit on the spool. Transport replays are resolved before
    this function creates an event.
    """
    notes = dict(meta or {})
    if reported_weight_g is not None:
        notes["reported_weight_g"] = reported_weight_g

    event = PresetUsageEvent(
        user_id=spool.user_id,
        device_id=device_id,
        preset_id=preset_id,
        print_job_id=print_job_id,
        spool_id=spool.id,
        event_type=event_type,
        delta_weight_g=delta_weight_g,
        remaining_weight_g=max(spool.initial_weight_g - spool.used_weight_g, 0.0),
        job_ref=job_ref,
        meta=notes or None,
    )
    db.add(event)
    if preset_id is not None and event_type == PresetUsageEventType.printer_report:
        from app.models.preset import Preset

        preset_author_id = await db.scalar(
            select(Preset.user_id).where(Preset.id == preset_id)
        )
        if preset_author_id is not None and preset_author_id != spool.user_id:
            from app.services.preset_funnel_metrics import record_preset_funnel_event

            record_preset_funnel_event(db, "confirmed_after_print")
    return event


async def list_spool_usage(
    db: AsyncSession, *, user_id: int, spool_id: int
) -> list[SpoolUsageEventResponse]:
    """A spool's consumption history, newest first."""
    spool = await db.get(UserSpool, spool_id)
    if spool is None or spool.user_id != user_id:
        raise_error(404, ERR_ACCESS_DENIED)

    rows = (
        (
            await db.execute(
                select(PresetUsageEvent)
                .where(
                    PresetUsageEvent.spool_id == spool_id,
                    PresetUsageEvent.user_id == user_id,
                )
                .options(selectinload(PresetUsageEvent.device))
                .order_by(PresetUsageEvent.created_at.desc(), PresetUsageEvent.id.desc())
            )
        )
        .scalars()
        .all()
    )

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
        print_job_id=event.print_job_id,
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
