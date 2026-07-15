"""Regression tests for the single-physical-location invariant of UserSpool.

One UserSpool.id has exactly one current location: shelf, one device slot,
or archive/empty. Several UserSpool of the same catalog Filament stay fully
independent. Moves are atomic; a true concurrent conflict yields 409.
"""

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.services import spool_service
from app.services.spool_service import (
    assign_spool_to_gate,
    release_spool_location,
)


async def _make_filament(db: AsyncSession, suffix: str) -> Filament:
    brand = Brand(name=f"Loc Brand {suffix}", slug=f"loc-brand-{suffix}", active=True)
    db.add(brand)
    await db.commit()
    await db.refresh(brand)

    filament = Filament(
        brand_id=brand.id,
        name=f"Loc Filament {suffix}",
        slug=f"loc-filament-{suffix}",
        material_type="PETG",
        active=True,
    )
    db.add(filament)
    await db.commit()
    await db.refresh(filament)
    return filament


async def _make_device(
    db: AsyncSession, user: User, suffix: str, gate_count: int = 8
) -> UserPrinterDevice:
    device = UserPrinterDevice(
        user_id=user.id,
        name=f"Loc Device {suffix}",
        device_fingerprint=f"loc-device-{suffix}",
        supports_hh=True,
        gate_count=gate_count,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def _make_spool(
    db: AsyncSession, user: User, filament: Filament, **overrides
) -> UserSpool:
    spool = UserSpool(
        user_id=user.id,
        filament_id=filament.id,
        initial_weight_g=1000.0,
        used_weight_g=0.0,
        state=UserSpoolState.shelf,
        source="manual",
        **overrides,
    )
    db.add(spool)
    await db.commit()
    await db.refresh(spool)
    return spool


async def _gate_rows_for_spool(db: AsyncSession, spool_id: int) -> list[PresetGateState]:
    result = await db.execute(
        select(PresetGateState).where(PresetGateState.spool_id == spool_id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_multiple_spools_of_one_filament_are_independent(
    db_session: AsyncSession, auth_user: User
):
    filament = await _make_filament(db_session, "multi")
    device = await _make_device(db_session, auth_user, "multi")
    spool_a = await _make_spool(db_session, auth_user, filament, lot_nr="lot-a")
    spool_b = await _make_spool(db_session, auth_user, filament, lot_nr="lot-b")

    await assign_spool_to_gate(
        db_session,
        user_id=auth_user.id,
        spool=spool_a,
        device=device,
        gate_index=0,
        source=PresetGateStateSource.web_manual,
    )
    await db_session.commit()

    assert spool_a.state == UserSpoolState.active
    assert spool_b.state == UserSpoolState.shelf
    assert await _gate_rows_for_spool(db_session, spool_a.id) != []
    assert await _gate_rows_for_spool(db_session, spool_b.id) == []


@pytest.mark.asyncio
async def test_move_shelf_to_slot(db_session: AsyncSession, auth_user: User):
    filament = await _make_filament(db_session, "shelf2slot")
    device = await _make_device(db_session, auth_user, "shelf2slot")
    spool = await _make_spool(db_session, auth_user, filament)

    state, displaced = await assign_spool_to_gate(
        db_session,
        user_id=auth_user.id,
        spool=spool,
        device=device,
        gate_index=3,
        source=PresetGateStateSource.web_manual,
    )
    await db_session.commit()

    assert displaced is None
    assert state.spool_id == spool.id
    assert state.gate_index == 3
    assert spool.state == UserSpoolState.active
    assert json.loads(spool.extra["mmu_gate_map"]) == 3


@pytest.mark.asyncio
async def test_move_slot_to_shelf(db_session: AsyncSession, auth_user: User):
    filament = await _make_filament(db_session, "slot2shelf")
    device = await _make_device(db_session, auth_user, "slot2shelf")
    spool = await _make_spool(db_session, auth_user, filament)

    await assign_spool_to_gate(
        db_session,
        user_id=auth_user.id,
        spool=spool,
        device=device,
        gate_index=1,
        source=PresetGateStateSource.web_manual,
    )
    await db_session.commit()

    await release_spool_location(db_session, spool)
    await db_session.commit()

    assert spool.state == UserSpoolState.shelf
    assert await _gate_rows_for_spool(db_session, spool.id) == []
    assert json.loads(spool.extra["mmu_gate_map"]) == -1
    assert json.loads(spool.extra["printer_name"]) == ""


@pytest.mark.asyncio
async def test_move_between_two_slots(db_session: AsyncSession, auth_user: User):
    filament = await _make_filament(db_session, "slot2slot")
    device = await _make_device(db_session, auth_user, "slot2slot")
    spool = await _make_spool(db_session, auth_user, filament)

    await assign_spool_to_gate(
        db_session,
        user_id=auth_user.id,
        spool=spool,
        device=device,
        gate_index=0,
        source=PresetGateStateSource.web_manual,
    )
    await db_session.commit()

    await assign_spool_to_gate(
        db_session,
        user_id=auth_user.id,
        spool=spool,
        device=device,
        gate_index=5,
        source=PresetGateStateSource.web_manual,
    )
    await db_session.commit()

    rows = await _gate_rows_for_spool(db_session, spool.id)
    assert [r.gate_index for r in rows] == [5]
    assert json.loads(spool.extra["mmu_gate_map"]) == 5


@pytest.mark.asyncio
async def test_concurrent_assignment_of_one_spool_conflicts(
    db_session: AsyncSession, auth_user: User, monkeypatch
):
    """A racing writer that re-binds the spool between our clear and our
    flush must surface as 409, not as a second silent location."""
    filament = await _make_filament(db_session, "race")
    device = await _make_device(db_session, auth_user, "race")
    spool = await _make_spool(db_session, auth_user, filament)

    await assign_spool_to_gate(
        db_session,
        user_id=auth_user.id,
        spool=spool,
        device=device,
        gate_index=0,
        source=PresetGateStateSource.web_manual,
    )
    await db_session.commit()
    spool_id = spool.id

    # Simulate the concurrent transaction winning the race: the clear step
    # sees no rows to release (as if another session holds the binding).
    async def _noop_clear(db, spool, **kwargs):
        return 0

    monkeypatch.setattr(spool_service, "clear_spool_gate_assignments", _noop_clear)

    with pytest.raises(HTTPException) as exc_info:
        await assign_spool_to_gate(
            db_session,
            user_id=auth_user.id,
            spool=spool,
            device=device,
            gate_index=2,
            source=PresetGateStateSource.web_manual,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "ERR_SPOOL_LOCATION_CONFLICT"

    await db_session.rollback()
    rows = await _gate_rows_for_spool(db_session, spool_id)
    assert [r.gate_index for r in rows] == [0]


@pytest.mark.asyncio
async def test_db_forbids_two_current_locations_for_one_spool(
    db_session: AsyncSession, auth_user: User
):
    """The partial unique index is the last line of defense below the service."""
    filament = await _make_filament(db_session, "invariant")
    device = await _make_device(db_session, auth_user, "invariant")
    spool = await _make_spool(db_session, auth_user, filament)

    await assign_spool_to_gate(
        db_session,
        user_id=auth_user.id,
        spool=spool,
        device=device,
        gate_index=0,
        source=PresetGateStateSource.web_manual,
    )
    await db_session.commit()

    from datetime import datetime, timezone

    db_session.add(
        PresetGateState(
            user_id=auth_user.id,
            device_id=device.id,
            gate_index=7,
            spool_id=spool.id,
            source=PresetGateStateSource.web_manual,
            source_ts=datetime.now(timezone.utc),
            is_active=True,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_two_identical_spools_keep_independent_locations(
    db_session: AsyncSession, auth_user: User
):
    filament = await _make_filament(db_session, "twins")
    device = await _make_device(db_session, auth_user, "twins")
    spool_a = await _make_spool(db_session, auth_user, filament)
    spool_b = await _make_spool(db_session, auth_user, filament)

    await assign_spool_to_gate(
        db_session,
        user_id=auth_user.id,
        spool=spool_a,
        device=device,
        gate_index=0,
        source=PresetGateStateSource.web_manual,
    )
    await db_session.commit()
    await assign_spool_to_gate(
        db_session,
        user_id=auth_user.id,
        spool=spool_b,
        device=device,
        gate_index=1,
        source=PresetGateStateSource.web_manual,
    )
    await db_session.commit()

    rows_a = await _gate_rows_for_spool(db_session, spool_a.id)
    rows_b = await _gate_rows_for_spool(db_session, spool_b.id)
    assert [r.gate_index for r in rows_a] == [0]
    assert [r.gate_index for r in rows_b] == [1]

    # Moving spool A onto B's slot displaces B back to the shelf,
    # without archiving it or touching its weights.
    _, displaced = await assign_spool_to_gate(
        db_session,
        user_id=auth_user.id,
        spool=spool_a,
        device=device,
        gate_index=1,
        source=PresetGateStateSource.web_manual,
    )
    await db_session.commit()

    assert displaced == spool_b.id
    await db_session.refresh(spool_b)
    assert spool_b.state == UserSpoolState.shelf
    assert await _gate_rows_for_spool(db_session, spool_b.id) == []
    rows_a = await _gate_rows_for_spool(db_session, spool_a.id)
    assert [r.gate_index for r in rows_a] == [1]
