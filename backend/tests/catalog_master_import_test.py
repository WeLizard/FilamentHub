"""Administrative catalog master-import preview/apply tests."""

from io import BytesIO

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import Brand, CatalogImportBatch, Filament, FilamentCountryCell, Preset
from app.schemas.catalog_import import CatalogImportDraft
from app.services.catalog_master_import_service import (
    apply_plan,
    build_plan,
    build_template,
    parse_workbook,
    summarize,
)

pytestmark = pytest.mark.asyncio


def _headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


def _draft() -> CatalogImportDraft:
    return CatalogImportDraft(
        filename="catalog.xlsx",
        brands=[
            {
                "_row": 2,
                "enabled": True,
                "brand_key": "example",
                "mode": "auto",
                "name": "Example Materials",
                "website": "https://example.test",
            }
        ],
        filaments=[
            {
                "_row": 2,
                "enabled": True,
                "filament_key": "example:pla:black",
                "brand_key": "example",
                "mode": "auto",
                "name": "Everyday PLA Black",
                "line": "Everyday PLA",
                "material_type": "PLA",
                "color_name": "Black",
                "color_hex": "#111111",
                "diameter": 1.75,
                "density": 1.24,
            }
        ],
        filament_markets=[
            {
                "_row": 2,
                "enabled": True,
                "filament_key": "example:pla:black",
                "country": "TR",
                "availability": "available",
                "price": 750,
                "currency": "TRY",
                "price_display_unit": "per_spool",
                "published": True,
            }
        ],
        presets=[
            {
                "_row": 2,
                "enabled": True,
                "preset_key": "example:pla:black:generic",
                "filament_key": "example:pla:black",
                "mode": "auto",
                "name": "Example PLA",
                "extruder_temp": 215,
                "bed_temp": 60,
                "flow_rate": 100,
                "fan_speed": 100,
            }
        ],
    )


async def test_master_import_preview_is_read_only_and_apply_is_idempotent(
    db_session: AsyncSession,
    admin_user,
) -> None:
    draft = _draft()
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(plan) == {
        "create": 4,
        "update": 0,
        "noop": 0,
        "skipped": 0,
        "error": 0,
    }
    assert await db_session.scalar(select(func.count()).select_from(Brand)) == 0

    batch = await apply_plan(
        db_session,
        draft,
        plan,
        admin_user_id=admin_user.id,
    )
    await db_session.commit()
    assert batch.id is not None
    assert await db_session.scalar(select(func.count()).select_from(Brand)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Filament)) == 1
    assert await db_session.scalar(select(func.count()).select_from(FilamentCountryCell)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Preset)) == 1
    assert await db_session.scalar(select(func.count()).select_from(CatalogImportBatch)) == 1

    repeated = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(repeated) == {
        "create": 0,
        "update": 0,
        "noop": 4,
        "skipped": 0,
        "error": 0,
    }


async def test_existing_values_require_explicit_overwrite(
    db_session: AsyncSession,
    admin_user,
) -> None:
    brand = Brand(
        name="Example Materials",
        slug="example-materials",
        website="https://old.example",
        currency="RUB",
        active=True,
        verified=False,
    )
    db_session.add(brand)
    await db_session.commit()

    draft = _draft()
    draft.filaments = []
    draft.filament_markets = []
    draft.presets = []
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(plan)["error"] == 1
    assert "website" in (plan[0].get("message") or "")

    draft.brands[0]["overwrite"] = True
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(plan)["update"] == 1


async def test_template_round_trips_into_editable_draft() -> None:
    workbook = load_workbook(BytesIO(build_template()))
    brands = workbook["Brands"]
    filaments = workbook["Filaments"]
    brand_headers = [cell.value for cell in brands[1]]
    filament_headers = [cell.value for cell in filaments[1]]
    brand_row = {"enabled": True, "brand_key": "sample", "name": "Sample"}
    filament_row = {
        "enabled": True,
        "filament_key": "sample:pla:red",
        "brand_key": "sample",
        "name": "PLA Red",
        "material_type": "PLA",
    }
    brands.append([brand_row.get(header, "") for header in brand_headers])
    filaments.append([filament_row.get(header, "") for header in filament_headers])
    output = BytesIO()
    workbook.save(output)

    parsed = parse_workbook(output.getvalue(), "sample.xlsx")
    assert parsed.brands[0]["brand_key"] == "sample"
    assert parsed.filaments[0]["filament_key"] == "sample:pla:red"


async def test_preview_confirmation_and_apply_work_through_admin_api(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
) -> None:
    draft = _draft()
    preview = await client.post(
        "/api/v1/admin/catalog/master-import/preview-draft",
        headers=_headers(admin_user),
        json=draft.model_dump(mode="json"),
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["summary"]["error"] == 0
    assert body["confirmation_token"]
    assert await db_session.scalar(select(func.count()).select_from(Brand)) == 0

    applied = await client.post(
        "/api/v1/admin/catalog/master-import/apply",
        headers=_headers(admin_user),
        json={
            "draft": body["draft"],
            "confirmation_token": body["confirmation_token"],
        },
    )
    assert applied.status_code == 200
    assert applied.json()["batch_id"] == 1
    assert await db_session.scalar(select(func.count()).select_from(Brand)) == 1

    history = await client.get(
        "/api/v1/admin/catalog/master-import/history",
        headers=_headers(admin_user),
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
