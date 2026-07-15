"""Business logic for preset slot sync (HH integration)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_DEVICE_NOT_FOUND,
    ERR_DEVICE_NOT_OWNER,
    ERR_GATE_INDEX_INVALID,
    ERR_PRESET_NOT_ACCESSIBLE,
    ERR_SPOOL_NOT_ACCESSIBLE,
    raise_error,
)
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.preset_slot_sync import (
    DeviceRegisterRequest,
    DeviceUpdateRequest,
    HHSnapshotRequest,
    ManualAssignmentRequest,
    UsageEstimateRequest,
)
from app.services.spool_service import (
    clear_spool_gate_assignments,
    clear_spool_location_projection,
    spool_has_gate_assignment,
)

logger = logging.getLogger(__name__)


def _normalize_utc(ts: datetime) -> datetime:
    """Normalize datetime to timezone-aware UTC for safe ordering comparisons."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


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
    return device


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


async def update_device(
    db: AsyncSession,
    user_id: int,
    device_id: int,
    payload: DeviceUpdateRequest,
) -> UserPrinterDevice:
    device = await require_device(db, user_id, device_id)
    if payload.name is not None:
        device.name = payload.name
    if payload.gate_count is not None:
        device.gate_count = payload.gate_count
    if payload.supports_hh is not None:
        device.supports_hh = payload.supports_hh
    if payload.printer_hostname is not None:
        device.printer_hostname = payload.printer_hostname
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
    preset_id_provided: bool = True,
    spool_id: int | None = None,
    spool_id_provided: bool = True,
    hh_material: str | None = None,
    hh_color_hex: str | None = None,
    hh_status: int | None = None,
) -> PresetGateState:
    bind = db.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""

    priority = {
        PresetGateStateSource.hh_snapshot: 3,
        PresetGateStateSource.manual_orca: 2,
        PresetGateStateSource.web_manual: 3,  # explicit user action always overrides
    }
    source_ts = _normalize_utc(source_ts)

    if dialect_name == "postgresql":
        insert_values: dict[str, object | None] = {
            "user_id": user_id,
            "device_id": device_id,
            "gate_index": gate_index,
            "preset_id": preset_id,
            "spool_id": spool_id,
            "hh_material": hh_material,
            "hh_color_hex": hh_color_hex,
            "hh_status": hh_status,
            "source": source,
            "source_ts": source_ts,
            "is_active": True,
        }

        stmt = pg_insert(PresetGateState).values(**insert_values)
        excluded = stmt.excluded

        incoming_priority = case(
            (excluded.source == PresetGateStateSource.hh_snapshot, 3),
            (excluded.source == PresetGateStateSource.web_manual, 3),
            (excluded.source == PresetGateStateSource.manual_orca, 2),
            else_=1,
        )
        current_priority = case(
            (PresetGateState.source == PresetGateStateSource.hh_snapshot, 3),
            (PresetGateState.source == PresetGateStateSource.web_manual, 3),
            (PresetGateState.source == PresetGateStateSource.manual_orca, 2),
            else_=1,
        )
        can_override = incoming_priority >= current_priority
        hh_ts_is_fresh = or_(
            excluded.source != PresetGateStateSource.hh_snapshot,
            excluded.source_ts > PresetGateState.source_ts,
        )

        update_values: dict[str, object] = {
            "user_id": excluded.user_id,
            "source": excluded.source,
            "source_ts": excluded.source_ts,
            "is_active": True,
            "hh_material": case(
                (excluded.source == PresetGateStateSource.hh_snapshot, excluded.hh_material),
                else_=PresetGateState.hh_material,
            ),
            "hh_color_hex": case(
                (excluded.source == PresetGateStateSource.hh_snapshot, excluded.hh_color_hex),
                else_=PresetGateState.hh_color_hex,
            ),
            "hh_status": case(
                (excluded.source == PresetGateStateSource.hh_snapshot, excluded.hh_status),
                else_=PresetGateState.hh_status,
            ),
        }

        if preset_id_provided:
            update_values["preset_id"] = excluded.preset_id
        if spool_id_provided:
            update_values["spool_id"] = excluded.spool_id

        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=[PresetGateState.device_id, PresetGateState.gate_index],
            set_=update_values,
            where=and_(can_override, hh_ts_is_fresh),
        ).returning(PresetGateState)

        result = await db.execute(upsert_stmt)
        state = result.scalars().first()
        if state is not None:
            return state

        existing_result = await db.execute(
            select(PresetGateState).where(
                PresetGateState.device_id == device_id,
                PresetGateState.gate_index == gate_index,
            )
        )
        existing = existing_result.scalars().first()
        if existing is None:
            raise RuntimeError("Failed to upsert gate state")
        return existing

    result = await db.execute(
        select(PresetGateState)
        .where(
            PresetGateState.device_id == device_id,
            PresetGateState.gate_index == gate_index,
        )
        .with_for_update()
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
        return state

    can_override = priority[source] >= priority[state.source]
    hh_ts_is_fresh = (
        source != PresetGateStateSource.hh_snapshot
        or _normalize_utc(source_ts) > _normalize_utc(state.source_ts)
    )

    if can_override and hh_ts_is_fresh:
        state.source = source
        state.source_ts = source_ts

        if source == PresetGateStateSource.hh_snapshot:
            state.hh_material = hh_material
            state.hh_color_hex = hh_color_hex
            state.hh_status = hh_status
        else:
            if preset_id_provided:
                state.preset_id = preset_id
            if spool_id_provided:
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

    snapshot_ts = _normalize_utc(payload.snapshot_ts)
    current_states = await get_gate_states(db, device.id)
    state_by_gate = {s.gate_index: s for s in current_states}

    updated = 0
    gate_state_updates: list[tuple[int, PresetGateState]] = []

    for gate_item in payload.gates:
        prev_state = state_by_gate.get(gate_item.gate)
        if prev_state is not None:
            prev_ts = _normalize_utc(prev_state.source_ts)
            if snapshot_ts <= prev_ts:
                # Ignore out-of-order HH snapshots, keep freshest known gate state.
                continue

        state = await _upsert_gate_state(
            db,
            user_id=user.id,
            device_id=device.id,
            gate_index=gate_item.gate,
            source=PresetGateStateSource.hh_snapshot,
            source_ts=snapshot_ts,
            preset_id_provided=False,
            spool_id_provided=False,
            hh_material=gate_item.material or None,
            hh_color_hex=gate_item.color_hex or None,
            hh_status=gate_item.status,
        )
        await db.flush()
        state_by_gate[gate_item.gate] = state
        gate_state_updates.append((gate_item.gate, state))

        updated += 1

    # Check mismatches in a single query (avoid N+1 by gate).
    mismatches: list[int] = []
    preset_ids_for_check = {
        state.preset_id
        for _, state in gate_state_updates
        if state.preset_id is not None and state.hh_material
    }
    preset_material_types: dict[int, str | None] = {}
    if preset_ids_for_check:
        preset_result = await db.execute(
            select(Preset.id, Filament.material_type)
            .select_from(Preset)
            .join(Filament, Preset.filament_id == Filament.id, isouter=True)
            .where(Preset.id.in_(preset_ids_for_check))
        )
        preset_material_types = dict(preset_result.all())

    for gate_index, state in gate_state_updates:
        if state.preset_id is None or not state.hh_material:
            continue
        preset_material = (preset_material_types.get(state.preset_id) or "").strip().upper()
        hh_material = state.hh_material.strip().upper()
        if preset_material and hh_material and preset_material != hh_material:
            mismatches.append(gate_index)

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
    is_public = preset.moderation_status == PresetModerationStatus.APPROVED
    is_own = preset.user_id == user_id
    if not (is_public or is_own):
        raise_error(403, ERR_PRESET_NOT_ACCESSIBLE, {"preset_id": preset_id})


async def _check_spool_accessible(
    db: AsyncSession,
    user_id: int,
    spool_id: int,
    *,
    require_usable: bool = False,
) -> UserSpool:
    result = await db.execute(
        select(UserSpool).where(
            UserSpool.id == spool_id,
            UserSpool.user_id == user_id,
        )
    )
    spool = result.scalars().first()
    if (
        spool is None
        or (
            require_usable
            and (
                spool.remaining_weight_g <= 0
                or spool.state in {UserSpoolState.archived, UserSpoolState.empty}
            )
        )
    ):
        raise_error(404, ERR_SPOOL_NOT_ACCESSIBLE, {"spool_id": spool_id})
    return spool


async def handle_manual_assignment(
    db: AsyncSession,
    user: User,
    payload: ManualAssignmentRequest,
    source: PresetGateStateSource,
    *,
    device: UserPrinterDevice | None = None,
    preset_id_provided: bool | None = None,
    spool_id_provided: bool | None = None,
) -> PresetGateState:
    resolved_device = device
    if resolved_device is None:
        resolved_device = await get_device_by_fingerprint(
            db, user.id, payload.device_fingerprint
        )
        if resolved_device is None:
            raise_error(404, ERR_DEVICE_NOT_FOUND)
    elif resolved_device.user_id != user.id:
        raise_error(403, ERR_DEVICE_NOT_OWNER)

    if resolved_device.gate_count is not None and payload.gate >= resolved_device.gate_count:
        raise_error(
            400,
            ERR_GATE_INDEX_INVALID,
            {"gate": payload.gate, "max": resolved_device.gate_count - 1},
        )

    if payload.preset_id is not None:
        await _check_preset_accessible(db, user.id, payload.preset_id)

    new_spool: UserSpool | None = None
    if payload.spool_id is not None:
        new_spool = await _check_spool_accessible(
            db,
            user.id,
            payload.spool_id,
            require_usable=True,
        )

    if preset_id_provided is None:
        preset_id_provided = "preset_id" in payload.model_fields_set
    if spool_id_provided is None:
        spool_id_provided = "spool_id" in payload.model_fields_set

    # Capture old spool at this gate before upsert (to clear its HH extra fields later)
    old_spool_id: int | None = None
    old_spool: UserSpool | None = None
    if spool_id_provided:
        old_spool_row = await db.execute(
            select(PresetGateState.spool_id).where(
                PresetGateState.device_id == resolved_device.id,
                PresetGateState.gate_index == payload.gate,
            )
        )
        old_spool_id = old_spool_row.scalar_one_or_none()
        if old_spool_id is not None and old_spool_id != payload.spool_id:
            old_spool_result = await db.execute(
                select(UserSpool).where(UserSpool.id == old_spool_id)
            )
            old_spool = old_spool_result.scalars().first()

    now = datetime.now(timezone.utc)
    if new_spool is not None:
        await clear_spool_gate_assignments(
            db,
            new_spool,
            source=source,
            except_device_id=resolved_device.id,
            except_gate_index=payload.gate,
        )

    state = await _upsert_gate_state(
        db,
        user_id=user.id,
        device_id=resolved_device.id,
        gate_index=payload.gate,
        source=source,
        source_ts=now,
        preset_id=payload.preset_id,
        preset_id_provided=preset_id_provided,
        spool_id=payload.spool_id,
        spool_id_provided=spool_id_provided,
    )
    await db.flush()

    # Sync spool.extra with HH-format fields so HH can read gate assignments from GET /spool
    # HH reads: json.loads(extra.get('printer_name', '""')) and int(extra.get('mmu_gate_map', -1))
    if spool_id_provided:
        new_spool_id = state.spool_id
        if old_spool_id != new_spool_id and old_spool is not None:
            if not await spool_has_gate_assignment(db, old_spool.id):
                extra = dict(old_spool.extra or {})
                extra["printer_name"] = json.dumps("")
                extra["mmu_gate_map"] = json.dumps(-1)
                old_spool.extra = extra
                if old_spool.state not in {UserSpoolState.archived, UserSpoolState.empty}:
                    old_spool.state = UserSpoolState.shelf
            logger.debug(
                "Cleared HH extra fields on spool %d (unassigned from gate %d)",
                old_spool_id,
                payload.gate,
            )

        # Set HH fields and active state even when re-applying the same assignment.
        if new_spool_id is not None:
            if new_spool is None or new_spool.id != new_spool_id:
                new_spool_row = await db.execute(
                    select(UserSpool).where(UserSpool.id == new_spool_id)
                )
                new_spool = new_spool_row.scalars().first()
            if new_spool is not None:
                extra = dict(new_spool.extra or {})
                extra["printer_name"] = json.dumps(resolved_device.name)
                extra["mmu_gate_map"] = json.dumps(payload.gate)
                new_spool.extra = extra
                new_spool.state = UserSpoolState.active
                logger.debug(
                    "Set HH extra fields on spool %d: printer=%r gate=%d",
                    new_spool_id,
                    resolved_device.name,
                    payload.gate,
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

    if payload.spool_id is not None:
        await _check_spool_accessible(db, user.id, payload.spool_id)

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
    *,
    preset_id_provided: bool = True,
    spool_id_provided: bool = True,
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
    return await handle_manual_assignment(
        db,
        user,
        payload,
        PresetGateStateSource.web_manual,
        device=device,
        preset_id_provided=preset_id_provided,
        spool_id_provided=spool_id_provided,
    )


async def clear_device_slots(
    db: AsyncSession,
    user: User,
    device_id: int,
) -> int:
    device = await require_device(db, user.id, device_id)
    now = _normalize_utc(datetime.now(timezone.utc))
    spool_ids_result = await db.execute(
        select(PresetGateState.spool_id).where(
            PresetGateState.device_id == device.id,
            PresetGateState.spool_id.is_not(None),
        )
    )
    spool_ids = {spool_id for spool_id in spool_ids_result.scalars().all() if spool_id is not None}
    result = await db.execute(
        update(PresetGateState)
        .where(PresetGateState.device_id == device.id)
        .values(
            preset_id=None,
            spool_id=None,
            source=PresetGateStateSource.web_manual,
            source_ts=now,
            is_active=True,
        )
    )
    await db.flush()

    if spool_ids:
        spools_result = await db.execute(
            select(UserSpool).where(
                UserSpool.id.in_(spool_ids),
                UserSpool.user_id == user.id,
            )
        )
        for spool in spools_result.scalars().all():
            if await spool_has_gate_assignment(db, spool.id):
                continue
            clear_spool_location_projection(spool)
            if spool.state not in {UserSpoolState.archived, UserSpoolState.empty}:
                spool.state = UserSpoolState.shelf

    await db.commit()
    return int(result.rowcount or 0)
