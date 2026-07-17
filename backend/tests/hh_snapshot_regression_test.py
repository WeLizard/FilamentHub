"""Regression tests for HH snapshot ingestion (MATERIAL-FOUNDATION-1).

Locks the observed/desired boundary of handle_hh_snapshot:
- snapshots only ever write the observed hh_* fields; desired assignment
  (preset_id/spool_id) is never touched and rows are never deleted;
- an explicit empty gates list is a fresh "all gates empty" observation;
- out-of-order snapshots are ignored per gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.preset_slot_sync import HHGateItem, HHSnapshotRequest
from app.services.preset_slot_sync_service import handle_hh_snapshot

FINGERPRINT = "device-hh-snapshot-regression"


async def _seed_user_device(db: AsyncSession) -> tuple[User, UserPrinterDevice]:
    user = User(
        email="hh-snapshot-regression@example.com",
        username="hh_snapshot_regression_user",
        password_hash="not-used",
        active=True,
    )
    device = UserPrinterDevice(
        user=user,
        name="HH Regression Device",
        device_fingerprint=FINGERPRINT,
        supports_hh=True,
        gate_count=4,
    )
    db.add_all([user, device])
    await db.commit()
    await db.refresh(user)
    await db.refresh(device)
    return user, device


async def _seed_gate_states(
    db: AsyncSession, user: User, device: UserPrinterDevice, ts: datetime
) -> list[PresetGateState]:
    states = [
        PresetGateState(
            user_id=user.id,
            device_id=device.id,
            gate_index=0,
            preset_id=101,
            spool_id=None,
            hh_material="PLA",
            hh_color_hex="FFFFFF",
            hh_status=1,
            source=PresetGateStateSource.hh_snapshot,
            source_ts=ts,
            is_active=True,
        ),
        PresetGateState(
            user_id=user.id,
            device_id=device.id,
            gate_index=1,
            preset_id=None,
            spool_id=None,
            hh_material="PETG",
            hh_color_hex="B2C9E6",
            hh_status=2,
            source=PresetGateStateSource.hh_snapshot,
            source_ts=ts,
            is_active=True,
        ),
    ]
    db.add_all(states)
    await db.commit()
    for state in states:
        await db.refresh(state)
    return states


def _snapshot(gates: list[HHGateItem], ts: datetime, gate_count: int = 4) -> HHSnapshotRequest:
    return HHSnapshotRequest(
        device_fingerprint=FINGERPRINT,
        gate_count=gate_count,
        snapshot_ts=ts,
        gates=gates,
    )


@pytest.mark.asyncio
async def test_empty_snapshot_is_a_fresh_all_empty_observation(db_session: AsyncSession):
    """gates=[] marks every known gate as observed-empty without touching
    desired assignment or deleting rows."""
    user, device = await _seed_user_device(db_session)
    old_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
    await _seed_gate_states(db_session, user, device, old_ts)

    new_ts = datetime.now(timezone.utc)
    _, updated, mismatches = await handle_hh_snapshot(
        db_session, user, _snapshot([], new_ts)
    )

    assert updated == 2
    assert mismatches == []
    result = await db_session.execute(
        select(PresetGateState)
        .where(PresetGateState.device_id == device.id)
        .order_by(PresetGateState.gate_index)
    )
    states = list(result.scalars().all())
    assert len(states) == 2  # no rows deleted, none created
    for state in states:
        assert state.hh_status == 0
        assert state.hh_material is None
        assert state.hh_color_hex is None
    assert states[0].preset_id == 101  # desired assignment untouched

    await db_session.refresh(device)
    assert device.last_seen_at is not None


@pytest.mark.asyncio
async def test_stale_empty_snapshot_is_ignored(db_session: AsyncSession):
    """An empty snapshot older than the stored gate state changes nothing."""
    user, device = await _seed_user_device(db_session)
    current_ts = datetime.now(timezone.utc)
    await _seed_gate_states(db_session, user, device, current_ts)

    stale_ts = current_ts - timedelta(minutes=5)
    _, updated, _ = await handle_hh_snapshot(db_session, user, _snapshot([], stale_ts))

    assert updated == 0
    result = await db_session.execute(
        select(PresetGateState)
        .where(PresetGateState.device_id == device.id)
        .order_by(PresetGateState.gate_index)
    )
    states = list(result.scalars().all())
    assert states[0].hh_material == "PLA"
    assert states[0].hh_status == 1
    assert states[1].hh_material == "PETG"
    assert states[1].hh_status == 2


@pytest.mark.asyncio
async def test_status_zero_gate_keeps_desired_assignment(db_session: AsyncSession):
    """A gate reported empty updates observed fields only — the assigned
    preset stays (the observed/desired boundary of #14798 discussions)."""
    user, device = await _seed_user_device(db_session)
    old_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
    await _seed_gate_states(db_session, user, device, old_ts)

    new_ts = datetime.now(timezone.utc)
    _, updated, _ = await handle_hh_snapshot(
        db_session,
        user,
        _snapshot([HHGateItem(gate=0, status=0)], new_ts),
    )

    assert updated == 1
    result = await db_session.execute(
        select(PresetGateState).where(
            PresetGateState.device_id == device.id,
            PresetGateState.gate_index == 0,
        )
    )
    state = result.scalars().one()
    assert state.hh_status == 0
    assert state.hh_material is None
    assert state.preset_id == 101


@pytest.mark.asyncio
async def test_partial_snapshot_leaves_missing_gates_untouched(db_session: AsyncSession):
    """Gates absent from the payload keep their previous observation."""
    user, device = await _seed_user_device(db_session)
    old_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
    await _seed_gate_states(db_session, user, device, old_ts)

    new_ts = datetime.now(timezone.utc)
    _, updated, _ = await handle_hh_snapshot(
        db_session,
        user,
        _snapshot([HHGateItem(gate=0, status=1, material="ABS", color_hex="112233")], new_ts),
    )

    assert updated == 1
    result = await db_session.execute(
        select(PresetGateState)
        .where(PresetGateState.device_id == device.id)
        .order_by(PresetGateState.gate_index)
    )
    states = list(result.scalars().all())
    assert states[0].hh_material == "ABS"
    assert states[1].hh_material == "PETG"  # untouched
    assert states[1].source_ts == old_ts


@pytest.mark.asyncio
async def test_out_of_order_gate_snapshot_is_ignored(db_session: AsyncSession):
    """A per-gate item older than the stored state does not overwrite it."""
    user, device = await _seed_user_device(db_session)
    current_ts = datetime.now(timezone.utc)
    await _seed_gate_states(db_session, user, device, current_ts)

    stale_ts = current_ts - timedelta(minutes=3)
    _, updated, _ = await handle_hh_snapshot(
        db_session,
        user,
        _snapshot([HHGateItem(gate=1, status=0, material="TPU")], stale_ts),
    )

    assert updated == 0
    result = await db_session.execute(
        select(PresetGateState).where(
            PresetGateState.device_id == device.id,
            PresetGateState.gate_index == 1,
        )
    )
    state = result.scalars().one()
    assert state.hh_material == "PETG"
    assert state.hh_status == 2


@pytest.mark.asyncio
async def test_snapshot_autoregisters_unknown_device(db_session: AsyncSession):
    """Current behavior lock: an unknown fingerprint registers a device with
    supports_hh, the payload gate_count and a fresh adapter-link touch."""
    user = User(
        email="hh-snapshot-autoreg@example.com",
        username="hh_snapshot_autoreg_user",
        password_hash="not-used",
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    device, updated, _ = await handle_hh_snapshot(
        db_session,
        user,
        HHSnapshotRequest(
            device_fingerprint="orca:autoreg:printer",
            gate_count=8,
            snapshot_ts=datetime.now(timezone.utc),
            gates=[],
        ),
    )

    assert device.id is not None
    assert device.supports_hh is True
    assert device.gate_count == 8
    assert device.last_seen_at is not None
    assert updated == 0  # no known gates yet — nothing to mark empty
