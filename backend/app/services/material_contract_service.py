"""Physical-printer and provider-neutral material contract services."""

from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_DEVICE_NOT_FOUND,
    ERR_MATERIAL_SLOT_IN_USE,
    ERR_MATERIAL_SYSTEM_EXISTS,
    ERR_MATERIAL_SYSTEM_NOT_FOUND,
    ERR_PRINTER_NOT_FOUND,
    ERR_PRINTER_PROFILE_NOT_FOUND,
    raise_error,
)
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import (
    MaterialSlot,
    MaterialSystem,
    PhysicalPrinterConnector,
)
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.preset_gate_state import PresetGateState
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.material_contract import (
    MaterialSlotCreate,
    MaterialSystemCreate,
    MaterialSystemUpdate,
    PhysicalPrinterConfigurationsUpdate,
    PhysicalPrinterConnectorCreate,
    PhysicalPrinterCreate,
    PhysicalPrinterUpdate,
)
from app.services.material_assignment_service import sync_legacy_material_assignment

# Happy Hare and the plain Klipper adapter describe the same feed, so they share
# one system on the printer instead of each creating its own.
KLIPPER_PROVIDERS = ("happy_hare", "legacy")

HAPPY_HARE_CAPABILITIES = [
    "read",
    "write",
    "presence",
    "spool_identity",
    "consumption",
]


def _printer_load_options():
    return (
        selectinload(UserPrinterDevice.profile_links),
        selectinload(UserPrinterDevice.material_systems)
        .selectinload(MaterialSystem.slots)
        .selectinload(MaterialSlot.legacy_gate_state),
        selectinload(UserPrinterDevice.material_systems)
        .selectinload(MaterialSystem.slots)
        .selectinload(MaterialSlot.assignment),
        selectinload(UserPrinterDevice.connectors),
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
    )
    printer = result.scalar_one_or_none()
    if printer is None:
        raise_error(404, ERR_DEVICE_NOT_FOUND)
    return printer


async def list_physical_printers(
    db: AsyncSession, user_id: int
) -> list[UserPrinterDevice]:
    result = await db.execute(
        select(UserPrinterDevice)
        .where(UserPrinterDevice.user_id == user_id)
        .options(*_printer_load_options())
        .order_by(UserPrinterDevice.created_at, UserPrinterDevice.id)
    )
    return list(result.scalars().unique().all())


async def _validate_profile_ids(
    db: AsyncSession, user_id: int, profile_ids: list[int]
) -> list[PrinterProfile]:
    if not profile_ids:
        return []
    result = await db.execute(
        select(PrinterProfile).where(
            PrinterProfile.id.in_(profile_ids),
            PrinterProfile.active.is_(True),
            or_(
                PrinterProfile.owner_user_id == user_id,
                (PrinterProfile.owner_user_id.is_(None) & PrinterProfile.is_official.is_(True)),
            ),
        )
    )
    profiles = list(result.scalars().all())
    if {profile.id for profile in profiles} != set(profile_ids):
        raise_error(404, ERR_PRINTER_PROFILE_NOT_FOUND)
    return profiles


async def _validate_catalog_printer_id(
    db: AsyncSession, printer_id: int | None
) -> None:
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
    await _validate_profile_ids(db, user_id, profile_ids)
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
    await _validate_catalog_printer_id(db, payload.printer_id)
    await _validate_profile_ids(db, user_id, payload.printer_profile_ids)
    printer = UserPrinterDevice(
        user_id=user_id,
        name=payload.name,
        printer_id=payload.printer_id,
        device_fingerprint=None,
        supports_hh=False,
    )
    db.add(printer)
    await db.flush()
    await _replace_profile_links(
        db,
        user_id=user_id,
        physical_printer_id=printer.id,
        profile_ids=payload.printer_profile_ids,
    )
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


async def create_material_system(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    payload: MaterialSystemCreate,
) -> UserPrinterDevice:
    await require_physical_printer(db, user_id, physical_printer_id)
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
        slots = [
            MaterialSlotCreate(provider_index=index)
            for index in range(payload.slot_count)
        ]
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
    await db.commit()
    return await require_physical_printer(db, user_id, physical_printer_id)


async def _first_occupied_slot_index(
    db: AsyncSession, slots: list[MaterialSlot]
) -> int | None:
    """Lowest slot index holding a spool or a preset, by either assignment path.

    Klipper systems keep the gate map and the slot assignment in step; systems of
    any other provider only ever get the assignment, so both have to be checked.
    """
    slot_ids = [slot.id for slot in slots]
    if not slot_ids:
        return None
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
    occupied.update(
        index_by_slot[slot_id] for slot_id in assignment_rows.scalars().all()
    )

    return min(occupied) if occupied else None


async def update_material_system(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
    payload: MaterialSystemUpdate,
) -> UserPrinterDevice:
    """Rename a material system or resize it to a declared number of slots."""
    system = await _require_material_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    if payload.name is not None:
        system.name = payload.name

    if payload.slot_count is not None:
        slots_result = await db.execute(
            select(MaterialSlot)
            .where(MaterialSlot.material_system_id == system.id)
            .order_by(MaterialSlot.provider_index)
        )
        slots = list(slots_result.scalars().all())
        by_index = {slot.provider_index: slot for slot in slots}
        for provider_index in range(payload.slot_count):
            if provider_index not in by_index:
                db.add(
                    MaterialSlot(
                        user_id=user_id,
                        material_system_id=system.id,
                        provider_index=provider_index,
                        kind="slot",
                    )
                )

        doomed = [slot for slot in slots if slot.provider_index >= payload.slot_count]
        if doomed:
            busy = await _first_occupied_slot_index(db, doomed)
            if busy is not None:
                raise_error(409, ERR_MATERIAL_SLOT_IN_USE, params={"index": busy + 1})
            await db.execute(
                delete(MaterialSlot).where(
                    MaterialSlot.id.in_([slot.id for slot in doomed])
                )
            )
        system.declared_slot_count = payload.slot_count
        if system.provider in KLIPPER_PROVIDERS:
            # The legacy gate map still gates manual assignment, so it has to
            # follow the declared size or the new slots refuse every spool.
            printer = await require_physical_printer(db, user_id, physical_printer_id)
            printer.gate_count = payload.slot_count

    await db.commit()
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


async def ensure_material_topology(
    db: AsyncSession,
    device: UserPrinterDevice,
    *,
    provider: str | None = None,
    gate_indices: set[int] | None = None,
) -> None:
    """Write what a provider reports about a printer's feed into the contract.

    Every provider owns its own system on the printer; a new one plugs in by
    passing its name instead of inheriting the Klipper pair.
    """
    provider = provider or ("happy_hare" if device.supports_hh else "legacy")
    siblings = (
        list(KLIPPER_PROVIDERS) if provider in KLIPPER_PROVIDERS else [provider]
    )
    indices = set(gate_indices or ())
    if device.gate_count is not None:
        indices.update(range(device.gate_count))
    if not device.supports_hh and not indices:
        return
    if indices:
        # A reported gate proves every lower gate exists, so the panel shows a
        # contiguous system instead of a hole where no spool has been seen yet.
        indices = set(range(max(indices) + 1))

    await db.flush()
    system = await db.scalar(
        select(MaterialSystem)
        .where(
            MaterialSystem.physical_printer_id == device.id,
            MaterialSystem.user_id == device.user_id,
            MaterialSystem.provider.in_(siblings),
        )
        .order_by(MaterialSystem.id)
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
    elif device.supports_hh:
        system.provider = "happy_hare"
        system.capabilities = list(HAPPY_HARE_CAPABILITIES)
        system.active = True
    elif system.provider == "manual":
        system.provider = provider

    existing_slots_result = await db.execute(
        select(MaterialSlot).where(MaterialSlot.material_system_id == system.id)
    )
    slots_by_index = {
        slot.provider_index: slot for slot in existing_slots_result.scalars().all()
    }
    for provider_index in sorted(indices):
        if provider_index not in slots_by_index:
            slot = MaterialSlot(
                user_id=device.user_id,
                material_system_id=system.id,
                provider_index=provider_index,
                kind="slot",
            )
            db.add(slot)
            await db.flush()
            slots_by_index[provider_index] = slot

    if (
        system.declared_slot_count is not None
        and indices
        and max(indices) + 1 > system.declared_slot_count
    ):
        # The machine reported more slots than the person declared; their answer
        # is stale, so ask again instead of hiding the extra slots.
        system.declared_slot_count = None

    if slots_by_index:
        states_result = await db.execute(
            select(PresetGateState).where(
                PresetGateState.device_id == device.id,
                PresetGateState.gate_index.in_(slots_by_index),
            )
        )
        for state in states_result.scalars().all():
            state.material_slot_id = slots_by_index[state.gate_index].id
            await sync_legacy_material_assignment(db, state)

    connector = await db.scalar(
        select(PhysicalPrinterConnector)
        .where(
            PhysicalPrinterConnector.physical_printer_id == device.id,
            PhysicalPrinterConnector.user_id == device.user_id,
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
    connector.capabilities = (
        list(HAPPY_HARE_CAPABILITIES) if device.supports_hh else []
    )
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
    await _shelve_spools(
        db, user_id, await _loaded_spool_ids_for_device(db, device_id)
    )


async def delete_material_system(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> UserPrinterDevice:
    """Remove one material system, returning its spools to the shelf.

    The printer keeps existing, and so does its key: the person can attach
    another system later without asking for a new one.
    """
    system = await _require_material_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )

    slots = list(
        (
            await db.execute(
                select(MaterialSlot).where(
                    MaterialSlot.material_system_id == system.id
                )
            )
        )
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
        spool_ids = set(gate_rows.scalars().all()) | set(
            assignment_rows.scalars().all()
        )

    if slot_ids:
        # The bindings go first: a spool only counts as free once nothing points
        # at it, and both tables are consulted for that.
        await db.execute(
            delete(MaterialSlotAssignment).where(
                MaterialSlotAssignment.material_slot_id.in_(slot_ids)
            )
        )
        await db.execute(
            delete(PresetGateState).where(
                PresetGateState.material_slot_id.in_(slot_ids)
            )
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
    if provider in KLIPPER_PROVIDERS:
        # The legacy gate map describes exactly this system, so it goes with it;
        # otherwise the next system would inherit a phantom slot count.
        printer.gate_count = None
    await db.commit()
    # The session keeps objects alive past commit, so the printer would answer
    # with the collection it loaded before the system was removed.
    db.expire_all()
    return await require_physical_printer(db, user_id, physical_printer_id)


async def delete_physical_printer(
    db: AsyncSession, user_id: int, physical_printer_id: int
) -> None:
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
                    select(MaterialSlot.id).where(
                        MaterialSlot.material_system_id.in_(system_ids)
                    )
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
    await db.execute(
        delete(PresetGateState).where(PresetGateState.device_id == printer.id)
    )
    await _shelve_spools(db, user_id, spool_ids)
    await db.delete(printer)
    await db.commit()
