"""Business logic for preset slot sync (HH integration)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import and_, case, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_DEVICE_NOT_FOUND,
    ERR_DEVICE_NOT_OWNER,
    ERR_GATE_INDEX_INVALID,
    ERR_MATERIAL_SYSTEM_NOT_FOUND,
    ERR_MATERIAL_TOPOLOGY_CHANGED,
    ERR_SPOOL_LOCATION_CONFLICT,
    raise_error,
)
from app.models.filament import Filament
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, MaterialSystem
from app.models.preset import Preset
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.preset_slot_sync import (
    DeviceRegisterRequest,
    DeviceUpdateRequest,
    HHExpectedAssignment,
    HHReconciliationDifference,
    HHReconciliationImportChange,
    HHReconciliationRequest,
    HHReconciliationResponse,
    HHReconciliationUnresolved,
    HHSnapshotRequest,
    ManualAssignmentRequest,
    PluginMaterialSlotContext,
    PluginMaterialSystemContext,
    PluginMaterialTopologyContextResponse,
    PluginPhysicalPrinterContext,
    UsageEstimateRequest,
)
from app.services.material_assignment_service import (
    require_accessible_preset,
    require_accessible_spool,
)
from app.services.material_contract_service import (
    ensure_material_topology,
    list_physical_printers,
    require_physical_printer,
)
from app.services.physical_printer_discovery_service import list_user_bindings
from app.services.spool_service import (
    clear_spool_gate_assignments,
    lock_material_slots_for_spools,
    lock_spool_row,
    material_slot_ids_for_gate,
    set_spool_location_projection,
    shelf_spool_if_unassigned,
)

logger = logging.getLogger(__name__)


def _normalize_utc(ts: datetime) -> datetime:
    """Normalize datetime to timezone-aware UTC for safe ordering comparisons."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


# ── Device helpers ─────────────────────────────────────────────────────────


def touch_device_last_seen(device: UserPrinterDevice) -> None:
    """Record the adapter's last successful contact with the backend.

    Presence semantics: this timestamp only says the plugin/adapter talked to
    FilamentHub recently — it is NOT the printer's power or online state.
    """
    device.last_seen_at = datetime.now(timezone.utc)


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


async def claim_printer_hostname(
    db: AsyncSession, device: UserPrinterDevice, hostname: str
) -> None:
    """Give a hostname to one device and take it from any other."""
    if device.printer_hostname == hostname:
        return
    previous = (
        await db.execute(
            select(UserPrinterDevice)
            .where(
                UserPrinterDevice.user_id == device.user_id,
                UserPrinterDevice.printer_hostname == hostname,
                UserPrinterDevice.id != device.id,
            )
            .order_by(UserPrinterDevice.id)
            .with_for_update()
        )
    ).scalars().all()
    for other in previous:
        other.printer_hostname = None
        logger.info(
            "Printer hostname moved from device id=%s to id=%s", other.id, device.id
        )
    if previous:
        await db.flush()
    device.printer_hostname = hostname


async def register_or_update_device(
    db: AsyncSession,
    user: User,
    payload: DeviceRegisterRequest,
) -> UserPrinterDevice:
    device = await get_device_by_fingerprint(db, user.id, payload.device_fingerprint)

    if device is None:
        device = UserPrinterDevice(
            user_id=user.id,
            device_fingerprint=payload.device_fingerprint,
            name=payload.name,
            printer_id=payload.printer_id,
            supports_hh=payload.supports_hh,
            gate_count=payload.gate_count,
        )
        db.add(device)
    else:
        device.name = payload.name
        if payload.printer_id is not None:
            device.printer_id = payload.printer_id
        device.supports_hh = payload.supports_hh
        if payload.gate_count is not None:
            device.gate_count = payload.gate_count
    touch_device_last_seen(device)

    await ensure_material_topology(db, device)
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
        await claim_printer_hostname(db, device, payload.printer_hostname)
    await ensure_material_topology(db, device)
    await db.commit()
    await db.refresh(device)
    return device


async def list_user_devices(
    db: AsyncSession,
    user_id: int,
) -> list[UserPrinterDevice]:
    result = await db.execute(
        select(UserPrinterDevice).where(
            UserPrinterDevice.user_id == user_id,
            UserPrinterDevice.device_fingerprint.is_not(None),
        )
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


async def _lock_material_gate_slots(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    gate_indices: set[int],
) -> None:
    """Lock stable gate routes before a legacy gate-row mutation."""
    if not gate_indices:
        return
    await db.execute(
        select(MaterialSlot.id)
        .join(MaterialSystem, MaterialSystem.id == MaterialSlot.material_system_id)
        .where(
            MaterialSlot.user_id == user_id,
            MaterialSlot.provider_index.in_(gate_indices),
            MaterialSystem.user_id == user_id,
            MaterialSystem.physical_printer_id == physical_printer_id,
        )
        .order_by(MaterialSlot.id)
        .with_for_update()
    )


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
        PresetGateStateSource.provider_report: 3,
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
            (excluded.source == PresetGateStateSource.provider_report, 3),
            (excluded.source == PresetGateStateSource.manual_orca, 2),
            else_=1,
        )
        current_priority = case(
            (PresetGateState.source == PresetGateStateSource.hh_snapshot, 3),
            (PresetGateState.source == PresetGateStateSource.web_manual, 3),
            (PresetGateState.source == PresetGateStateSource.provider_report, 3),
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

        # The legacy gate may already be present in this session through the
        # material-slot relationship. Refresh that identity from RETURNING;
        # otherwise SQLAlchemy can hand the caller the pre-upsert values and
        # the topology mirror writes the old assignment back immediately.
        result = await db.execute(
            upsert_stmt.execution_options(populate_existing=True)
        )
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

    if device is None:
        device = UserPrinterDevice(
            user_id=user.id,
            device_fingerprint=fingerprint,
            name=device_name or fingerprint,
            supports_hh=supports_hh,
            gate_count=gate_count,
        )
        db.add(device)
    else:
        device.supports_hh = supports_hh
        if gate_count is not None:
            device.gate_count = gate_count
        if device_name:
            device.name = device_name
    touch_device_last_seen(device)

    await ensure_material_topology(db, device)
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
    device = (
        await require_device(db, user.id, payload.physical_printer_id)
        if payload.physical_printer_id is not None
        else await get_device_by_fingerprint(db, user.id, payload.device_fingerprint or "")
    )

    if device is None:
        assert payload.device_fingerprint is not None
        device = UserPrinterDevice(
            user_id=user.id,
            device_fingerprint=payload.device_fingerprint,
            name=payload.device_fingerprint,
            supports_hh=True,
            gate_count=payload.gate_count,
        )
        db.add(device)
        await db.flush()
    else:
        device.supports_hh = True
        device.gate_count = payload.gate_count
    device.reports_feed = True
    touch_device_last_seen(device)

    # Desired assignment writers lock stable slots before touching the legacy
    # gate row.  Establish and lock the complete topology first so an HH
    # observation cannot deadlock with a concurrent user assignment while it
    # updates the observation fields on that same legacy row.
    await ensure_material_topology(
        db,
        device,
        gate_indices={item.gate for item in payload.gates},
        exact_gate_count=payload.gate_count,
    )
    await _lock_material_gate_slots(
        db,
        user_id=user.id,
        physical_printer_id=device.id,
        gate_indices=set(range(payload.gate_count)),
    )

    snapshot_ts = _normalize_utc(payload.snapshot_ts)
    current_states = await get_gate_states(db, device.id)
    state_by_gate = {s.gate_index: s for s in current_states}

    updated = 0
    gate_state_updates: list[tuple[int, PresetGateState]] = []

    # An explicit empty gates list is a fresh observation: the MMU reports that
    # no gate holds filament. Reflect it in the observed hh_* fields of every
    # known gate (same out-of-order guard as per-gate items); the desired
    # assignment (preset_id/spool_id) is intentionally untouched and no rows
    # are deleted — freshness/cleanup policy is a later slice.
    if not payload.gates:
        for gate_index, prev_state in sorted(state_by_gate.items()):
            prev_ts = _normalize_utc(prev_state.source_ts)
            if snapshot_ts <= prev_ts:
                continue
            state = await _upsert_gate_state(
                db,
                user_id=user.id,
                device_id=device.id,
                gate_index=gate_index,
                source=PresetGateStateSource.hh_snapshot,
                source_ts=snapshot_ts,
                preset_id_provided=False,
                spool_id_provided=False,
                hh_material=None,
                hh_color_hex=None,
                hh_status=0,
            )
            await db.flush()
            state_by_gate[gate_index] = state
            updated += 1

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

    await ensure_material_topology(
        db,
        device,
        gate_indices={state.gate_index for _, state in gate_state_updates}
        | set(state_by_gate),
        exact_gate_count=payload.gate_count,
    )
    await db.commit()
    await db.refresh(device)
    return device, updated, mismatches


async def build_plugin_material_topology_context(
    db: AsyncSession,
    user_id: int,
    source_instance_id: str,
) -> PluginMaterialTopologyContextResponse:
    """Return only the local bindings and desired slots a plugin needs.

    A machine profile is configuration, not physical identity.  The stable
    ``(source_instance_id, connection_ref)`` binding created by printer sync is
    therefore the only automatic route from a local Orca connection to a
    FilamentHub physical printer.  Endpoints, credentials, names and unrelated
    account data deliberately never cross this capability boundary.
    """
    printers = await list_physical_printers(db, user_id)
    bindings = await list_user_bindings(db, user_id)
    refs_by_printer: dict[int, set[str]] = {}
    for binding in bindings:
        if (
            binding.source_instance_id == source_instance_id
            and binding.connection_ref
        ):
            refs_by_printer.setdefault(binding.physical_printer_id, set()).add(
                binding.connection_ref
            )

    result: list[PluginPhysicalPrinterContext] = []
    for printer in printers:
        systems: list[PluginMaterialSystemContext] = []
        for system in sorted(printer.material_systems, key=lambda item: item.id):
            if not system.active or system.provider not in {"happy_hare", "bambu"}:
                continue
            if system.provider == "bambu" and not any(
                connector.active
                and connector.provider == "bambu"
                and connector.transport == "orca_plugin_lan"
                and connector.material_system_id == system.id
                and connector.source_instance_id == source_instance_id
                for connector in printer.connectors
            ):
                continue
            slots: list[PluginMaterialSlotContext] = []
            for slot in sorted(
                system.slots, key=lambda item: (item.provider_index, item.id)
            ):
                if not slot.active:
                    continue
                preset_id = None
                spool_id = None
                source_ts = None
                if slot.assignment is not None and slot.assignment.active:
                    preset_id = slot.assignment.preset_id
                    spool_id = slot.assignment.spool_id
                    source_ts = slot.assignment.source_ts
                elif (
                    slot.legacy_gate_state is not None
                    and slot.legacy_gate_state.is_active
                ):
                    preset_id = slot.legacy_gate_state.preset_id
                    spool_id = slot.legacy_gate_state.spool_id
                    source_ts = slot.legacy_gate_state.source_ts
                slots.append(
                    PluginMaterialSlotContext(
                        material_slot_id=slot.id,
                        provider_index=slot.provider_index,
                        assignment_revision=slot.assignment_revision,
                        preset_id=preset_id,
                        spool_id=spool_id,
                        source_ts=source_ts,
                    )
                )
            systems.append(
                PluginMaterialSystemContext(
                    id=system.id,
                    provider=system.provider,
                    slots=slots,
                )
            )
        if systems:
            result.append(
                PluginPhysicalPrinterContext(
                    id=printer.id,
                    connection_refs=sorted(refs_by_printer.get(printer.id, set())),
                    material_systems=systems,
                )
            )

    return PluginMaterialTopologyContextResponse(
        source_instance_id=source_instance_id,
        printers=result,
    )


def _decode_spool_extra(extra: dict | None, key: str) -> object | None:
    if not extra or key not in extra:
        return None
    value = extra[key]
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


async def _require_hh_reconciliation_target(
    db: AsyncSession,
    user_id: int,
    payload: HHReconciliationRequest,
) -> tuple[UserPrinterDevice, MaterialSystem]:
    printer = await require_physical_printer(db, user_id, payload.physical_printer_id)
    bound = await db.scalar(
        select(PrinterConnectionBinding.id).where(
            PrinterConnectionBinding.user_id == user_id,
            PrinterConnectionBinding.physical_printer_id == printer.id,
            PrinterConnectionBinding.source_instance_id == payload.source_instance_id,
            PrinterConnectionBinding.connection_ref == payload.connection_ref,
        )
    )
    if bound is None:
        raise_error(403, ERR_DEVICE_NOT_OWNER)

    system = next(
        (
            item
            for item in printer.material_systems
            if item.id == payload.material_system_id
            and item.user_id == user_id
            and item.active
            and item.provider == "happy_hare"
        ),
        None,
    )
    if system is None:
        raise_error(404, ERR_MATERIAL_SYSTEM_NOT_FOUND)
    if printer.gate_count is not None and payload.gate_count != printer.gate_count:
        raise_error(
            400,
            ERR_GATE_INDEX_INVALID,
            {"gate": payload.gate_count - 1, "max": printer.gate_count - 1},
        )
    return printer, system


async def build_hh_reconciliation_preview(
    db: AsyncSession,
    user: User,
    payload: HHReconciliationRequest,
) -> HHReconciliationResponse:
    """Build a user-confirmable bridge between observed and desired HH state.

    Positive provider spool IDs are accepted only when they belong to this
    user. If Happy Hare lost its ID but still reports filament in a gate, one
    exact unassigned last-location hint may be proposed. A hint is never applied
    automatically and colour/material similarity is deliberately ignored.
    """
    printer, system = await _require_hh_reconciliation_target(
        db, user.id, payload
    )
    slots_by_gate = {
        slot.provider_index: slot
        for slot in system.slots
        if slot.active and 0 <= slot.provider_index < payload.gate_count
    }
    desired: dict[int, int | None] = {}
    for gate in range(payload.gate_count):
        slot = slots_by_gate.get(gate)
        spool_id = None
        if slot is not None and slot.assignment is not None and slot.assignment.active:
            spool_id = slot.assignment.spool_id
        elif (
            slot is not None
            and slot.legacy_gate_state is not None
            and slot.legacy_gate_state.is_active
        ):
            spool_id = slot.legacy_gate_state.spool_id
        desired[gate] = spool_id

    actual_by_gate = {item.gate: item.spool_id for item in payload.gates}
    status_by_gate = {item.gate: int(item.status) for item in payload.gates}
    positive_ids = {
        spool_id for spool_id in actual_by_gate.values() if spool_id is not None
    }
    usable_by_id: dict[int, UserSpool] = {}
    if positive_ids:
        usable_spools = list(
            (
                await db.execute(
                    select(UserSpool).where(
                        UserSpool.id.in_(positive_ids),
                        UserSpool.user_id == user.id,
                        UserSpool.state.not_in(
                            {UserSpoolState.archived, UserSpoolState.empty}
                        ),
                        UserSpool.initial_weight_g > UserSpool.used_weight_g,
                    )
                )
            ).scalars()
        )
        usable_by_id = {spool.id: spool for spool in usable_spools}

    actual_counts: dict[int, int] = {}
    for spool_id in actual_by_gate.values():
        if spool_id is not None:
            actual_counts[spool_id] = actual_counts.get(spool_id, 0) + 1

    assigned_spool_ids = {
        spool_id
        for spool_id in (
            await db.execute(
                select(PresetGateState.spool_id).where(
                    PresetGateState.user_id == user.id,
                    PresetGateState.spool_id.is_not(None),
                )
            )
        ).scalars()
        if spool_id is not None
    }
    assigned_spool_ids.update(
        spool_id
        for spool_id in (
            await db.execute(
                select(MaterialSlotAssignment.spool_id).where(
                    MaterialSlotAssignment.user_id == user.id,
                    MaterialSlotAssignment.spool_id.is_not(None),
                    MaterialSlotAssignment.active.is_(True),
                )
            )
        ).scalars()
        if spool_id is not None
    )

    previous_by_gate: dict[int, list[int]] = {}
    location_names = {
        name for name in (printer.printer_hostname, printer.name) if name
    }
    if location_names:
        previous_spools = list(
            (
                await db.execute(
                    select(UserSpool).where(
                        UserSpool.user_id == user.id,
                        UserSpool.extra.is_not(None),
                        UserSpool.state.not_in(
                            {UserSpoolState.archived, UserSpoolState.empty}
                        ),
                        UserSpool.initial_weight_g > UserSpool.used_weight_g,
                    )
                )
            ).scalars()
        )
        for spool in previous_spools:
            if spool.id in assigned_spool_ids:
                continue
            last_printer = _decode_spool_extra(spool.extra, "fhub_last_printer")
            last_gate = _decode_spool_extra(spool.extra, "fhub_last_gate")
            try:
                gate = int(last_gate) if last_gate is not None else -1
            except (TypeError, ValueError):
                continue
            if last_printer in location_names and 0 <= gate < payload.gate_count:
                previous_by_gate.setdefault(gate, []).append(spool.id)

    printer_changes: list[HHReconciliationDifference] = []
    imports: list[HHReconciliationImportChange] = []
    unresolved: list[HHReconciliationUnresolved] = []
    for gate in range(payload.gate_count):
        actual = actual_by_gate.get(gate)
        wanted = desired[gate]
        if payload.spool_ids_known and actual != wanted:
            printer_changes.append(
                HHReconciliationDifference(
                    gate=gate,
                    actual_spool_id=actual,
                    desired_spool_id=wanted,
                )
            )

        if actual is not None:
            if actual_counts.get(actual, 0) > 1:
                unresolved.append(
                    HHReconciliationUnresolved(gate=gate, reason="duplicate_spool")
                )
            elif actual not in usable_by_id:
                unresolved.append(
                    HHReconciliationUnresolved(gate=gate, reason="spool_unavailable")
                )
            elif actual != wanted:
                imports.append(
                    HHReconciliationImportChange(
                        gate=gate,
                        proposed_spool_id=actual,
                        desired_spool_id=wanted,
                        source="provider",
                    )
                )
            continue

        # HH status describes the filament path, not whether a physical spool
        # remains assigned to the gate. Never clear desired state from it.
        if status_by_gate.get(gate) not in {1, 2} or wanted is not None:
            continue
        candidates = previous_by_gate.get(gate, [])
        if len(candidates) == 1:
            imports.append(
                HHReconciliationImportChange(
                    gate=gate,
                    proposed_spool_id=candidates[0],
                    desired_spool_id=None,
                    source="last_known",
                )
            )
        else:
            unresolved.append(
                HHReconciliationUnresolved(
                    gate=gate,
                    reason=(
                        "ambiguous_last_known" if len(candidates) > 1 else "identity_unknown"
                    ),
                )
            )

    return HHReconciliationResponse(
        printer_changes=printer_changes,
        import_changes=imports,
        unresolved=unresolved,
        desired_assignments=[
            HHExpectedAssignment(gate=gate, spool_id=desired[gate])
            for gate in range(payload.gate_count)
        ],
    )


async def adopt_hh_reconciliation(
    db: AsyncSession,
    user: User,
    payload: HHReconciliationRequest,
) -> HHReconciliationResponse:
    """Atomically accept the explicitly previewed provider-side proposals."""
    preview = await build_hh_reconciliation_preview(db, user, payload)
    if payload.expected_desired is None:
        raise_error(409, ERR_MATERIAL_TOPOLOGY_CHANGED)
    expected = {item.gate: item.spool_id for item in payload.expected_desired}
    current = {item.gate: item.spool_id for item in preview.desired_assignments}
    if expected != current:
        raise_error(409, ERR_MATERIAL_TOPOLOGY_CHANGED)

    # Follow the shared writer's lock order: physical spools first, then slot
    # rows. This prevents a last-known hint from stealing a spool that was moved
    # after the preview and keeps the full-map CAS atomic on PostgreSQL.
    lock_ids = {
        item.proposed_spool_id for item in preview.import_changes
    }
    lock_ids.update(
        item.spool_id
        for item in preview.desired_assignments
        if item.spool_id is not None
    )
    for spool_id in sorted(lock_ids):
        await lock_spool_row(db, spool_id)
    await db.execute(
        select(MaterialSlot)
        .where(MaterialSlot.material_system_id == payload.material_system_id)
        .order_by(MaterialSlot.id)
        .with_for_update()
    )
    await db.execute(
        select(PresetGateState)
        .where(PresetGateState.device_id == payload.physical_printer_id)
        .order_by(PresetGateState.gate_index)
        .with_for_update()
    )
    confirmed = await build_hh_reconciliation_preview(db, user, payload)
    confirmed_current = {
        item.gate: item.spool_id for item in confirmed.desired_assignments
    }
    preview_proposals = {
        (item.gate, item.proposed_spool_id, item.source)
        for item in preview.import_changes
    }
    confirmed_proposals = {
        (item.gate, item.proposed_spool_id, item.source)
        for item in confirmed.import_changes
    }
    if confirmed_current != expected or confirmed_proposals != preview_proposals:
        raise_error(409, ERR_MATERIAL_TOPOLOGY_CHANGED)

    printer = await require_device(db, user.id, payload.physical_printer_id)
    for change in sorted(confirmed.import_changes, key=lambda item: item.gate):
        await handle_manual_assignment(
            db,
            user,
            ManualAssignmentRequest(
                device_fingerprint=printer.device_fingerprint
                or f"logical:{printer.logical_id}",
                gate=change.gate,
                spool_id=change.proposed_spool_id,
            ),
            PresetGateStateSource.web_manual,
            device=printer,
            preset_id_provided=False,
            spool_id_provided=True,
            commit=False,
        )
    await db.commit()
    confirmed.adopted_gates = len(confirmed.import_changes)
    return confirmed


# ── Manual assignment ──────────────────────────────────────────────────────


async def handle_manual_assignment(
    db: AsyncSession,
    user: User,
    payload: ManualAssignmentRequest,
    source: PresetGateStateSource,
    *,
    device: UserPrinterDevice | None = None,
    preset_id_provided: bool | None = None,
    spool_id_provided: bool | None = None,
    commit: bool = True,
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
        await require_accessible_preset(db, user.id, payload.preset_id)

    if preset_id_provided is None:
        preset_id_provided = "preset_id" in payload.model_fields_set
    if spool_id_provided is None:
        spool_id_provided = "spool_id" in payload.model_fields_set

    # Capture both physical identities before taking locks, then follow the
    # shared order: all involved spools, stable slot, legacy gate row.
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

    new_spool: UserSpool | None = None
    if payload.spool_id is not None:
        new_spool = await require_accessible_spool(
            db,
            user.id,
            payload.spool_id,
            require_usable=True,
        )
    involved_spool_ids = {
        spool_id
        for spool_id in {old_spool_id, payload.spool_id}
        if spool_id is not None
    }
    for spool_id in sorted(involved_spool_ids):
        await lock_spool_row(db, spool_id)

    await ensure_material_topology(
        db,
        resolved_device,
        gate_indices={payload.gate},
        sync_legacy_assignments=False,
    )
    target_material_slot_ids = await material_slot_ids_for_gate(
        db,
        device_id=resolved_device.id,
        gate_index=payload.gate,
    )
    await lock_material_slots_for_spools(
        db,
        involved_spool_ids,
        additional_material_slot_ids=target_material_slot_ids,
    )

    now = datetime.now(timezone.utc)
    if new_spool is not None:
        await clear_spool_gate_assignments(
            db,
            new_spool,
            source=source,
            except_device_id=resolved_device.id,
            except_gate_index=payload.gate,
            except_material_slot_id=min(target_material_slot_ids, default=None),
        )
        # Old bindings must hit the DB before the new one to satisfy the
        # single-location unique index within the transaction.
        await db.flush()

    try:
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
    except IntegrityError:
        raise_error(409, ERR_SPOOL_LOCATION_CONFLICT)

    await ensure_material_topology(
        db, resolved_device, gate_indices={payload.gate}
    )
    # Production sessions disable autoflush. Persist the mirrored assignment
    # deletion before asking whether the old spool is still mounted anywhere.
    await db.flush()

    # Sync spool.extra with HH-format fields so HH can read gate assignments from GET /spool
    # HH reads: json.loads(extra.get('printer_name', '""')) and int(extra.get('mmu_gate_map', -1))
    if spool_id_provided:
        new_spool_id = state.spool_id
        if old_spool_id != new_spool_id and old_spool is not None:
            await shelf_spool_if_unassigned(db, old_spool)
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
                set_spool_location_projection(new_spool, resolved_device, payload.gate)
                new_spool.state = UserSpoolState.active
                logger.debug(
                    "Set HH extra fields on spool %d: printer_device_id=%s gate=%d",
                    new_spool_id,
                    resolved_device.id,
                    payload.gate,
                )

    if commit:
        await db.commit()
        await db.refresh(state)
    else:
        await db.flush()

    return state


# ── Usage estimate ─────────────────────────────────────────────────────────


async def handle_usage_estimate(
    db: AsyncSession,
    user: User,
    payload: UsageEstimateRequest,
) -> PresetUsageEvent:
    device = await get_device_by_fingerprint(db, user.id, payload.device_fingerprint)

    if payload.spool_id is not None:
        await require_accessible_spool(db, user.id, payload.spool_id)

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
