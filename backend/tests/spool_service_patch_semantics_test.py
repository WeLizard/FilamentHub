"""Tests for spool service PATCH nullable semantics via model_fields_set."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.spool import SpoolCreateRequest, SpoolUpdateRequest
from app.services.spool_service import create_spool, update_spool, use_spool


async def _seed_spool_for_patch_test(db: AsyncSession) -> tuple[User, UserSpool, Filament]:
    user = User(
        email="spool-patch-test@example.com",
        username="spool_patch_test_user",
        password_hash="not-used",
        active=True,
    )
    brand = Brand(name="Patch Brand", slug="patch-brand", verified=True, active=True)
    filament = Filament(
        brand=brand,
        name="Patch PLA",
        slug="patch-pla",
        material_type="PLA",
        color_name="White",
        color_hex="#FFFFFF",
        diameter=1.75,
        density=1.24,
        spool_weight=1000.0,
        active=True,
    )
    spool = UserSpool(
        user=user,
        filament=filament,
        initial_weight_g=1000.0,
        used_weight_g=10.0,
        state=UserSpoolState.active,
        source="manual",
        lot_nr="LOT-ABC",
        comment="seed-comment",
    )
    db.add_all([user, brand, filament, spool])
    await db.commit()
    await db.refresh(user)
    await db.refresh(filament)
    await db.refresh(spool)
    return user, spool, filament


@pytest.mark.asyncio
async def test_update_spool_should_clear_nullable_fields_when_explicit_null(
    db_session: AsyncSession,
):
    """PATCH with explicit null should clear filament_id, lot_nr and comment."""
    user, spool, _ = await _seed_spool_for_patch_test(db_session)

    payload = SpoolUpdateRequest(
        filament_id=None,
        lot_nr=None,
        comment=None,
    )

    result = await update_spool(db_session, user, spool.id, payload)

    assert result.id == spool.id
    assert result.filament_id is None
    assert result.lot_nr is None
    assert result.comment is None


@pytest.mark.asyncio
async def test_update_spool_should_keep_nullable_fields_when_not_provided(
    db_session: AsyncSession,
):
    """PATCH without nullable fields should keep previous values unchanged."""
    user, spool, filament = await _seed_spool_for_patch_test(db_session)

    payload = SpoolUpdateRequest(initial_weight_g=1200.0)

    result = await update_spool(db_session, user, spool.id, payload)

    assert result.initial_weight_g == pytest.approx(1200.0)
    assert result.filament_id == filament.id
    assert result.lot_nr == "LOT-ABC"
    assert result.comment == "seed-comment"


@pytest.mark.asyncio
async def test_create_spool_defaults_to_shelf_and_allows_repeat_purchase(
    db_session: AsyncSession,
):
    """The material QR identifies a SKU, not one unique physical spool."""
    user, _, filament = await _seed_spool_for_patch_test(db_session)
    payload = SpoolCreateRequest(
        filament_id=filament.id,
        initial_weight_g=1000,
        source="qr",
    )

    first = await create_spool(db_session, user, payload)
    second = await create_spool(db_session, user, payload)

    assert first.id != second.id
    assert first.filament_id == second.filament_id == filament.id
    assert first.state == second.state == UserSpoolState.shelf.value
    assert first.source == second.source == "qr"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("used_weight_g", "state"),
    [
        (1000.0, UserSpoolState.shelf.value),
        (0.0, UserSpoolState.empty.value),
    ],
)
async def test_create_spool_rejects_already_empty_spool(
    db_session: AsyncSession,
    used_weight_g: float,
    state: str,
):
    user, _, filament = await _seed_spool_for_patch_test(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await create_spool(
            db_session,
            user,
            SpoolCreateRequest(
                filament_id=filament.id,
                initial_weight_g=1000,
                used_weight_g=used_weight_g,
                state=state,
            ),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "ERR_SPOOL_EMPTY_ON_CREATE"


@pytest.mark.asyncio
async def test_putting_spool_on_shelf_clears_gate_binding_and_projection(
    db_session: AsyncSession,
):
    user, spool, _ = await _seed_spool_for_patch_test(db_session)
    device = UserPrinterDevice(
        user_id=user.id,
        name="Shelf Device",
        device_fingerprint="shelf-device",
        supports_hh=True,
        gate_count=4,
    )
    db_session.add(device)
    await db_session.flush()
    gate_state = PresetGateState(
        user_id=user.id,
        device_id=device.id,
        gate_index=2,
        spool_id=spool.id,
        source=PresetGateStateSource.web_manual,
        source_ts=datetime.now(timezone.utc),
        is_active=True,
    )
    spool.extra = {"printer_name": '"Shelf Device"', "mmu_gate_map": "2"}
    db_session.add(gate_state)
    await db_session.commit()

    result = await update_spool(
        db_session,
        user,
        spool.id,
        SpoolUpdateRequest(state=UserSpoolState.shelf.value),
    )

    gate_spool_id = await db_session.scalar(
        select(PresetGateState.spool_id).where(PresetGateState.id == gate_state.id)
    )
    assert result.state == UserSpoolState.shelf.value
    assert gate_spool_id is None
    assert result.extra == {"printer_name": '""', "mmu_gate_map": "-1"}


@pytest.mark.asyncio
async def test_finished_spool_moves_to_archive_group_and_clears_gate(
    db_session: AsyncSession,
):
    user, spool, _ = await _seed_spool_for_patch_test(db_session)
    device = UserPrinterDevice(
        user_id=user.id,
        name="Usage Device",
        device_fingerprint="usage-device",
        supports_hh=True,
        gate_count=1,
    )
    db_session.add(device)
    await db_session.flush()
    gate_state = PresetGateState(
        user_id=user.id,
        device_id=device.id,
        gate_index=0,
        spool_id=spool.id,
        source=PresetGateStateSource.web_manual,
        source_ts=datetime.now(timezone.utc),
        is_active=True,
    )
    db_session.add(gate_state)
    await db_session.commit()

    result = await use_spool(db_session, user, spool.id, spool.remaining_weight_g)

    gate_spool_id = await db_session.scalar(
        select(PresetGateState.spool_id).where(PresetGateState.id == gate_state.id)
    )
    assert result.state == UserSpoolState.empty.value
    assert result.remaining_weight_g == 0
    assert result.last_used_at is not None
    assert gate_spool_id is None
