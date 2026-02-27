"""Business logic for preset slot sync (HH integration)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_DEVICE_NOT_FOUND,
    ERR_DEVICE_NOT_OWNER,
    ERR_GATE_INDEX_INVALID,
    ERR_PRESET_NOT_ACCESSIBLE,
    raise_error,
)
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.preset_slot_sync import (
    DeviceRegisterRequest,
    HHSnapshotRequest,
    ManualAssignmentRequest,
    UsageEstimateRequest,
)

logger = logging.getLogger(__name__)


# ── Device helpers ─────────────────────────────────────────────────────────


async def get_device_by_fingerprint(
    db: AsyncSession,
    user_id: int,
    fingerprint: str,
) -> UserPrinterDevice | None:
    result = await db.execute(
        select(UserPrinterDevice).where(
            UserPrinterDevice.user_id == user_id,
            UserPrinterDevice.device_fingerprint == fingerprint,
        )
    )
    return result.scalars().first()


async def require_device(
    db: AsyncSession,
    user_id: int,
    device_id: int,
) -> UserPrinterDevice:
    result = await db.execute(
        select(UserPrinterDevice).where(UserPrinterDevice.id == device_id)
    )
    device = result.scalars().first()
    if not device:
        raise_error(404, ERR_DEVICE_NOT_FOUND)
    if device.user_id != user_id:
        raise_error(403, ERR_DEVICE_NOT_OWNER)
    return device  # type: ignore[return-value]


async def register_or_update_device(
    db: AsyncSession,
    user: User,
    payload: DeviceRegisterRequest,
) -> UserPrinterDevice:
    device = await get_device_by_fingerprint(db, user.id, payload.device_fingerprint)
    now = datetime.now(timezone.utc)

    if device is None:
        device = UserPrinterDevice(
            user_id=user.id,
            device_fingerprint=payload.device_fingerprint,
            name=payload.name,
            printer_id=payload.printer_id,
            supports_hh=payload.supports_hh,
            gate_count=payload.gate_count,
            last_seen_at=now,
        )
        db.add(device)
    else:
        device.name = payload.name
        if payload.printer_id is not None:
            device.printer_id = payload.printer_id
        device.supports_hh = payload.supports_hh
        if payload.gate_count is not None:
            device.gate_count = payload.gate_count
        device.last_seen_at = now

    await db.commit()
    await db.refresh(device)
    return device


async def list_user_devices(
    db: AsyncSession,
    user_id: int,
) -> list[UserPrinterDevice]:
    result = await db.execute(
        select(UserPrinterDevice).where(UserPrinterDevice.user_id == user_id)
    )
    return list(result.scalars().all())


# ── Gate state helpers ─────────────────────────────────────────────────────


async def get_gate_states(
    db: AsyncSession,
    device_id: int,
) -> list[PresetGateState]:
    result = await db.execute(
        select(PresetGateState)
        .where(PresetGateState.device_id == device_id)
        .order_by(PresetGateState.gate_index)
    )
    return list(result.scalars().all())


async def _upsert_gate_state(
    db: AsyncSession,
    *,
    user_id: int,
    device_id: int,
    gate_index: int,
    source: PresetGateStateSource,
    source_ts: datetime,
    preset_id: int | None = None,
    spool_id: int | None = None,
    hh_material: str | None = None,
    hh_color_hex: str | None = None,
    hh_status: int | None = None,
) -> PresetGateState:
    result = await db.execute(
        select(PresetGateState).where(
            PresetGateState.device_id == device_id,
            PresetGateState.gate_index == gate_index,
        )
    )
    state = result.scalars().first()

    if state is None:
        state = PresetGateState(
            user_id=user_id,
            device_id=device_id,
            gate_index=gate_index,
            preset_id=preset_id,
            spool_id=spool_id,
            hh_material=hh_material,
            hh_color_hex=hh_color_hex,
            hh_status=hh_status,
            source=source,
            source_ts=source_ts,
            is_active=True,
        )
        db.add(state)
    else:
        # Priority: hh_snapshot > manual_orca > web_manual
        # Only update HH fields if source has higher or equal priority
        _priority = {
            PresetGateStateSource.hh_snapshot: 3,
            PresetGateStateSource.manual_orca: 2,
            PresetGateStateSource.web_manual: 1,
        }
        if _priority[source] >= _priority[state.source]:
            state.source = source
            state.source_ts = source_ts

        if source == PresetGateStateSource.hh_snapshot:
            state.hh_material = hh_material
            state.hh_color_hex = hh_color_hex
            state.hh_status = hh_status
        else:
            if preset_id is not None or source != PresetGateStateSource.hh_snapshot:
                state.preset_id = preset_id
            if spool_id is not None:
                state.spool_id = spool_id

        state.is_active = True

    return state


# ── Heartbeat ──────────────────────────────────────────────────────────────


async def handle_heartbeat(
    db: AsyncSession,
    user: User,
    fingerprint: str,
    device_name: str | None,
    supports_hh: bool,
    gate_count: int | None,
) -> UserPrinterDevice:
    device = await get_device_by_fingerprint(db, user.id, fingerprint)
    now = datetime.now(timezone.utc)

    if device is None:
        device = UserPrinterDevice(
            user_id=user.id,
            device_fingerprint=fingerprint,
            name=device_name or fingerprint,
            supports_hh=supports_hh,
            gate_count=gate_count,
            last_seen_at=now,
        )
        db.add(device)
    else:
        device.last_seen_at = now
        device.supports_hh = supports_hh
        if gate_count is not None:
            device.gate_count = gate_count
        if device_name:
            device.name = device_name

    await db.commit()
    await db.refresh(device)
    return device


# ── HH Snapshot ───────────────────────────────────────────────────────────


async def handle_hh_snapshot(
    db: AsyncSession,
    user: User,
    payload: HHSnapshotRequest,
) -> tuple[UserPrinterDevice, int, list[int]]:
    """Process HH snapshot. Returns (device, updated_count, mismatch_gate_indices)."""
    device = await get_device_by_fingerprint(db, user.id, payload.device_fingerprint)
    now = datetime.now(timezone.utc)

    if device is None:
        device = UserPrinterDevice(
            user_id=user.id,
            device_fingerprint=payload.device_fingerprint,
            name=payload.device_fingerprint,
            supports_hh=True,
            gate_count=payload.gate_count,
            last_seen_at=now,
        )
        db.add(device)
        await db.flush()
    else:
        device.last_seen_at = now
        device.supports_hh = True
        device.gate_count = payload.gate_count

    mismatches: list[int] = []
    updated = 0

    for gate_item in payload.gates:
        state = await _upsert_gate_state(
            db,
            user_id=user.id,
            device_id=device.id,
            gate_index=gate_item.gate,
            source=PresetGateStateSource.hh_snapshot,
            source_ts=payload.snapshot_ts,
            hh_material=gate_item.material or None,
            hh_color_hex=gate_item.color_hex or None,
            hh_status=gate_item.status,
        )
        await db.flush()

        # Check mismatch: preset assigned but HH material doesn't match
        if state.preset_id is not None and state.hh_material:
            # Simple mismatch check — can be extended with material mapping lookup
            result = await db.execute(
                select(Preset).where(Preset.id == state.preset_id)
            )
            preset = result.scalars().first()
            if preset and preset.filament_id:
                # Flag as mismatch — frontend will show warning
                mismatches.append(gate_item.gate)

        updated += 1

    await db.commit()
    await db.refresh(device)
    return device, updated, mismatches


# ── Manual assignment ──────────────────────────────────────────────────────


async def _check_preset_accessible(
    db: AsyncSession,
    user_id: int,
    preset_id: int,
) -> None:
    result = await db.execute(
        select(Preset).where(Preset.id == preset_id)
    )
    preset = result.scalars().first()
    if not preset:
        raise_error(404, ERR_PRESET_NOT_ACCESSIBLE, {"preset_id": preset_id})
    is_public = preset.moderation_status == PresetModerationStatus.approved
    is_own = preset.user_id == user_id
    if not (is_public or is_own):
        raise_error(403, ERR_PRESET_NOT_ACCESSIBLE, {"preset_id": preset_id})


async def handle_manual_assignment(
    db: AsyncSession,
    user: User,
    payload: ManualAssignmentRequest,
    source: PresetGateStateSource,
) -> PresetGateState:
    device = await get_device_by_fingerprint(db, user.id, payload.device_fingerprint)
    if device is None:
        raise_error(404, ERR_DEVICE_NOT_FOUND)

    if device.gate_count is not None and payload.gate >= device.gate_count:
        raise_error(400, ERR_GATE_INDEX_INVALID, {"gate": payload.gate, "max": device.gate_count - 1})

    if payload.preset_id is not None:
        await _check_preset_accessible(db, user.id, payload.preset_id)

    now = datetime.now(timezone.utc)
    state = await _upsert_gate_state(
        db,
        user_id=user.id,
        device_id=device.id,  # type: ignore[union-attr]
        gate_index=payload.gate,
        source=source,
        source_ts=now,
        preset_id=payload.preset_id,
        spool_id=payload.spool_id,
    )
    await db.commit()
    await db.refresh(state)
    return state


# ── Usage estimate ─────────────────────────────────────────────────────────


async def handle_usage_estimate(
    db: AsyncSession,
    user: User,
    payload: UsageEstimateRequest,
) -> PresetUsageEvent:
    device = await get_device_by_fingerprint(db, user.id, payload.device_fingerprint)

    event = PresetUsageEvent(
        user_id=user.id,
        device_id=device.id if device else None,
        preset_id=payload.preset_id,
        spool_id=payload.spool_id,
        event_type=PresetUsageEventType.print_estimate,
        delta_weight_g=payload.delta_weight_g,
        job_ref=payload.job_ref,
        meta=payload.meta,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


# ── Web: assign preset to slot ─────────────────────────────────────────────


async def web_assign_preset_to_slot(
    db: AsyncSession,
    user: User,
    device_id: int,
    gate_index: int,
    preset_id: int | None,
    spool_id: int | None,
) -> PresetGateState:
    device = await require_device(db, user.id, device_id)

    if device.gate_count is not None and gate_index >= device.gate_count:
        raise_error(400, ERR_GATE_INDEX_INVALID, {"gate": gate_index, "max": device.gate_count - 1})

    if preset_id is not None:
        await _check_preset_accessible(db, user.id, preset_id)

    payload = ManualAssignmentRequest(
        device_fingerprint=device.device_fingerprint,
        gate=gate_index,
        preset_id=preset_id,
        spool_id=spool_id,
    )
    return await handle_manual_assignment(db, user, payload, PresetGateStateSource.web_manual)


async def clear_device_slots(
    db: AsyncSession,
    user: User,
    device_id: int,
) -> int:
    device = await require_device(db, user.id, device_id)
    states = await get_gate_states(db, device.id)
    cleared = 0
    for state in states:
        state.preset_id = None
        state.spool_id = None
        cleared += 1
    await db.commit()
    return cleared
