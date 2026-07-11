"""Tests for the brand usage analytics endpoint."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.user import User
from app.models.user_spool import UserSpool


@pytest.mark.asyncio
async def test_brand_usage_aggregates_real_data(
    admin_client: AsyncClient, admin_user: User, db_session: AsyncSession
) -> None:
    brand = Brand(name="UsageBrand", slug="usage-brand")
    db_session.add(brand)
    await db_session.flush()

    filament = Filament(
        brand_id=brand.id, name="UB PLA", slug="ub-pla", material_type="PLA"
    )
    db_session.add(filament)
    await db_session.flush()

    printer = Printer(
        name="Ender 3", manufacturer="Creality", model="Ender 3", slug="ub-ender-3"
    )
    db_session.add(printer)
    await db_session.flush()

    preset = Preset(
        filament_id=filament.id,
        name="UB PLA Fast",
        extruder_temp=210,
        bed_temp=60,
        usage_count=5,
    )
    db_session.add(preset)
    await db_session.flush()

    db_session.add(PresetPrinter(preset_id=preset.id, printer_id=printer.id))
    db_session.add(
        UserSpool(user_id=admin_user.id, filament_id=filament.id, initial_weight_g=1000)
    )
    await db_session.commit()

    resp = await admin_client.get(f"/api/v1/brands/{brand.id}/usage")
    assert resp.status_code == 200

    data = resp.json()
    assert data["presets_count"] == 1
    assert data["total_preset_usage"] == 5
    assert data["spools_tracked"] == 1
    assert len(data["popular_printers"]) == 1
    assert data["popular_printers"][0]["name"] == "Ender 3"
    assert data["popular_printers"][0]["count"] == 1


@pytest.mark.asyncio
async def test_brand_usage_empty_brand(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    brand = Brand(name="EmptyBrand", slug="empty-brand")
    db_session.add(brand)
    await db_session.commit()

    resp = await admin_client.get(f"/api/v1/brands/{brand.id}/usage")
    assert resp.status_code == 200

    data = resp.json()
    assert data == {
        "popular_printers": [],
        "spools_tracked": 0,
        "total_preset_usage": 0,
        "presets_count": 0,
    }


@pytest.mark.asyncio
async def test_brand_usage_not_found(admin_client: AsyncClient) -> None:
    resp = await admin_client.get("/api/v1/brands/999999/usage")
    assert resp.status_code == 404
