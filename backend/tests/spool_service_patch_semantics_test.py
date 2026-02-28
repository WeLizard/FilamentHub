"""Tests for spool service PATCH nullable semantics via model_fields_set."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.spool import SpoolUpdateRequest
from app.services.spool_service import update_spool


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
