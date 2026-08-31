"""Exact, owner-scoped filtering for the shared spool inventory endpoint."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState


@pytest.mark.asyncio
async def test_spool_list_filters_exact_variant_without_leaking_another_owner(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    brand = Brand(name="Inventory Filter Brand", slug="inventory-filter-brand", active=True)
    exact = Filament(
        brand=brand,
        name="Exact PLA",
        slug="exact-pla",
        qr_code="FH-INVENTORY-EXACT",
        material_type="PLA",
        active=True,
    )
    other = Filament(
        brand=brand,
        name="Exact PLA",
        slug="exact-pla-other-variant",
        material_type="PLA",
        active=True,
    )
    foreign_user = User(
        email="inventory-filter-foreign@example.com",
        username="inventory_filter_foreign",
        password_hash="not-used",
        active=True,
    )
    db_session.add_all([brand, exact, other, foreign_user])
    await db_session.flush()

    own_exact = [
        UserSpool(
            user_id=auth_user.id,
            filament_id=exact.id,
            initial_weight_g=1000,
            used_weight_g=100,
            state=UserSpoolState.shelf,
            source="manual",
        ),
        UserSpool(
            user_id=auth_user.id,
            filament_id=exact.id,
            initial_weight_g=1000,
            used_weight_g=250,
            state=UserSpoolState.active,
            source="qr",
            extra={
                "printer_name": json.dumps("Printer A"),
                "mmu_gate_map": json.dumps(1),
            },
        ),
        UserSpool(
            user_id=auth_user.id,
            filament_id=exact.id,
            initial_weight_g=1000,
            used_weight_g=400,
            state=UserSpoolState.archived,
            source="manual",
        ),
        UserSpool(
            user_id=auth_user.id,
            filament_id=exact.id,
            initial_weight_g=1000,
            used_weight_g=1000,
            state=UserSpoolState.empty,
            source="manual",
        ),
    ]
    other_variant = UserSpool(
        user_id=auth_user.id,
        filament_id=other.id,
        initial_weight_g=1000,
        state=UserSpoolState.shelf,
        source="manual",
    )
    foreign_exact = UserSpool(
        user_id=foreign_user.id,
        filament_id=exact.id,
        initial_weight_g=1000,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add_all([*own_exact, other_variant, foreign_exact])
    await db_session.commit()

    filtered = await auth_client.get(
        "/api/v1/spools",
        params={"filament_id": exact.id},
    )
    assert filtered.status_code == 200
    filtered_data = filtered.json()
    assert {item["id"] for item in filtered_data} == {spool.id for spool in own_exact}
    assert {item["filament_id"] for item in filtered_data} == {exact.id}
    assert {item["filament"]["qr_code"] for item in filtered_data} == {"FH-INVENTORY-EXACT"}
    assert {item["state"] for item in filtered_data} == {
        "active",
        "shelf",
        "archived",
        "empty",
    }
    active = next(item for item in filtered_data if item["state"] == "active")
    assert json.loads(active["extra"]["printer_name"]) == "Printer A"
    assert json.loads(active["extra"]["mmu_gate_map"]) == 1

    unfiltered = await auth_client.get("/api/v1/spools")
    assert unfiltered.status_code == 200
    assert {item["id"] for item in unfiltered.json()} == {
        *(spool.id for spool in own_exact),
        other_variant.id,
    }
    assert (
        next(item for item in unfiltered.json() if item["id"] == other_variant.id)["filament"][
            "qr_code"
        ]
        is None
    )

    invalid = await auth_client.get("/api/v1/spools", params={"filament_id": 0})
    assert invalid.status_code == 422

    row_count = await db_session.scalar(select(func.count()).select_from(UserSpool))
    assert row_count == 6
