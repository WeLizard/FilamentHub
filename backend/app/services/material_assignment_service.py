"""Provider-neutral desired assignments for material slots."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_MATERIAL_ASSIGNMENT_CONFLICT,
    ERR_MATERIAL_SLOT_NOT_FOUND,
    ERR_MATERIAL_SYSTEM_NOT_FOUND,
    ERR_PRESET_NOT_ACCESSIBLE,
    ERR_SPOOL_LOCATION_CONFLICT,
    ERR_SPOOL_NOT_ACCESSIBLE,
    raise_error,
)
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, MaterialSystem
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.material_contract import (
    MaterialSlotAssignmentUpdate,
    MaterialSystemAssignmentsClearRequest,
)
from app.schemas.preset_slot_sync import ManualAssignmentRequest
from app.services.spool_service import (
    clear_spool_gate_assignments,
    lock_material_slots_for_spools,
    shelf_spool_if_unassigned,
)


async def require_accessible_preset(
    db: AsyncSession,
    user_id: int,
    preset_id: int,
) -> None:
    preset = await db.scalar(select(Preset).where(Preset.id == preset_id))
    if preset is None:
        raise_error(404, ERR_PRESET_NOT_ACCESSIBLE, {"preset_id": preset_id})
    is_public = preset.moderation_status == PresetModerationStatus.APPROVED
    if not is_public and preset.user_id != user_id:
        raise_error(403, ERR_PRESET_NOT_ACCESSIBLE, {"preset_id": preset_id})


async def require_accessible_spool(
    db: AsyncSession,
    user_id: int,
    spool_id: int,
    *,
    require_usable: bool = False,
) -> UserSpool:
    spool = await db.scalar(
        select(UserSpool).where(
            UserSpool.id == spool_id,
            UserSpool.user_id == user_id,
        )
    )
    if (
        spool is None
        or require_usable
        and (
            spool.remaining_weight_g <= 0
            or spool.state in {UserSpoolState.archived, UserSpoolState.empty}
        )
    ):
        raise_error(404, ERR_SPOOL_NOT_ACCESSIBLE, {"spool_id": spool_id})
    return spool


async def _require_material_slot(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_slot_id: int,
) -> MaterialSlot:
    slot = await db.scalar(
        select(MaterialSlot)
        .join(MaterialSystem, MaterialSystem.id == MaterialSlot.material_system_id)
        .join(
            UserPrinterDevice,
            UserPrinterDevice.id == MaterialSystem.physical_printer_id,
        )
        .where(
            MaterialSlot.id == material_slot_id,
            MaterialSlot.user_id == user_id,
            MaterialSlot.active.is_(True),
            MaterialSystem.physical_printer_id == physical_printer_id,
            MaterialSystem.user_id == user_id,
            MaterialSystem.active.is_(True),
            UserPrinterDevice.user_id == user_id,
        )
        # selectinload, not joinedload: an outer join to an optional assignment or
        # gate state makes Postgres reject FOR UPDATE. SQLite tolerates it, so this
        # only breaks against the real database.
        .options(
            selectinload(MaterialSlot.material_system).selectinload(
                MaterialSystem.physical_printer
            ),
            selectinload(MaterialSlot.assignment),
            selectinload(MaterialSlot.legacy_gate_state),
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if slot is None:
        raise_error(404, ERR_MATERIAL_SLOT_NOT_FOUND)
    return slot


async def sync_legacy_material_assignment(
    db: AsyncSession,
    state: PresetGateState,
) -> None:
    """Mirror a legacy gate's desired fields into its provider-neutral slot."""
    if state.material_slot_id is None:
        return
    material_slot = await db.scalar(
        select(MaterialSlot)
        .where(MaterialSlot.id == state.material_slot_id)
        .options(selectinload(MaterialSlot.assignment))
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if material_slot is None:
        return
    state.material_slot = material_slot
    assignment = material_slot.assignment
    if state.preset_id is None and state.spool_id is None:
        if assignment is not None:
            material_slot.assignment = None
            material_slot.assignment_revision += 1
        return
    source = state.source.value if hasattr(state.source, "value") else str(state.source)
    if assignment is None:
        material_slot.assignment = MaterialSlotAssignment(
            user_id=state.user_id,
            preset_id=state.preset_id,
            spool_id=state.spool_id,
            source=source,
            source_ts=state.source_ts,
            active=True,
        )
        material_slot.assignment_revision += 1
        return
    desired_changed = (
        assignment.preset_id != state.preset_id
        or assignment.spool_id != state.spool_id
        or not assignment.active
    )
    assignment.preset_id = state.preset_id
    assignment.spool_id = state.spool_id
    assignment.source = source
    assignment.source_ts = state.source_ts
    assignment.active = True
    if desired_changed:
        material_slot.assignment_revision += 1


def _assignment_conflict_params(slots: list[MaterialSlot]) -> dict:
    current_slots = []
    for slot in sorted(slots, key=lambda item: item.id):
        assignment = slot.assignment
        current_slots.append(
            {
                "material_slot_id": slot.id,
                "current_revision": slot.assignment_revision,
                "current_preset_id": assignment.preset_id if assignment else None,
                "current_spool_id": assignment.spool_id if assignment else None,
            }
        )
    params: dict = {"slots": current_slots}
    if len(current_slots) == 1:
        params.update(current_slots[0])
    return params


def _raise_assignment_conflict(slots: list[MaterialSlot]) -> None:
    raise_error(409, ERR_MATERIAL_ASSIGNMENT_CONFLICT, _assignment_conflict_params(slots))


async def update_material_slot_assignment(
    db: AsyncSession,
    user: User,
    *,
    physical_printer_id: int,
    material_slot_id: int,
    payload: MaterialSlotAssignmentUpdate,
    source: PresetGateStateSource = PresetGateStateSource.web_manual,
) -> None:
    fields = payload.model_fields_set
    # Every assignment writer uses the same lock order: physical spools first,
    # then stable feed routes.  The expected identity is the current spool for a
    # fresh command; a stale/foreign value is ignored by this tenant-scoped lock
    # and rejected after the slot row is locked and re-read.
    requested_spool_id = (
        payload.spool_id
        if "spool_id" in fields
        else payload.expected_spool_id
    )
    lock_ids = sorted(
        spool_id
        for spool_id in {payload.expected_spool_id, requested_spool_id}
        if spool_id is not None
    )
    for spool_id in lock_ids:
        await db.execute(
            select(UserSpool.id)
            .where(UserSpool.id == spool_id, UserSpool.user_id == user.id)
            .with_for_update()
        )
    await lock_material_slots_for_spools(
        db,
        set(lock_ids),
        user_id=user.id,
        additional_material_slot_ids={material_slot_id},
    )

    slot = await _require_material_slot(
        db,
        user_id=user.id,
        physical_printer_id=physical_printer_id,
        material_slot_id=material_slot_id,
    )
    current = slot.assignment
    next_preset_id = (
        payload.preset_id
        if "preset_id" in fields
        else current.preset_id if current is not None else None
    )
    next_spool_id = (
        payload.spool_id
        if "spool_id" in fields
        else current.spool_id if current is not None else None
    )

    current_preset_id = current.preset_id if current is not None else None
    current_spool_id = current.spool_id if current is not None else None
    legacy_state = slot.legacy_gate_state
    requires_legacy_projection = legacy_state is not None or (
        slot.kind == "slot"
        and slot.material_system.provider in {"happy_hare", "legacy"}
    )
    legacy_matches = not requires_legacy_projection or (
        legacy_state is not None
        and legacy_state.preset_id == next_preset_id
        and legacy_state.spool_id == next_spool_id
    )
    if (
        (next_preset_id, next_spool_id) == (current_preset_id, current_spool_id)
        and legacy_matches
    ):
        return
    if (
        payload.expected_revision != slot.assignment_revision
        or payload.expected_spool_id != current_spool_id
    ):
        _raise_assignment_conflict([slot])

    if next_preset_id is not None:
        await require_accessible_preset(db, user.id, next_preset_id)
    next_spool = None
    if next_spool_id is not None:
        next_spool = await require_accessible_spool(
            db, user.id, next_spool_id, require_usable=True
        )

    # Legacy HH slots keep the existing Spoolman-compatible writer as their
    # compatibility surface; it dual-writes back into this assignment table.
    if requires_legacy_projection:
        from app.services.preset_slot_sync_service import handle_manual_assignment

        device = slot.material_system.physical_printer
        legacy_payload = ManualAssignmentRequest(
            device_fingerprint=device.device_fingerprint
            or f"logical:{device.logical_id}",
            gate=slot.provider_index,
            preset_id=payload.preset_id,
            spool_id=payload.spool_id,
        )
        await handle_manual_assignment(
            db,
            user,
            legacy_payload,
            source,
            device=device,
            preset_id_provided="preset_id" in fields,
            spool_id_provided="spool_id" in fields,
        )
        return

    old_spool_id = current_spool_id
    if next_spool is not None:
        await clear_spool_gate_assignments(
            db,
            next_spool,
            source=source,
            except_material_slot_id=slot.id,
        )
        await db.flush()

    now = datetime.now(timezone.utc)
    if next_preset_id is None and next_spool_id is None:
        if current is not None:
            slot.assignment = None
    elif current is None:
        slot.assignment = MaterialSlotAssignment(
            user_id=user.id,
            preset_id=next_preset_id,
            spool_id=next_spool_id,
            source=source.value,
            source_ts=now,
            active=True,
        )
    else:
        current.preset_id = next_preset_id
        current.spool_id = next_spool_id
        current.source = source.value
        current.source_ts = now
        current.active = True
    slot.assignment_revision += 1

    try:
        await db.flush()
    except IntegrityError:
        raise_error(409, ERR_SPOOL_LOCATION_CONFLICT)

    if old_spool_id is not None and old_spool_id != next_spool_id:
        old_spool = await require_accessible_spool(db, user.id, old_spool_id)
        await shelf_spool_if_unassigned(db, old_spool)
    if next_spool is not None:
        next_spool.state = UserSpoolState.active
    await db.commit()


async def clear_material_system_assignments(
    db: AsyncSession,
    user: User,
    *,
    physical_printer_id: int,
    material_system_id: int,
    payload: MaterialSystemAssignmentsClearRequest,
) -> int:
    system_exists = await db.scalar(
        select(MaterialSystem.id).where(
            MaterialSystem.id == material_system_id,
            MaterialSystem.physical_printer_id == physical_printer_id,
            MaterialSystem.user_id == user.id,
        )
    )
    if system_exists is None:
        raise_error(404, ERR_MATERIAL_SYSTEM_NOT_FOUND)

    current_assignment_spool_ids = set(
        (
            await db.scalars(
                select(MaterialSlotAssignment.spool_id)
                .join(MaterialSlot)
                .join(MaterialSystem)
                .where(
                    MaterialSystem.id == material_system_id,
                    MaterialSystem.physical_printer_id == physical_printer_id,
                    MaterialSystem.user_id == user.id,
                    MaterialSlot.user_id == user.id,
                    MaterialSlotAssignment.spool_id.is_not(None),
                )
            )
        ).all()
    )
    current_legacy_spool_ids = set(
        (
            await db.scalars(
                select(PresetGateState.spool_id)
                .join(MaterialSlot, MaterialSlot.id == PresetGateState.material_slot_id)
                .join(MaterialSystem)
                .where(
                    MaterialSystem.id == material_system_id,
                    MaterialSystem.physical_printer_id == physical_printer_id,
                    MaterialSystem.user_id == user.id,
                    MaterialSlot.user_id == user.id,
                    PresetGateState.spool_id.is_not(None),
                )
            )
        ).all()
    )
    # Match the single-slot writer and legacy spool moves: lock every observed
    # and expected physical spool before locking the system's stable routes.
    for spool_id in sorted(
        current_assignment_spool_ids
        | current_legacy_spool_ids
        | {
            item.expected_spool_id
            for item in payload.slots
            if item.expected_spool_id is not None
        }
    ):
        await db.execute(
            select(UserSpool.id)
            .where(UserSpool.id == spool_id, UserSpool.user_id == user.id)
            .with_for_update()
        )
    slots = list(
        (
            await db.execute(
                select(MaterialSlot)
                .join(MaterialSystem)
                .where(
                    MaterialSystem.id == material_system_id,
                    MaterialSystem.physical_printer_id == physical_printer_id,
                    MaterialSystem.user_id == user.id,
                    MaterialSlot.user_id == user.id,
                )
                .order_by(MaterialSlot.id)
                .options(
                    selectinload(MaterialSlot.assignment),
                    selectinload(MaterialSlot.legacy_gate_state),
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        )
        .scalars()
        .unique()
        .all()
    )
    if not slots:
        return 0

    expectations = {
        item.material_slot_id: item
        for item in payload.slots
    }
    if set(expectations) != {slot.id for slot in slots}:
        _raise_assignment_conflict(slots)

    already_clear = all(
        (slot.assignment is None or (
            slot.assignment.preset_id is None and slot.assignment.spool_id is None
        ))
        and (
            slot.legacy_gate_state is None
            or (
                slot.legacy_gate_state.preset_id is None
                and slot.legacy_gate_state.spool_id is None
            )
        )
        for slot in slots
    )
    if already_clear:
        return 0

    stale_slots = []
    for slot in slots:
        expectation = expectations[slot.id]
        current_spool_id = slot.assignment.spool_id if slot.assignment else None
        if (
            expectation.expected_revision != slot.assignment_revision
            or expectation.expected_spool_id != current_spool_id
        ):
            stale_slots.append(slot)
    if stale_slots:
        _raise_assignment_conflict(slots)

    spool_ids = {
        spool_id
        for slot in slots
        for spool_id in (
            slot.assignment.spool_id if slot.assignment is not None else None,
            slot.legacy_gate_state.spool_id
            if slot.legacy_gate_state is not None
            else None,
        )
        if spool_id is not None
    }
    now = datetime.now(timezone.utc)
    cleared = 0
    for slot in slots:
        had_assignment = slot.assignment is not None and (
            slot.assignment.preset_id is not None
            or slot.assignment.spool_id is not None
        )
        state = slot.legacy_gate_state
        had_legacy = state is not None and (
            state.preset_id is not None or state.spool_id is not None
        )
        if slot.assignment is not None:
            slot.assignment = None
        if state is not None:
            state.preset_id = None
            state.spool_id = None
            state.source = PresetGateStateSource.web_manual
            state.source_ts = now
            state.is_active = True
        if had_assignment or had_legacy:
            slot.assignment_revision += 1
            cleared += 1

    await db.flush()
    if spool_ids:
        spools = (
            await db.execute(
                select(UserSpool).where(
                    UserSpool.id.in_(spool_ids), UserSpool.user_id == user.id
                )
            )
        ).scalars()
        for spool in spools:
            await shelf_spool_if_unassigned(db, spool)
    await db.commit()
    return cleared
