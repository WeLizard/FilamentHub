"""Business logic for user spool (filament inventory) management."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import set_committed_value

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_FILAMENT_NOT_FOUND,
    ERR_SPOOL_EMPTY_ON_CREATE,
    ERR_SPOOL_LOCATION_CONFLICT,
    ERR_SPOOL_USED_EXCEEDS_INITIAL,
    raise_error,
)
from app.models.filament import Filament
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, MaterialSystem
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.preset_usage_event import PresetUsageEventType
from app.models.print_job import PrintJobMaterial
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.spool import (
    SpoolCreateRequest,
    SpoolFilamentInfo,
    SpoolResponse,
    SpoolUpdateRequest,
)
from app.services.spool_material_service import set_spool_filament_with_qr_guard
from app.services.spool_usage_service import record_spool_usage


def _read_projected_location(extra: dict) -> tuple[str, int]:
    try:
        printer = json.loads(extra.get("printer_name") or '""')
    except (json.JSONDecodeError, TypeError):
        printer = str(extra.get("printer_name") or "")
    try:
        gate = int(json.loads(extra.get("mmu_gate_map") or "-1"))
    except (json.JSONDecodeError, TypeError, ValueError):
        gate = -1
    return printer, gate


def clear_spool_location_projection(spool: UserSpool) -> None:
    extra = dict(spool.extra or {})
    # Keep the released location as a hint: identical spools of one catalog
    # SKU stay tellable apart by where each one was loaded last.
    printer, gate = _read_projected_location(extra)
    if printer and gate >= 0:
        extra["fhub_last_printer"] = json.dumps(printer)
        extra["fhub_last_gate"] = json.dumps(gate)
        extra["fhub_last_unloaded_at"] = json.dumps(datetime.now(timezone.utc).isoformat())
    extra["printer_name"] = json.dumps("")
    extra["mmu_gate_map"] = json.dumps(-1)
    spool.extra = extra


def set_spool_location_projection(
    spool: UserSpool, device: UserPrinterDevice, gate_index: int
) -> None:
    extra = dict(spool.extra or {})
    extra["printer_name"] = json.dumps(device.printer_hostname or device.name)
    extra["mmu_gate_map"] = json.dumps(gate_index)
    spool.extra = extra


async def lock_spool_row(db: AsyncSession, spool_id: int) -> None:
    """Serialize concurrent moves of the same physical spool (no-op on SQLite)."""
    await db.execute(select(UserSpool.id).where(UserSpool.id == spool_id).with_for_update())


async def lock_material_slots_for_spools(
    db: AsyncSession,
    spool_ids: set[int],
    *,
    user_id: int,
    additional_material_slot_ids: set[int] | None = None,
) -> dict[int, MaterialSlot]:
    """Lock one tenant's stable routes involved in a spool move, in ID order.

    Callers lock the physical spool rows first.  Discovering the route IDs is
    safe after that because every desired-assignment writer follows the same
    spool-first order.  The optional IDs cover the destination route before a
    legacy gate row is claimed.
    """
    material_slot_ids = set(additional_material_slot_ids or ())
    if spool_ids:
        legacy_ids = await db.scalars(
            select(PresetGateState.material_slot_id).where(
                PresetGateState.user_id == user_id,
                PresetGateState.spool_id.in_(spool_ids),
                PresetGateState.material_slot_id.is_not(None),
            )
        )
        material_slot_ids.update(legacy_ids.all())
        assignment_ids = await db.scalars(
            select(MaterialSlotAssignment.material_slot_id).where(
                MaterialSlotAssignment.user_id == user_id,
                MaterialSlotAssignment.spool_id.in_(spool_ids)
            )
        )
        material_slot_ids.update(assignment_ids.all())
    if not material_slot_ids:
        return {}
    material_slots = list(
        (
            await db.scalars(
                select(MaterialSlot)
                .where(
                    MaterialSlot.id.in_(material_slot_ids),
                    MaterialSlot.user_id == user_id,
                )
                .order_by(MaterialSlot.id)
                .with_for_update()
            )
        ).all()
    )
    return {slot.id: slot for slot in material_slots}


async def material_slot_ids_for_gate(
    db: AsyncSession,
    *,
    device_id: int,
    gate_index: int,
) -> set[int]:
    """Resolve legacy provider coordinates to their stable feed-route IDs."""
    return set(
        (
            await db.scalars(
                select(MaterialSlot.id)
                .join(MaterialSystem, MaterialSystem.id == MaterialSlot.material_system_id)
                .where(
                    MaterialSystem.physical_printer_id == device_id,
                    MaterialSystem.active.is_(True),
                    MaterialSlot.provider_index == gate_index,
                    MaterialSlot.active.is_(True),
                )
            )
        ).all()
    )


async def shelf_spool_if_unassigned(db: AsyncSession, spool: UserSpool) -> None:
    """Return a spool to the shelf once it has no current slot binding."""
    if await spool_has_gate_assignment(db, spool.id):
        return
    clear_spool_location_projection(spool)
    if spool.state not in {UserSpoolState.archived, UserSpoolState.empty}:
        spool.state = UserSpoolState.shelf


async def assign_spool_to_gate(
    db: AsyncSession,
    *,
    user_id: int,
    spool: UserSpool,
    device: UserPrinterDevice,
    gate_index: int,
    source: PresetGateStateSource,
) -> tuple[PresetGateState, int | None]:
    """Atomically move a physical spool into a specific device slot.

    Locks the spool row, releases every previous binding of this spool,
    then claims the target gate; a spool displaced from the target gate
    goes back to the shelf. Does not commit. Raises 409 when a concurrent
    move wins the race (unique index on active spool_id is the backstop).
    """
    displaced_spool_id = await db.scalar(
        select(PresetGateState.spool_id).where(
            PresetGateState.device_id == device.id,
            PresetGateState.gate_index == gate_index,
        )
    )
    involved_spool_ids = {
        spool_id for spool_id in {spool.id, displaced_spool_id} if spool_id is not None
    }
    for spool_id in sorted(involved_spool_ids):
        await lock_spool_row(db, spool_id)

    from app.services.material_contract_service import ensure_material_topology

    await ensure_material_topology(
        db,
        device,
        gate_indices={gate_index},
        sync_legacy_assignments=False,
    )
    target_material_slot_ids = await material_slot_ids_for_gate(
        db, device_id=device.id, gate_index=gate_index
    )
    await lock_material_slots_for_spools(
        db,
        involved_spool_ids,
        user_id=user_id,
        additional_material_slot_ids=target_material_slot_ids,
    )

    await clear_spool_gate_assignments(
        db,
        spool,
        source=source,
        except_device_id=device.id,
        except_gate_index=gate_index,
        except_material_slot_id=min(target_material_slot_ids, default=None),
    )
    # Old bindings must hit the DB before the new one to satisfy the
    # single-location unique index within the transaction.
    await db.flush()

    target_result = await db.execute(
        select(PresetGateState)
        .where(
            PresetGateState.device_id == device.id,
            PresetGateState.gate_index == gate_index,
        )
        .with_for_update()
    )
    target_state = target_result.scalars().first()
    displaced_spool_id = target_state.spool_id if target_state is not None else None
    now = datetime.now(timezone.utc)

    if target_state is None:
        target_state = PresetGateState(
            user_id=user_id,
            device_id=device.id,
            gate_index=gate_index,
            preset_id=None,
            spool_id=spool.id,
            source=source,
            source_ts=now,
            is_active=True,
        )
        db.add(target_state)
    else:
        target_state.spool_id = spool.id
        target_state.source = source
        target_state.source_ts = now
        target_state.is_active = True

    try:
        await db.flush()
    except IntegrityError:
        raise_error(409, ERR_SPOOL_LOCATION_CONFLICT)

    await ensure_material_topology(db, device, gate_indices={gate_index})

    if displaced_spool_id is not None and displaced_spool_id != spool.id:
        displaced_result = await db.execute(
            select(UserSpool).where(
                UserSpool.id == displaced_spool_id,
                UserSpool.user_id == user_id,
            )
        )
        displaced_spool = displaced_result.scalars().first()
        if displaced_spool is not None:
            await shelf_spool_if_unassigned(db, displaced_spool)

    set_spool_location_projection(spool, device, gate_index)
    spool.state = UserSpoolState.active
    return target_state, displaced_spool_id


async def release_spool_location(
    db: AsyncSession,
    spool: UserSpool,
    *,
    source: PresetGateStateSource = PresetGateStateSource.web_manual,
) -> None:
    """Atomically take a physical spool off any slot (shelf semantics).

    Does not commit; keeps archived/empty state untouched.
    """
    await lock_spool_row(db, spool.id)
    await clear_spool_gate_assignments(db, spool, source=source)
    await db.flush()
    clear_spool_location_projection(spool)
    if spool.state not in {UserSpoolState.archived, UserSpoolState.empty}:
        spool.state = UserSpoolState.shelf


async def clear_spool_gate_assignments(
    db: AsyncSession,
    spool: UserSpool,
    *,
    source: PresetGateStateSource = PresetGateStateSource.web_manual,
    except_device_id: int | None = None,
    except_gate_index: int | None = None,
    except_material_slot_id: int | None = None,
) -> int:
    """Clear current slot bindings for a physical spool without committing."""
    await lock_spool_row(db, spool.id)
    locked_material_slots = await lock_material_slots_for_spools(
        db,
        {spool.id},
        user_id=spool.user_id,
    )

    assignment_result = await db.execute(
        select(MaterialSlotAssignment)
        .where(MaterialSlotAssignment.spool_id == spool.id)
        .with_for_update()
    )
    assignments = list(assignment_result.scalars().all())

    result = await db.execute(
        select(PresetGateState).where(PresetGateState.spool_id == spool.id).with_for_update()
    )
    states = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    cleared = 0
    revision_slot_ids: set[int] = set()
    for gate_state in states:
        if (
            except_device_id is not None
            and except_gate_index is not None
            and gate_state.device_id == except_device_id
            and gate_state.gate_index == except_gate_index
        ):
            continue
        gate_state.spool_id = None
        gate_state.source = source
        gate_state.source_ts = now
        gate_state.is_active = True
        if gate_state.material_slot_id is not None:
            revision_slot_ids.add(gate_state.material_slot_id)
        cleared += 1

    for assignment in assignments:
        if assignment.material_slot_id == except_material_slot_id:
            continue
        assignment.spool_id = None
        assignment.source = source.value
        assignment.source_ts = now
        revision_slot_ids.add(assignment.material_slot_id)
        if assignment.preset_id is None:
            await db.delete(assignment)
            material_slot = locked_material_slots.get(assignment.material_slot_id)
            if material_slot is not None:
                set_committed_value(material_slot, "assignment", None)
        cleared += 1

    for material_slot_id in revision_slot_ids:
        material_slot = locked_material_slots.get(material_slot_id)
        if material_slot is not None:
            material_slot.assignment_revision += 1

    if cleared:
        clear_spool_location_projection(spool)
    return cleared


async def spool_has_gate_assignment(db: AsyncSession, spool_id: int) -> bool:
    result = await db.execute(
        select(PresetGateState.id).where(PresetGateState.spool_id == spool_id).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return True
    assignment_result = await db.execute(
        select(MaterialSlotAssignment.id)
        .where(MaterialSlotAssignment.spool_id == spool_id)
        .limit(1)
    )
    return assignment_result.scalar_one_or_none() is not None


def _validate_spool_weights(initial_weight_g: float, used_weight_g: float) -> None:
    if used_weight_g > initial_weight_g:
        raise_error(400, ERR_SPOOL_USED_EXCEEDS_INITIAL)


async def _load_filament_info(db: AsyncSession, filament_id: int) -> Filament | None:
    result = await db.execute(
        select(Filament).options(joinedload(Filament.brand)).where(Filament.id == filament_id)
    )
    return result.unique().scalars().first()


def _build_response(spool: UserSpool, filament: Filament | None) -> SpoolResponse:
    fil_info: SpoolFilamentInfo | None = None
    if filament is not None:
        fil_info = SpoolFilamentInfo(
            id=filament.id,
            name=filament.name,
            material_type=filament.material_type,
            color_name=filament.color_name,
            color_hex=filament.color_hex,
            brand_name=filament.brand.name if filament.brand is not None else None,
            price_per_kg=filament.price_per_kg,
            currency=filament.brand.currency if filament.brand is not None else None,
            required_nozzle_hrc=filament.required_nozzle_hrc,
        )
    extra = spool.extra or {}
    raw_currency = extra.get("currency")
    currency = raw_currency if isinstance(raw_currency, str) and raw_currency else None
    return SpoolResponse(
        id=spool.id,
        user_id=spool.user_id,
        filament_id=spool.filament_id,
        filament=fil_info,
        initial_weight_g=spool.initial_weight_g,
        used_weight_g=spool.used_weight_g,
        remaining_weight_g=spool.remaining_weight_g,
        remaining_pct=spool.remaining_pct,
        price=spool.price,
        currency=currency,
        state=spool.state.value,
        source=spool.source,
        lot_nr=spool.lot_nr,
        comment=spool.comment,
        created_at=spool.created_at,
        updated_at=spool.updated_at,
        last_used_at=spool.last_used_at,
        extra=spool.extra,
    )


async def list_spools(
    db: AsyncSession,
    user_id: int,
    *,
    filament_id: int | None = None,
) -> list[SpoolResponse]:
    query = select(UserSpool).where(UserSpool.user_id == user_id)
    if filament_id is not None:
        query = query.where(UserSpool.filament_id == filament_id)

    result = await db.execute(
        query.order_by(UserSpool.created_at.desc())
    )
    spools = list(result.scalars().all())

    # Batch load filaments
    fil_ids = {s.filament_id for s in spools if s.filament_id}
    filaments: dict[int, Filament] = {}
    if fil_ids:
        fil_result = await db.execute(
            select(Filament).options(joinedload(Filament.brand)).where(Filament.id.in_(fil_ids))
        )
        filaments = {f.id: f for f in fil_result.unique().scalars().all()}

    return [
        _build_response(s, filaments.get(s.filament_id) if s.filament_id else None) for s in spools
    ]


async def create_spool(
    db: AsyncSession,
    user: User,
    payload: SpoolCreateRequest,
) -> SpoolResponse:
    _validate_spool_weights(payload.initial_weight_g, payload.used_weight_g)
    if (
        payload.used_weight_g >= payload.initial_weight_g
        or payload.state == UserSpoolState.empty.value
    ):
        raise_error(400, ERR_SPOOL_EMPTY_ON_CREATE)

    if payload.filament_id is not None:
        filament = await _load_filament_info(db, payload.filament_id)
        if filament is None:
            raise_error(404, ERR_FILAMENT_NOT_FOUND)
    else:
        filament = None

    spool = UserSpool(
        user_id=user.id,
        filament_id=payload.filament_id,
        initial_weight_g=payload.initial_weight_g,
        used_weight_g=payload.used_weight_g,
        price=payload.price,
        extra={"currency": payload.currency} if payload.currency is not None else {},
        state=UserSpoolState(payload.state),
        source=payload.source,
        lot_nr=payload.lot_nr,
        comment=payload.comment,
    )
    db.add(spool)
    await db.commit()
    await db.refresh(spool)
    return _build_response(spool, filament)


async def update_spool(
    db: AsyncSession,
    user: User,
    spool_id: int,
    payload: SpoolUpdateRequest,
) -> SpoolResponse:
    result = await db.execute(select(UserSpool).where(UserSpool.id == spool_id))
    spool = result.scalars().first()
    if spool is None or spool.user_id != user.id:
        raise_error(404, ERR_ACCESS_DENIED)

    if "filament_id" in payload.model_fields_set:
        if payload.filament_id is not None:
            filament = await _load_filament_info(db, payload.filament_id)
            if filament is None:
                raise_error(404, ERR_FILAMENT_NOT_FOUND)
        else:
            filament = None
        spool = await set_spool_filament_with_qr_guard(
            db,
            spool=spool,
            filament_id=payload.filament_id,
        )
    else:
        filament = await _load_filament_info(db, spool.filament_id) if spool.filament_id else None

    previous_initial_weight = spool.initial_weight_g
    previous_used_weight = spool.used_weight_g
    previous_remaining_weight = spool.remaining_weight_g

    next_initial_weight = (
        payload.initial_weight_g if payload.initial_weight_g is not None else spool.initial_weight_g
    )
    next_used_weight = (
        payload.used_weight_g if payload.used_weight_g is not None else spool.used_weight_g
    )
    _validate_spool_weights(next_initial_weight, next_used_weight)
    spool.initial_weight_g = next_initial_weight
    spool.used_weight_g = next_used_weight
    if payload.state is not None:
        spool.state = UserSpoolState(payload.state)
    if "price" in payload.model_fields_set:
        spool.price = payload.price
    if "currency" in payload.model_fields_set:
        next_extra = dict(spool.extra or {})
        if payload.currency is None:
            next_extra.pop("currency", None)
        else:
            next_extra["currency"] = payload.currency
        spool.extra = next_extra
    if "lot_nr" in payload.model_fields_set:
        spool.lot_nr = payload.lot_nr
    if "comment" in payload.model_fields_set:
        spool.comment = payload.comment

    if spool.state == UserSpoolState.empty:
        spool.used_weight_g = spool.initial_weight_g
    elif spool.remaining_weight_g <= 0:
        spool.state = UserSpoolState.empty

    if (
        spool.initial_weight_g != previous_initial_weight
        or spool.used_weight_g != previous_used_weight
    ):
        await record_spool_usage(
            db,
            spool=spool,
            event_type=PresetUsageEventType.manual_adjust,
            delta_weight_g=spool.used_weight_g - previous_used_weight,
            meta={
                "reason": "spool_edit",
                "previous_initial_weight_g": previous_initial_weight,
                "previous_remaining_weight_g": previous_remaining_weight,
            },
        )

    if spool.state in {
        UserSpoolState.shelf,
        UserSpoolState.archived,
        UserSpoolState.empty,
    }:
        await clear_spool_gate_assignments(db, spool)
        clear_spool_location_projection(spool)

    await db.commit()
    await db.refresh(spool)
    return _build_response(spool, filament)


async def use_spool(
    db: AsyncSession,
    user: User,
    spool_id: int,
    delta_weight_g: float,
) -> SpoolResponse:
    result = await db.execute(select(UserSpool).where(UserSpool.id == spool_id))
    spool = result.scalars().first()
    if spool is None or spool.user_id != user.id:
        raise_error(404, ERR_ACCESS_DENIED)

    before = spool.used_weight_g
    spool.used_weight_g = min(
        spool.initial_weight_g,
        spool.used_weight_g + delta_weight_g,
    )
    await record_spool_usage(
        db,
        spool=spool,
        event_type=PresetUsageEventType.manual_adjust,
        delta_weight_g=spool.used_weight_g - before,
    )
    spool.last_used_at = datetime.now(timezone.utc)
    if spool.first_used_at is None:
        spool.first_used_at = spool.last_used_at

    if spool.remaining_weight_g <= 0:
        spool.state = UserSpoolState.empty
        await clear_spool_gate_assignments(db, spool)
        clear_spool_location_projection(spool)

    filament = await _load_filament_info(db, spool.filament_id) if spool.filament_id else None
    await db.commit()
    await db.refresh(spool)
    return _build_response(spool, filament)


async def delete_spool(db: AsyncSession, user: User, spool_id: int) -> None:
    result = await db.execute(select(UserSpool).where(UserSpool.id == spool_id))
    spool = result.scalars().first()
    if spool is None or spool.user_id != user.id:
        raise_error(404, ERR_ACCESS_DENIED)
    await db.execute(
        update(PrintJobMaterial).where(PrintJobMaterial.spool_id == spool.id).values(spool_id=None)
    )
    await db.delete(spool)
    await db.commit()
