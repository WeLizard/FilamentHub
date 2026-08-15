"""Tests for preset slot sync service critical paths."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.preset_slot_sync import ManualAssignmentRequest
from app.services.preset_slot_sync_service import (
    _upsert_gate_state,
    handle_manual_assignment,
)


async def _assign_from_web(
    db: AsyncSession,
    user: User,
    device: UserPrinterDevice,
    gate: int,
    spool_id: int,
) -> None:
    await handle_manual_assignment(
        db,
        user,
        ManualAssignmentRequest(
            device_fingerprint=device.device_fingerprint,
            gate=gate,
            spool_id=spool_id,
        ),
        PresetGateStateSource.web_manual,
        device=device,
        preset_id_provided=False,
        spool_id_provided=True,
    )


async def _seed_user_device(db: AsyncSession) -> tuple[User, UserPrinterDevice]:
    user = User(
        email="slot-sync-test@example.com",
        username="slot_sync_test_user",
        password_hash="not-used",
        active=True,
    )
    device = UserPrinterDevice(
        user=user,
        name="Test Device",
        device_fingerprint="device-slot-sync-test",
        supports_hh=True,
        gate_count=4,
    )
    db.add_all([user, device])
    await db.commit()
    await db.refresh(user)
    await db.refresh(device)
    return user, device


@pytest.mark.asyncio
async def test_upsert_gate_state_should_preserve_priority_and_ignore_old_hh_snapshot(
    db_session: AsyncSession,
):
    """HH snapshot must win over lower-priority source and over out-of-order HH update."""
    user, device = await _seed_user_device(db_session)

    hh_new_ts = datetime.now(timezone.utc)
    hh_old_ts = hh_new_ts - timedelta(minutes=5)

    first = await _upsert_gate_state(
        db_session,
        user_id=user.id,
        device_id=device.id,
        gate_index=0,
        source=PresetGateStateSource.hh_snapshot,
        source_ts=hh_new_ts,
        preset_id_provided=False,
        spool_id_provided=False,
        hh_material="PLA",
        hh_color_hex="FFFFFF",
        hh_status=1,
    )
    await db_session.flush()

    second = await _upsert_gate_state(
        db_session,
        user_id=user.id,
        device_id=device.id,
        gate_index=0,
        source=PresetGateStateSource.manual_orca,
        source_ts=hh_new_ts + timedelta(minutes=1),
        preset_id=999,
        preset_id_provided=True,
        spool_id=777,
        spool_id_provided=True,
    )
    await db_session.flush()

    third = await _upsert_gate_state(
        db_session,
        user_id=user.id,
        device_id=device.id,
        gate_index=0,
        source=PresetGateStateSource.hh_snapshot,
        source_ts=hh_old_ts,
        preset_id_provided=False,
        spool_id_provided=False,
        hh_material="ABS",
        hh_color_hex="000000",
        hh_status=0,
    )
    await db_session.commit()

    states_result = await db_session.execute(
        select(PresetGateState).where(
            PresetGateState.device_id == device.id,
            PresetGateState.gate_index == 0,
        )
    )
    states = list(states_result.scalars().all())

    assert len(states) == 1
    state = states[0]
    assert first.id == second.id == third.id == state.id
    assert state.source == PresetGateStateSource.hh_snapshot
    assert state.source_ts == hh_new_ts
    assert state.hh_material == "PLA"
    assert state.hh_color_hex == "FFFFFF"
    assert state.hh_status == 1
    assert state.preset_id is None
    assert state.spool_id is None


@pytest.mark.asyncio
async def test_hh_upsert_updates_explicit_assignment_fields_on_sqlite_too(
    db_session: AsyncSession,
):
    """SQLite fallback must match the PostgreSQL upsert for provided fields."""
    user, device = await _seed_user_device(db_session)
    first_spool = UserSpool(
        user_id=user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.active,
        source="manual",
    )
    second_spool = UserSpool(
        user_id=user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.active,
        source="manual",
    )
    db_session.add_all([first_spool, second_spool])
    await db_session.flush()
    now = datetime.now(timezone.utc)

    await _upsert_gate_state(
        db_session,
        user_id=user.id,
        device_id=device.id,
        gate_index=0,
        source=PresetGateStateSource.web_manual,
        source_ts=now,
        spool_id=first_spool.id,
        spool_id_provided=True,
    )
    await db_session.flush()
    state = await _upsert_gate_state(
        db_session,
        user_id=user.id,
        device_id=device.id,
        gate_index=0,
        source=PresetGateStateSource.hh_snapshot,
        source_ts=now + timedelta(seconds=1),
        spool_id=second_spool.id,
        spool_id_provided=True,
        hh_material="PETG",
        hh_color_hex="00FF00",
        hh_status=1,
    )
    await db_session.flush()

    assert state.spool_id == second_spool.id
    assert state.hh_material == "PETG"
    assert state.hh_color_hex == "00FF00"
    assert state.hh_status == 1


@pytest.mark.asyncio
async def test_web_assignment_can_override_a_provider_report_source(
    db_session: AsyncSession,
):
    user, device = await _seed_user_device(db_session)
    now = datetime.now(timezone.utc)
    await _upsert_gate_state(
        db_session,
        user_id=user.id,
        device_id=device.id,
        gate_index=0,
        source=PresetGateStateSource.provider_report,
        source_ts=now,
        preset_id_provided=False,
        spool_id_provided=False,
    )
    await db_session.flush()
    state = await _upsert_gate_state(
        db_session,
        user_id=user.id,
        device_id=device.id,
        gate_index=0,
        source=PresetGateStateSource.web_manual,
        source_ts=now + timedelta(seconds=1),
        preset_id_provided=False,
        spool_id_provided=False,
    )

    assert state.source == PresetGateStateSource.web_manual


@pytest.mark.asyncio
async def test_web_assignment_moves_one_physical_spool_between_gates(
    db_session: AsyncSession,
):
    """A spool has one physical location; moving it clears its previous gate."""
    user, device = await _seed_user_device(db_session)
    first_spool = UserSpool(
        user_id=user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="qr",
    )
    second_spool = UserSpool(
        user_id=user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add_all([first_spool, second_spool])
    await db_session.commit()
    await db_session.refresh(first_spool)
    await db_session.refresh(second_spool)

    await _assign_from_web(db_session, user, device, 0, first_spool.id)
    await _assign_from_web(db_session, user, device, 1, first_spool.id)

    moved_states_result = await db_session.execute(
        select(PresetGateState)
        .where(PresetGateState.device_id == device.id)
        .order_by(PresetGateState.gate_index)
    )
    moved_states = list(moved_states_result.scalars().all())
    await db_session.refresh(first_spool)
    assert [state.spool_id for state in moved_states] == [None, first_spool.id]
    assert first_spool.state == UserSpoolState.active
    assert first_spool.extra["printer_name"] == '"Test Device"'
    assert first_spool.extra["mmu_gate_map"] == "1"

    await _assign_from_web(db_session, user, device, 1, second_spool.id)

    await db_session.refresh(first_spool)
    await db_session.refresh(second_spool)
    assert first_spool.state == UserSpoolState.shelf
    assert first_spool.extra["printer_name"] == '""'
    assert first_spool.extra["mmu_gate_map"] == "-1"
    assert second_spool.state == UserSpoolState.active
    assert second_spool.extra["printer_name"] == '"Test Device"'
    assert second_spool.extra["mmu_gate_map"] == "1"
