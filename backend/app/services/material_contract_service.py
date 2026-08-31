"""Physical-printer and provider-neutral material contract services."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_DEVICE_NOT_FOUND,
    ERR_MATERIAL_ASSIGNMENT_CONFLICT,
    ERR_MATERIAL_SLOT_IN_USE,
    ERR_MATERIAL_SYSTEM_EXISTS,
    ERR_MATERIAL_SYSTEM_NOT_FOUND,
    ERR_PRINTER_BRIDGE_UNAUTHORIZED,
    ERR_PRINTER_NOT_FOUND,
    ERR_PRINTER_PROFILE_NOT_FOUND,
    raise_error,
)
from app.core.security import device_inventory_digest
from app.models.filament import Filament
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import (
    MaterialSlot,
    MaterialSystem,
    PhysicalPrinterConnector,
)
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.preset_gate_state import PresetGateState
from app.models.print_job import PrintJob
from app.models.printer import Printer
from app.models.printer_bridge_observation import (
    MaterialSlotObservation,
    PhysicalPrinterStatusObservation,
)
from app.models.printer_profile import PrinterProfile
from app.models.spool_tag import SpoolTag
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.schemas.material_contract import (
    MaterialSlotCreate,
    MaterialSystemCreate,
    MaterialSystemUpdate,
    PhysicalPrinterConfigurationsUpdate,
    PhysicalPrinterConnectorCreate,
    PhysicalPrinterCreate,
    PhysicalPrinterUpdate,
    PrinterBridgeSnapshotRequest,
    PrinterBridgeSnapshotResponse,
)
from app.schemas.printer_bridge import (
    PrinterBridgeDesiredPresetSnapshot,
    PrinterBridgeDesiredSlotSnapshot,
    PrinterBridgeDesiredSnapshotResponse,
    PrinterBridgeDesiredSpoolSnapshot,
)
from app.services.material_assignment_service import sync_legacy_material_assignment

# Happy Hare and the plain Klipper adapter describe the same feed, so they share
# one system on the printer instead of each creating its own.
KLIPPER_PROVIDERS = ("happy_hare", "legacy")

MAX_GATE_INDEX = 255

HAPPY_HARE_CAPABILITIES = [
    "read",
    "write",
    "presence",
    "spool_identity",
    "consumption",
]

# Happy Hare gates occupy 0..255. The provider-neutral material contract allows
# indices through 1023, so the last value is a stable local identity for the
# optional direct bypass route and can never collide with a real HH gate.
HAPPY_HARE_BYPASS_PROVIDER_INDEX = 1023
DEFAULT_DENSITY_G_CM3 = 1.24
DEFAULT_DIAMETER_MM = 1.75


def _printer_load_options():
    return (
        selectinload(UserPrinterDevice.profile_links),
        selectinload(UserPrinterDevice.material_systems)
        .selectinload(MaterialSystem.slots)
        .selectinload(MaterialSlot.legacy_gate_state),
        selectinload(UserPrinterDevice.material_systems)
        .selectinload(MaterialSystem.slots)
        .selectinload(MaterialSlot.assignment),
        selectinload(UserPrinterDevice.material_systems)
        .selectinload(MaterialSystem.slots)
        .selectinload(MaterialSlot.observations)
        .selectinload(MaterialSlotObservation.connector)
        .selectinload(PhysicalPrinterConnector.status_observation),
        selectinload(UserPrinterDevice.connectors).selectinload(
            PhysicalPrinterConnector.status_observation
        ),
    )


async def require_physical_printer(
    db: AsyncSession, user_id: int, physical_printer_id: int
) -> UserPrinterDevice:
    result = await db.execute(
        select(UserPrinterDevice)
        .where(
            UserPrinterDevice.id == physical_printer_id,
            UserPrinterDevice.user_id == user_id,
        )
        .options(*_printer_load_options())
        .execution_options(populate_existing=True)
    )
    printer = result.scalar_one_or_none()
    if printer is None:
        raise_error(404, ERR_DEVICE_NOT_FOUND)
    return printer


async def list_physical_printers(db: AsyncSession, user_id: int) -> list[UserPrinterDevice]:
    result = await db.execute(
        select(UserPrinterDevice)
        .where(UserPrinterDevice.user_id == user_id)
        .options(*_printer_load_options())
        .order_by(UserPrinterDevice.created_at, UserPrinterDevice.id)
    )
    return list(result.scalars().unique().all())


async def _validate_profile_ids(
    db: AsyncSession,
    user_id: int,
    profile_ids: list[int],
    *,
    active_only: bool = True,
) -> list[PrinterProfile]:
    if not profile_ids:
        return []
    query = select(PrinterProfile).where(
        PrinterProfile.id.in_(profile_ids),
        or_(
            PrinterProfile.owner_user_id == user_id,
            (PrinterProfile.owner_user_id.is_(None) & PrinterProfile.is_official.is_(True)),
        ),
    )
    if active_only:
        query = query.where(PrinterProfile.active.is_(True))
    result = await db.execute(query)
    profiles = list(result.scalars().all())
    if {profile.id for profile in profiles} != set(profile_ids):
        raise_error(404, ERR_PRINTER_PROFILE_NOT_FOUND)
    return profiles


async def _validate_catalog_printer_id(db: AsyncSession, printer_id: int | None) -> None:
    if printer_id is None:
        return
    exists = await db.scalar(
        select(Printer.id).where(Printer.id == printer_id, Printer.active.is_(True))
    )
    if exists is None:
        raise_error(404, ERR_PRINTER_NOT_FOUND)


async def _replace_profile_links(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    profile_ids: list[int],
) -> None:
    current_ids = set(
        (
            await db.execute(
                select(UserPrinterProfileLink.printer_profile_id).where(
                    UserPrinterProfileLink.physical_printer_id == physical_printer_id,
                    UserPrinterProfileLink.user_id == user_id,
                )
            )
        ).scalars()
    )
    requested_ids = set(profile_ids)
    await _validate_profile_ids(
        db,
        user_id,
        sorted(requested_ids - current_ids),
    )
    # A profile retired by a newer upstream bundle remains valid historical
    # context on a printer that already used it. It can be retained or removed,
    # but cannot be newly attached elsewhere.
    await _validate_profile_ids(
        db,
        user_id,
        sorted(requested_ids & current_ids),
        active_only=False,
    )
    await db.execute(
        delete(UserPrinterProfileLink).where(
            UserPrinterProfileLink.physical_printer_id == physical_printer_id,
            UserPrinterProfileLink.user_id == user_id,
        )
    )
    db.add_all(
        [
            UserPrinterProfileLink(
                user_id=user_id,
                physical_printer_id=physical_printer_id,
                printer_profile_id=profile_id,
            )
            for profile_id in profile_ids
        ]
    )


async def create_physical_printer(
    db: AsyncSession, user_id: int, payload: PhysicalPrinterCreate
) -> UserPrinterDevice:
    from app.services.orca_import_guard import hold_account_import_lock
    from app.services.printer_setup_service import (
        attach_setup_connection,
        find_setup_printer,
        setup_material_system,
    )

    await hold_account_import_lock(db, user_id)
    logical_id = (
        str(uuid5(NAMESPACE_URL, f"filamenthub:printer-create:{user_id}:{payload.request_id}"))
        if payload.request_id else None
    )
    if logical_id:
        replay_id = await db.scalar(select(UserPrinterDevice.id).where(
            UserPrinterDevice.user_id == user_id,
            UserPrinterDevice.logical_id == logical_id,
        ))
        if replay_id is not None:
            # A retry resumes the original creation. It never rewrites changes
            # made to that printer after the first response was lost.
            return await require_physical_printer(db, user_id, replay_id)
    await _validate_catalog_printer_id(db, payload.printer_id)
    await _validate_profile_ids(db, user_id, payload.printer_profile_ids)
    known_id = await find_setup_printer(db, user_id, payload.connection)
    if known_id is not None:
        printer = await require_physical_printer(db, user_id, known_id)
        existing_profiles = set((await db.execute(select(
            UserPrinterProfileLink.printer_profile_id,
        ).where(UserPrinterProfileLink.physical_printer_id == known_id))).scalars())
        db.add_all([
            UserPrinterProfileLink(
                user_id=user_id, physical_printer_id=known_id, printer_profile_id=profile_id,
            )
            for profile_id in payload.printer_profile_ids if profile_id not in existing_profiles
        ])
    else:
        printer = UserPrinterDevice(
            user_id=user_id,
            name=payload.name,
            printer_id=payload.printer_id,
            device_fingerprint=None,
            supports_hh=False,
            **({"logical_id": logical_id} if logical_id else {}),
        )
        db.add(printer)
        await db.flush()
        await _replace_profile_links(
            db,
            user_id=user_id,
            physical_printer_id=printer.id,
            profile_ids=payload.printer_profile_ids,
        )
    await attach_setup_connection(db, user_id, printer.id, payload.connection)
    await setup_material_system(db, user_id, printer.id, payload.material_system)
    await db.commit()
    return await require_physical_printer(db, user_id, printer.id)


async def update_physical_printer(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    payload: PhysicalPrinterUpdate,
) -> UserPrinterDevice:
    printer = await require_physical_printer(db, user_id, physical_printer_id)
    fields = payload.model_fields_set
    if "name" in fields and payload.name is not None:
        printer.name = payload.name
    if "printer_id" in fields:
        await _validate_catalog_printer_id(db, payload.printer_id)
        printer.printer_id = payload.printer_id
    await db.commit()
    return await require_physical_printer(db, user_id, physical_printer_id)


async def set_physical_printer_configurations(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    payload: PhysicalPrinterConfigurationsUpdate,
) -> UserPrinterDevice:
    await require_physical_printer(db, user_id, physical_printer_id)
    await _replace_profile_links(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        profile_ids=payload.printer_profile_ids,
    )
    await db.commit()
    return await require_physical_printer(db, user_id, physical_printer_id)


def _forget_reporting(printer: UserPrinterDevice) -> None:
    """Drop what the previous feed system said about this printer.

    Reporting is a fact about a feed system, while the flag lives on the printer
    that carries the key. Keeping it across systems would show a fresh system as
    already connected, with data from a system that is gone.
    """
    printer.reports_feed = False
    printer.last_seen_at = None


async def create_material_system(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    payload: MaterialSystemCreate,
    *,
    commit: bool = True,
) -> UserPrinterDevice:
    printer = await require_physical_printer(db, user_id, physical_printer_id)
    # A printer feeds from one place. Two systems on it would mean two sources
    # racing to say what sits in a slot, with no way to tell which is right.
    taken = await db.scalar(
        select(MaterialSystem.id).where(
            MaterialSystem.physical_printer_id == physical_printer_id,
            MaterialSystem.user_id == user_id,
        )
    )
    if taken is not None:
        raise_error(409, ERR_MATERIAL_SYSTEM_EXISTS)
    _forget_reporting(printer)
    system = MaterialSystem(
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        name=payload.name,
        kind=payload.kind,
        provider=payload.provider,
        capabilities=list(payload.capabilities),
        declared_slot_count=payload.slot_count,
    )
    slots = list(payload.slots)
    if not slots and payload.slot_count is not None:
        slots = [MaterialSlotCreate(provider_index=index) for index in range(payload.slot_count)]
    system.slots = [
        MaterialSlot(
            user_id=user_id,
            provider_index=slot.provider_index,
            label=slot.label,
            kind=slot.kind,
        )
        for slot in slots
    ]
    db.add(system)
    if commit:
        await db.commit()
    else:
        await db.flush()
    # The session keeps objects alive past commit, so the printer would answer
    # with the collection it loaded before this system existed.
    db.expire(printer)
    return await require_physical_printer(db, user_id, physical_printer_id)


async def _occupied_slot_indices(db: AsyncSession, slots: list[MaterialSlot]) -> set[int]:
    """Slot indices holding a spool or a preset, by either assignment path.

    Klipper systems keep the gate map and the slot assignment in step; systems of
    any other provider only ever get the assignment, so both have to be checked.
    """
    slot_ids = [slot.id for slot in slots]
    if not slot_ids:
        return set()
    index_by_slot = {slot.id: slot.provider_index for slot in slots}

    occupied: set[int] = set()
    gate_rows = await db.execute(
        select(PresetGateState.gate_index).where(
            PresetGateState.material_slot_id.in_(slot_ids),
            or_(
                PresetGateState.spool_id.is_not(None),
                PresetGateState.preset_id.is_not(None),
            ),
        )
    )
    occupied.update(gate_rows.scalars().all())

    assignment_rows = await db.execute(
        select(MaterialSlotAssignment.material_slot_id).where(
            MaterialSlotAssignment.material_slot_id.in_(slot_ids),
            or_(
                MaterialSlotAssignment.spool_id.is_not(None),
                MaterialSlotAssignment.preset_id.is_not(None),
            ),
        )
    )
    occupied.update(index_by_slot[slot_id] for slot_id in assignment_rows.scalars().all())

    return occupied


async def _first_occupied_slot_index(db: AsyncSession, slots: list[MaterialSlot]) -> int | None:
    occupied = await _occupied_slot_indices(db, slots)
    return min(occupied) if occupied else None


async def _lock_system_slots(db: AsyncSession, system_id: int) -> list[MaterialSlot]:
    # Slot writers must not wait for a parent while a topology writer holds that
    # parent and waits for the slot. Call before changing the system or printer.
    with db.no_autoflush:
        return list((await db.scalars(
            select(MaterialSlot).where(MaterialSlot.material_system_id == system_id)
            .order_by(MaterialSlot.id)
            .options(selectinload(MaterialSlot.assignment), selectinload(MaterialSlot.legacy_gate_state))
            .with_for_update().execution_options(populate_existing=True)
        )).all())


def _route_meaning(kind: str, system_kind: str, single_route: bool) -> str:
    if kind in {"slot", "gate"}:
        # Older manual single-spool cards used the generic name "slot".
        return "external" if single_route and system_kind == "direct_feed" else "gate"
    return kind


async def _guard_route_reinterpretation(
    db: AsyncSession, system: MaterialSystem, slots: list[MaterialSlot],
    routes: list[MaterialSlotCreate], next_kind: str,
    *, retain_missing: bool = False,
) -> None:
    by_index = {item.provider_index: item.kind for item in slots} if retain_missing else {}
    by_index.update({item.provider_index: item.kind for item in routes})
    changed = [slot for slot in slots if slot.provider_index in by_index
               if _route_meaning(slot.kind, system.kind, len(slots) == 1)
               != _route_meaning(by_index[slot.provider_index], next_kind, len(by_index) == 1)]
    busy = await _first_occupied_slot_index(db, changed)
    if busy is not None:
        raise_error(409, ERR_MATERIAL_SLOT_IN_USE, params={"index": busy + 1})


async def update_material_system(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
    payload: MaterialSystemUpdate,
    *,
    commit: bool = True,
) -> UserPrinterDevice:
    """Edit declared topology without losing occupied routes or their identity."""
    from app.services.orca_import_guard import hold_account_import_lock

    await hold_account_import_lock(db, user_id)
    system = await _require_material_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    if payload.slot_count is not None or payload.slots is not None:
        slots = await _lock_system_slots(db, system.id)
        if payload.name is not None:
            system.name = payload.name
        by_index = {slot.provider_index: slot for slot in slots}
        if payload.slots is not None:
            unchanged = (
                payload.kind in {None, system.kind} and payload.provider in {None, system.provider}
                and {(item.provider_index, item.kind, item.label) for item in payload.slots}
                == {(slot.provider_index, slot.kind, slot.label) for slot in slots if slot.active}
            )
            # A lost response may replay an already applied explicit map. It
            # cannot change any assignment, and must not force a fresh card.
            if unchanged:
                if commit:
                    await db.commit()
                else:
                    await db.flush()
                return await require_physical_printer(db, user_id, physical_printer_id)
            expected = {item.material_slot_id: item for item in payload.expected_slots or []}
            if len(expected) != len(payload.expected_slots or []) or set(expected) != {slot.id for slot in slots}:
                raise_error(409, ERR_MATERIAL_ASSIGNMENT_CONFLICT)
            for slot in slots:
                assignment = slot.assignment or slot.legacy_gate_state
                if (slot.assignment_revision != expected[slot.id].expected_revision
                    or (assignment.spool_id if assignment else None) != expected[slot.id].expected_spool_id):
                    raise_error(409, ERR_MATERIAL_ASSIGNMENT_CONFLICT)
            requested = payload.slots
        else:
            # Count describes ordinary routes only. External holders and bypass
            # are not the tail of a contiguous array of gates.
            assert payload.slot_count is not None
            requested = [MaterialSlotCreate(provider_index=index,
                         kind=by_index[index].kind if index in by_index else "slot",
                         label=by_index[index].label if index in by_index else None)
                         for index in range(payload.slot_count)]
            requested += [MaterialSlotCreate(provider_index=slot.provider_index, kind=slot.kind, label=slot.label)
                          for slot in slots if slot.kind not in {"slot", "gate"}]
            if len({item.provider_index for item in requested}) != len(requested):
                raise_error(409, ERR_MATERIAL_ASSIGNMENT_CONFLICT)
        requested_indices = {item.provider_index for item in requested}
        doomed = [slot for slot in slots if slot.provider_index not in requested_indices]
        await _guard_route_reinterpretation(db, system, slots, requested, payload.kind or system.kind)
        busy = await _first_occupied_slot_index(db, doomed)
        if busy is not None:
            raise_error(409, ERR_MATERIAL_SLOT_IN_USE, params={"index": busy + 1})
        if payload.provider is not None and payload.provider != system.provider:
            connected = await db.scalar(select(PhysicalPrinterConnector.id).where(
                PhysicalPrinterConnector.material_system_id == system.id,
                PhysicalPrinterConnector.active.is_(True),
            ).limit(1))
            if system.provider != "manual" or connected is not None:
                raise_error(409, ERR_MATERIAL_SYSTEM_EXISTS)
            system.provider = payload.provider
        for item in requested:
            slot = by_index.get(item.provider_index)
            if slot is None:
                db.add(MaterialSlot(user_id=user_id, material_system_id=system.id,
                                    provider_index=item.provider_index, kind=item.kind, label=item.label))
            else:
                if (slot.kind != item.kind or slot.label != item.label or not slot.active
                    or payload.kind is not None and payload.kind != system.kind):
                    slot.assignment_revision += 1
                slot.kind, slot.label, slot.active = item.kind, item.label, True
        if doomed:
            await db.execute(
                delete(MaterialSlot).where(MaterialSlot.id.in_([slot.id for slot in doomed]))
            )
        ordinary = {item.provider_index for item in requested if item.kind in {"slot", "gate"}}
        declared_count = len(ordinary) if ordinary and ordinary == set(range(len(ordinary))) else None
        system.declared_slot_count = declared_count
        if payload.kind is not None:
            system.kind = payload.kind
        if system.provider in KLIPPER_PROVIDERS:
            # The legacy gate map still gates manual assignment, so it has to
            # follow the declared size or the new slots refuse every spool.
            printer = await require_physical_printer(db, user_id, physical_printer_id)
            printer.gate_count = declared_count

    if payload.name is not None:
        system.name = payload.name
    if commit:
        await db.commit()
    else:
        await db.flush()
    return await require_physical_printer(db, user_id, physical_printer_id)


async def _require_material_system(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> MaterialSystem:
    result = await db.execute(
        select(MaterialSystem).where(
            MaterialSystem.id == material_system_id,
            MaterialSystem.user_id == user_id,
            MaterialSystem.physical_printer_id == physical_printer_id,
        )
    )
    system = result.scalar_one_or_none()
    if system is None:
        raise_error(404, ERR_MATERIAL_SYSTEM_NOT_FOUND)
    return system


async def upsert_physical_printer_connector(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    payload: PhysicalPrinterConnectorCreate,
) -> UserPrinterDevice:
    await require_physical_printer(db, user_id, physical_printer_id)
    if payload.material_system_id is not None:
        await _require_material_system(
            db,
            user_id=user_id,
            physical_printer_id=physical_printer_id,
            material_system_id=payload.material_system_id,
        )
    result = await db.execute(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.user_id == user_id,
            PhysicalPrinterConnector.physical_printer_id == physical_printer_id,
            PhysicalPrinterConnector.provider == payload.provider,
            PhysicalPrinterConnector.transport == payload.transport,
        )
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        connector = PhysicalPrinterConnector(
            user_id=user_id,
            physical_printer_id=physical_printer_id,
            provider=payload.provider,
            transport=payload.transport,
        )
        db.add(connector)
    connector.material_system_id = payload.material_system_id
    connector.capabilities = list(payload.capabilities)
    connector.active = True
    await db.commit()
    return await require_physical_printer(db, user_id, physical_printer_id)


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _newer_observation(candidate: datetime, existing: datetime | None) -> bool:
    return existing is None or _utc_datetime(candidate) >= _utc_datetime(existing)


def _snapshot_is_current(
    connector: PhysicalPrinterConnector,
    payload: PrinterBridgeSnapshotRequest,
    observed_at: datetime,
) -> bool:
    if payload.sequence is None:
        return _newer_observation(observed_at, connector.last_observation_at)
    if connector.last_snapshot_source_instance_id != payload.source_instance_id:
        return True
    return (
        connector.last_snapshot_sequence is None
        or payload.sequence > connector.last_snapshot_sequence
    )


def _printer_bridge_observation_source(provider: str, transport: str) -> str:
    if provider == "bambu" and transport == "orca_plugin_lan":
        return "bambu_lan_mqtt"
    return f"{provider}_{'edge' if transport == 'edge_agent' else 'moonraker'}"[:50]


async def build_printer_bridge_desired_snapshot(
    db: AsyncSession,
    connector: PhysicalPrinterConnector,
) -> PrinterBridgeDesiredSnapshotResponse:
    """Build the provider-neutral desired spool and preset state for one connector."""
    if connector.material_system_id is None:
        raise_error(404, ERR_MATERIAL_SYSTEM_NOT_FOUND)
    system = await db.scalar(
        select(MaterialSystem)
        .where(
            MaterialSystem.id == connector.material_system_id,
            MaterialSystem.user_id == connector.user_id,
            MaterialSystem.physical_printer_id == connector.physical_printer_id,
        )
        .options(
            selectinload(MaterialSystem.slots)
            .selectinload(MaterialSlot.assignment)
            .selectinload(MaterialSlotAssignment.spool)
            .selectinload(UserSpool.filament)
            .selectinload(Filament.brand),
            selectinload(MaterialSystem.slots)
            .selectinload(MaterialSlot.assignment)
            .selectinload(MaterialSlotAssignment.preset),
        )
        .execution_options(populate_existing=True)
    )
    if system is None:
        raise_error(404, ERR_MATERIAL_SYSTEM_NOT_FOUND)

    slots: list[PrinterBridgeDesiredSlotSnapshot] = []
    for slot in sorted(system.slots, key=lambda item: (item.provider_index, item.id)):
        assignment = slot.assignment
        spool_snapshot = None
        preset_snapshot = None
        if assignment is not None and assignment.spool is not None:
            spool = assignment.spool
            filament = spool.filament
            spool_snapshot = PrinterBridgeDesiredSpoolSnapshot(
                id=spool.id,
                filament_id=spool.filament_id,
                name=filament.name if filament is not None else f"Spool #{spool.id}",
                brand=(
                    filament.brand.name
                    if filament is not None and filament.brand is not None
                    else None
                ),
                material_type=filament.material_type if filament is not None else None,
                color_hex=filament.color_hex if filament is not None else None,
                remaining_weight_g=spool.remaining_weight_g,
                initial_weight_g=spool.initial_weight_g,
                density_g_cm3=(
                    filament.density
                    if filament is not None and filament.density and filament.density > 0
                    else DEFAULT_DENSITY_G_CM3
                ),
                diameter_mm=(
                    filament.diameter
                    if filament is not None and filament.diameter and filament.diameter > 0
                    else DEFAULT_DIAMETER_MM
                ),
            )
        if assignment is not None and assignment.preset is not None:
            preset_snapshot = PrinterBridgeDesiredPresetSnapshot(
                id=assignment.preset.id,
                name=assignment.preset.name,
            )
        slots.append(
            PrinterBridgeDesiredSlotSnapshot(
                material_slot_id=slot.id,
                index=slot.provider_index,
                label=slot.label,
                kind=slot.kind,
                assignment_revision=slot.assignment_revision,
                spool=spool_snapshot,
                preset=preset_snapshot,
            )
        )

    revision_payload = {
        "physical_printer_id": connector.physical_printer_id,
        "material_system_id": system.id,
        "system_name": system.name,
        "system_kind": system.kind,
        "slots": [slot.model_dump(mode="json") for slot in slots],
    }
    revision = hashlib.sha256(
        json.dumps(
            revision_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return PrinterBridgeDesiredSnapshotResponse(revision=revision, **revision_payload)


async def ingest_printer_bridge_snapshot(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    payload: PrinterBridgeSnapshotRequest,
    *,
    commit: bool = True,
) -> PrinterBridgeSnapshotResponse:
    """Persist only normalized facts from a locally authenticated connector.

    LAN address, printer serial and credentials never enter this contract. The
    source timestamp is capped at receipt time so a fast client clock cannot
    make every later observation look stale forever.
    """
    from app.core.errors import ERR_PRINTER_IDENTITY_CONFLICT
    from app.services.orca_import_guard import hold_account_import_lock
    from app.services.printer_identity_service import remember_identity

    await hold_account_import_lock(db, user_id)
    printer = await require_physical_printer(db, user_id, physical_printer_id)
    system = await _require_material_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=payload.material_system_id,
    )
    if system.provider not in {"manual", payload.provider}:
        raise_error(409, ERR_MATERIAL_SYSTEM_EXISTS)
    existing_slots = await _lock_system_slots(db, system.id)

    received_at = datetime.now(timezone.utc)
    observed_at = min(_utc_datetime(payload.observed_at), received_at)
    observation_source = _printer_bridge_observation_source(
        payload.provider,
        payload.transport,
    )

    connector = await db.scalar(
        select(PhysicalPrinterConnector)
        .where(
            PhysicalPrinterConnector.user_id == user_id,
            PhysicalPrinterConnector.physical_printer_id == physical_printer_id,
            PhysicalPrinterConnector.provider == payload.provider,
            PhysicalPrinterConnector.transport == payload.transport,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if connector is None:
        connector = PhysicalPrinterConnector(
            user_id=user_id,
            physical_printer_id=physical_printer_id,
            provider=payload.provider,
            transport=payload.transport,
        )
        db.add(connector)
        await db.flush()
    elif connector.source_instance_id != payload.source_instance_id:
        raise_error(401, ERR_PRINTER_BRIDGE_UNAUTHORIZED)

    connector.last_seen_at = received_at
    connector.active = True
    if payload.capabilities is not None:
        connector.capabilities = list(payload.capabilities)
    printer.last_seen_at = received_at
    printer.reports_feed = True

    snapshot_is_current = _snapshot_is_current(connector, payload, observed_at)
    if not snapshot_is_current:
        if commit:
            await db.commit()
        return PrinterBridgeSnapshotResponse(
            accepted=False,
            stale=True,
            connector_id=connector.id,
            material_system_id=system.id,
            slots_seen=len(payload.slots),
        )

    if payload.device_identity and not await remember_identity(
        db, user_id, physical_printer_id, payload.device_identity,
    ):
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)

    connector.material_system_id = system.id
    connector.source_instance_id = payload.source_instance_id
    if _newer_observation(observed_at, connector.last_observation_at):
        connector.last_observation_at = observed_at
    if payload.sequence is not None:
        connector.last_snapshot_sequence = payload.sequence
        connector.last_snapshot_source_instance_id = payload.source_instance_id
    newer_source = await db.scalar(
        select(PhysicalPrinterConnector.id).where(
            PhysicalPrinterConnector.material_system_id == system.id,
            PhysicalPrinterConnector.id != connector.id,
            PhysicalPrinterConnector.active.is_(True),
            PhysicalPrinterConnector.last_seen_at > received_at,
        ).limit(1)
    )
    topology_is_current = newer_source is None
    next_kind = "mmu" if payload.provider == "happy_hare" and payload.slots else system.kind
    if topology_is_current:
        await _guard_route_reinterpretation(db, system, existing_slots, [
            MaterialSlotCreate(provider_index=item.provider_index, kind=item.kind, label=item.label)
            for item in payload.slots
        ], next_kind, retain_missing=True)
        if system.kind != next_kind:
            for slot in existing_slots:
                slot.assignment_revision += 1
        system.kind = next_kind
    system.provider = payload.provider
    system.capabilities = sorted(set(system.capabilities) | set(connector.capabilities))
    system.active = True

    accepted = True

    inventory_matches = bool(
        printer.api_key
        and payload.inventory_key_digest
        and hmac.compare_digest(
            device_inventory_digest(printer.api_key) or "", payload.inventory_key_digest
        )
    )
    reported_spool_ids = {item.spool_id for item in payload.slots if item.spool_id is not None}
    owned_spool_ids = (
        set(
            (
                await db.scalars(
                    select(UserSpool.id).where(
                        UserSpool.user_id == user_id, UserSpool.id.in_(reported_spool_ids)
                    )
                )
            ).all()
        )
        if inventory_matches and reported_spool_ids
        else set()
    )
    reported_tag_uids = {item.tag_uid for item in payload.slots if item.tag_uid is not None}
    tag_bindings = (
        {
            tag.uid: tag
            for tag in (
                await db.scalars(
                    select(SpoolTag).where(
                        SpoolTag.user_id == user_id,
                        SpoolTag.uid.in_(reported_tag_uids),
                    )
                )
            ).all()
        }
        if reported_tag_uids
        else {}
    )

    status_observation = await db.scalar(
        select(PhysicalPrinterStatusObservation).where(
            PhysicalPrinterStatusObservation.connector_id == connector.id
        )
    )
    if payload.printer is not None:
        if status_observation is None:
            status_observation = PhysicalPrinterStatusObservation(
                user_id=user_id,
                connector_id=connector.id,
                source=observation_source,
                observed_at=observed_at,
                state=payload.printer.state,
            )
            db.add(status_observation)
        for field_name, value in payload.printer.model_dump().items():
            setattr(status_observation, field_name, value)
        status_observation.source = observation_source
        status_observation.observed_at = observed_at
        status_observation.received_at = received_at
        accepted = True

    slots_by_index = {slot.provider_index: slot for slot in existing_slots}
    if payload.slot_topology_complete and topology_is_current:
        reported_indices = {item.provider_index for item in payload.slots}
        # A slot the printer stopped reporting is hidden, but not when a person
        # put something in it: hiding it would strand the spool in a slot nobody
        # can see, still counted as loaded. Resizing by hand refuses the same
        # case with ERR_MATERIAL_SLOT_IN_USE, and a provider report carries less
        # authority than a person's own assignment, not more.
        occupied_indices = await _occupied_slot_indices(db, existing_slots)
        for slot in existing_slots:
            if (
                slot.provider_index not in reported_indices
                and slot.provider_index not in occupied_indices
            ):
                if slot.active:
                    slot.assignment_revision += 1
                slot.active = False
    for item in payload.slots:
        slot = slots_by_index.get(item.provider_index)
        if not topology_is_current and (slot is None or not slot.active):
            continue
        if slot is None:
            slot = MaterialSlot(
                user_id=user_id,
                material_system_id=system.id,
                provider_index=item.provider_index,
                label=item.label,
                kind=item.kind,
            )
            db.add(slot)
            await db.flush()
            slots_by_index[item.provider_index] = slot
        elif topology_is_current:
            if slot.kind != item.kind or not slot.active:
                slot.assignment_revision += 1
            if item.label:
                slot.label = item.label
            slot.kind = item.kind
            slot.active = True

        observation = await db.scalar(
            select(MaterialSlotObservation).where(
                MaterialSlotObservation.connector_id == connector.id,
                MaterialSlotObservation.material_slot_id == slot.id,
            )
        )
        if observation is None:
            observation = MaterialSlotObservation(
                user_id=user_id,
                connector_id=connector.id,
                material_slot_id=slot.id,
                source=observation_source,
                observed_at=observed_at,
            )
            db.add(observation)
        values = item.model_dump(exclude={"provider_index", "label", "kind"})
        provider_identity_known = (
            inventory_matches
            and item.spool_identity_known
            and (item.spool_id is None or item.spool_id in owned_spool_ids)
        )
        provider_spool_id = item.spool_id if provider_identity_known else None
        tag_binding = tag_bindings.get(item.tag_uid) if item.tag_uid is not None else None
        values["tag_match_status"] = None
        if item.tag_uid is None:
            values["spool_identity_known"] = provider_identity_known
            values["spool_id"] = provider_spool_id
        elif tag_binding is None:
            values["tag_match_status"] = "unlinked"
            values["spool_identity_known"] = provider_identity_known
            values["spool_id"] = provider_spool_id
        elif provider_spool_id is not None and provider_spool_id != tag_binding.spool_id:
            values["tag_match_status"] = "conflict"
            values["spool_identity_known"] = False
            values["spool_id"] = None
        else:
            values["tag_match_status"] = "matched"
            values["spool_identity_known"] = True
            values["spool_id"] = tag_binding.spool_id
        values["color_hex"] = values["color_hex"].upper() if values["color_hex"] else None
        for field_name, value in values.items():
            setattr(observation, field_name, value)
        observation.source = observation_source
        observation.observed_at = observed_at
        observation.received_at = received_at
        accepted = True

    if payload.provider == "happy_hare" and payload.slot_topology_complete and topology_is_current:
        gates = {item.provider_index for item in payload.slots if item.kind != "bypass"}
        if gates and gates == set(range(len(gates))):
            printer.supports_hh = True
            printer.gate_count = len(gates)
            system.kind = "mmu"
            await ensure_material_topology(
                db,
                printer,
                exact_gate_count=len(gates),
                reported_routes=[
                    MaterialSlotCreate(
                        provider_index=item.provider_index,
                        label=item.label,
                        kind=item.kind,
                    )
                    for item in payload.slots
                    if item.kind == "bypass"
                ],
                preserve_existing_assignments=True,
            )

    if commit:
        await db.commit()
    return PrinterBridgeSnapshotResponse(
        accepted=accepted,
        stale=not accepted,
        connector_id=connector.id,
        material_system_id=system.id,
        slots_seen=len(payload.slots),
    )


async def ensure_material_topology(
    db: AsyncSession,
    device: UserPrinterDevice,
    *,
    provider: str | None = None,
    gate_indices: set[int] | None = None,
    exact_gate_count: int | None = None,
    reported_routes: list[MaterialSlotCreate] | None = None,
    sync_legacy_assignments: bool = True,
    preserve_existing_assignments: bool = False,
) -> None:
    """Write what a provider reports about a printer's feed into the contract.

    Every provider owns its own system on the printer; a new one plugs in by
    passing its name instead of inheriting the Klipper pair.
    """
    provider = provider or ("happy_hare" if device.supports_hh else "legacy")
    if device.id is None:
        await db.flush()
    siblings = list(KLIPPER_PROVIDERS) if provider in KLIPPER_PROVIDERS else [provider]
    indices = set(gate_indices or ())
    if exact_gate_count is not None:
        indices.update(range(exact_gate_count))
    if device.gate_count is not None:
        indices.update(range(device.gate_count))
    if not device.supports_hh and not indices:
        return
    if indices:
        # A reported gate proves every lower gate exists, so the panel shows a
        # contiguous system instead of a hole where no spool has been seen yet.
        indices = set(range(min(max(indices), MAX_GATE_INDEX) + 1))
    routes_by_index = {route.provider_index: route for route in (reported_routes or [])}
    indices.update(routes_by_index)

    system = await db.scalar(
        select(MaterialSystem)
        .where(
            MaterialSystem.physical_printer_id == device.id,
            MaterialSystem.user_id == device.user_id,
            MaterialSystem.provider.in_(siblings),
        )
        .order_by(MaterialSystem.id)
        .execution_options(autoflush=False)
    )
    if system is None:
        # A printer normally feeds from one place. If the person already
        # described it by hand, the arriving data belongs to that system rather
        # than to a second one appearing beside it.
        lonely = list(
            (
                await db.execute(
                    select(MaterialSystem)
                    .where(
                        MaterialSystem.physical_printer_id == device.id,
                        MaterialSystem.user_id == device.user_id,
                    )
                    .order_by(MaterialSystem.id)
                    .execution_options(autoflush=False)
                )
            )
            .scalars()
            .all()
        )
        if len(lonely) == 1:
            system = lonely[0]
    if system is None:
        system = MaterialSystem(
            user_id=device.user_id,
            physical_printer_id=device.id,
            name="Happy Hare" if device.supports_hh else "Material system",
            kind="mmu",
            provider="happy_hare" if device.supports_hh else "legacy",
            capabilities=HAPPY_HARE_CAPABILITIES if device.supports_hh else [],
        )
        if device.gate_count is not None:
            system.declared_slot_count = device.gate_count
        db.add(system)
        await db.flush()
    elif system.provider not in {*siblings, "manual"}:
        # This feed already names its own way of reporting, so nothing here is
        # about it: neither its name, nor its slots, nor how many it declares.
        return
    existing_slots_result = await db.execute(
        select(MaterialSlot).where(MaterialSlot.material_system_id == system.id)
        .execution_options(autoflush=False)
    )
    slots_by_index = {slot.provider_index: slot for slot in existing_slots_result.scalars().all()}
    next_kind = "mmu" if device.supports_hh else system.kind
    requested = [routes_by_index.get(index) or MaterialSlotCreate(
        provider_index=index, kind="slot",
    ) for index in sorted(indices)]
    # Ordinary assignment mirroring does not change topology and may already
    # hold its target slot. Only topology-changing calls acquire the whole map.
    topology_changes = (system.kind != next_kind or exact_gate_count is not None
                        or any(index not in slots_by_index for index in indices)
                        or any(index in slots_by_index and (
                            slots_by_index[index].kind != route.kind or not slots_by_index[index].active
                        ) for index, route in routes_by_index.items()))
    if topology_changes:
        locked = await _lock_system_slots(db, system.id)
        slots_by_index = {slot.provider_index: slot for slot in locked}
        await _guard_route_reinterpretation(db, system, locked, requested, next_kind, retain_missing=True)
    prior = {slot.id: (slot.kind, slot.active) for slot in slots_by_index.values()}
    kind_changed = system.kind != next_kind
    if device.supports_hh:
        system.kind = next_kind
        system.provider = "happy_hare"
        system.capabilities = list(HAPPY_HARE_CAPABILITIES)
        system.active = True
    elif system.provider == "manual":
        system.provider = provider
    for provider_index in sorted(indices):
        route = routes_by_index.get(provider_index)
        if provider_index not in slots_by_index:
            slot = MaterialSlot(
                user_id=device.user_id,
                material_system_id=system.id,
                provider_index=provider_index,
                label=route.label if route is not None else None,
                kind=route.kind if route is not None else "slot",
            )
            db.add(slot)
            await db.flush()
            slots_by_index[provider_index] = slot
        elif route is not None:
            slot = slots_by_index[provider_index]
            slot.kind = route.kind
            if route.label is not None:
                slot.label = route.label
            slot.active = True

    if exact_gate_count is not None:
        # A complete provider snapshot is stronger evidence than the highest
        # occupied gate. Keep rows outside a shrunken topology recoverable, but
        # do not present them as current hardware slots.
        system.declared_slot_count = exact_gate_count
        occupied_route_indices = await _occupied_slot_indices(db, list(slots_by_index.values()))
        for provider_index, slot in slots_by_index.items():
            if slot.kind in {"slot", "gate"}:
                slot.active = (
                    provider_index < exact_gate_count or provider_index in occupied_route_indices
                )
            elif reported_routes is not None:
                # A complete route report can retire a removed bypass, but an
                # assigned spool must stay visible until the person moves it.
                slot.active = (
                    provider_index in routes_by_index or provider_index in occupied_route_indices
                )

    if (
        exact_gate_count is None
        and system.declared_slot_count is not None
        and indices
        and max(indices) + 1 > system.declared_slot_count
    ):
        # The machine reported more slots than the person declared; their answer
        # is stale, so ask again instead of hiding the extra slots.
        system.declared_slot_count = None

    for slot in slots_by_index.values():
        if slot.id in prior and (kind_changed or prior[slot.id] != (slot.kind, slot.active)):
            slot.assignment_revision += 1

    if slots_by_index:
        states_result = await db.execute(
            select(PresetGateState).where(
                PresetGateState.device_id == device.id,
                PresetGateState.gate_index.in_(slots_by_index),
            )
        )
        for state in states_result.scalars().all():
            state.material_slot_id = slots_by_index[state.gate_index].id
            if sync_legacy_assignments:
                await sync_legacy_material_assignment(
                    db, state, preserve_existing=preserve_existing_assignments,
                )

    connector = await db.scalar(
        select(PhysicalPrinterConnector)
        .where(
            PhysicalPrinterConnector.physical_printer_id == device.id,
            PhysicalPrinterConnector.user_id == device.user_id,
            PhysicalPrinterConnector.transport.in_(["spoolman_compat", "legacy_adapter"]),
            or_(
                PhysicalPrinterConnector.material_system_id == system.id,
                PhysicalPrinterConnector.provider.in_(siblings),
            ),
        )
        .order_by(PhysicalPrinterConnector.id)
    )
    if connector is None:
        connector = PhysicalPrinterConnector(
            user_id=device.user_id,
            physical_printer_id=device.id,
            provider=system.provider,
            transport="spoolman_compat" if device.api_key else "legacy_adapter",
        )
        db.add(connector)
    connector.material_system_id = system.id
    connector.capabilities = list(HAPPY_HARE_CAPABILITIES) if device.supports_hh else []
    connector.last_seen_at = device.last_seen_at
    connector.active = True


async def _shelve_spools(db: AsyncSession, user_id: int, spool_ids: set[int]) -> None:
    from app.models.user_spool import UserSpool
    from app.services.spool_service import (
        clear_spool_gate_assignments,
        shelf_spool_if_unassigned,
    )

    for spool_id in spool_ids:
        spool = await db.get(UserSpool, spool_id)
        if spool is None or spool.user_id != user_id:
            continue
        await clear_spool_gate_assignments(db, spool)
        await shelf_spool_if_unassigned(db, spool)


async def _loaded_spool_ids_for_device(db: AsyncSession, device_id: int) -> set[int]:
    """Spools sitting in this printer, whichever assignment path put them there."""
    gate_rows = await db.execute(
        select(PresetGateState.spool_id).where(
            PresetGateState.device_id == device_id,
            PresetGateState.spool_id.is_not(None),
        )
    )
    assignment_rows = await db.execute(
        select(MaterialSlotAssignment.spool_id)
        .join(MaterialSlot, MaterialSlot.id == MaterialSlotAssignment.material_slot_id)
        .join(MaterialSystem, MaterialSystem.id == MaterialSlot.material_system_id)
        .where(
            MaterialSystem.physical_printer_id == device_id,
            MaterialSlotAssignment.spool_id.is_not(None),
        )
    )
    return set(gate_rows.scalars().all()) | set(assignment_rows.scalars().all())


async def _shelve_loaded_spools(db: AsyncSession, user_id: int, device_id: int) -> None:
    await _shelve_spools(db, user_id, await _loaded_spool_ids_for_device(db, device_id))


async def delete_material_system(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> UserPrinterDevice:
    """Remove one material system, returning its spools to the shelf.

    The physical printer and its Orca configurations stay, but the material
    system's reporting credential must not outlive the integration it grants.
    A replacement system receives a fresh one-time key during its own setup.
    """
    system = await _require_material_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )

    slots = list(
        (await db.execute(select(MaterialSlot).where(MaterialSlot.material_system_id == system.id)))
        .scalars()
        .all()
    )
    slot_ids = [slot.id for slot in slots]

    spool_ids: set[int] = set()
    if slot_ids:
        gate_rows = await db.execute(
            select(PresetGateState.spool_id).where(
                PresetGateState.material_slot_id.in_(slot_ids),
                PresetGateState.spool_id.is_not(None),
            )
        )
        assignment_rows = await db.execute(
            select(MaterialSlotAssignment.spool_id).where(
                MaterialSlotAssignment.material_slot_id.in_(slot_ids),
                MaterialSlotAssignment.spool_id.is_not(None),
            )
        )
        spool_ids = set(gate_rows.scalars().all()) | set(assignment_rows.scalars().all())

    if slot_ids:
        # The bindings go first: a spool only counts as free once nothing points
        # at it, and both tables are consulted for that.
        await db.execute(
            delete(MaterialSlotAssignment).where(
                MaterialSlotAssignment.material_slot_id.in_(slot_ids)
            )
        )
        await db.execute(
            delete(PresetGateState).where(PresetGateState.material_slot_id.in_(slot_ids))
        )
        await db.execute(delete(MaterialSlot).where(MaterialSlot.id.in_(slot_ids)))

    await _shelve_spools(db, user_id, spool_ids)

    provider = system.provider
    await db.execute(
        delete(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.material_system_id == system.id
        )
    )
    await db.execute(delete(MaterialSystem).where(MaterialSystem.id == system.id))
    db.expunge(system)

    printer = await require_physical_printer(db, user_id, physical_printer_id)
    _forget_reporting(printer)
    printer.api_key = None
    if provider in KLIPPER_PROVIDERS:
        # The legacy gate map describes exactly this system, so it goes with it;
        # otherwise the next system would inherit a phantom slot count.
        printer.gate_count = None
    await db.commit()
    # The session keeps objects alive past commit, so the printer would answer
    # with the collection it loaded before the system was removed.
    db.expire_all()
    return await require_physical_printer(db, user_id, physical_printer_id)


async def delete_physical_printer(db: AsyncSession, user_id: int, physical_printer_id: int) -> None:
    """Delete a physical printer, shelving the spools loaded in it first.

    A spool in a gate is real material the person keeps after selling or
    retiring the machine, so it is released and returned to the shelf before the
    gates disappear with the printer. Everything that only describes this
    machine — material systems, gate states, configuration links, connection
    bindings — is removed by the cascades; usage history keeps its rows.
    """
    printer = await require_physical_printer(db, user_id, physical_printer_id)
    spool_ids = await _loaded_spool_ids_for_device(db, printer.id)
    system_ids = [system.id for system in printer.material_systems]
    if system_ids:
        slot_ids = list(
            (
                await db.execute(
                    select(MaterialSlot.id).where(MaterialSlot.material_system_id.in_(system_ids))
                )
            )
            .scalars()
            .all()
        )
        if slot_ids:
            await db.execute(
                delete(MaterialSlotAssignment).where(
                    MaterialSlotAssignment.material_slot_id.in_(slot_ids)
                )
            )
    await db.execute(delete(PresetGateState).where(PresetGateState.device_id == printer.id))
    # Keep production history even in test/dev databases that do not enforce
    # ON DELETE SET NULL themselves. The printer name snapshot remains visible.
    await db.execute(
        update(PrintJob)
        .where(PrintJob.physical_printer_id == printer.id)
        .values(physical_printer_id=None)
    )
    await _shelve_spools(db, user_id, spool_ids)
    await db.delete(printer)
    await db.commit()
