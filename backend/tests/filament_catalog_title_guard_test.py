"""Prevent imported physical-spool names from being published as catalog products."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament

IMPORTED_PIPSPOOL_TITLE = "(#1) PLA MATT LAVENDER PURPLE - Polymaker - PipSpool"


@pytest.mark.asyncio
async def test_create_rejects_imported_spool_title_as_catalog_filament(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="PipSpool Guard Test", slug="pipspool-guard-test", active=True)
    db_session.add(brand)
    await db_session.flush()

    response = await auth_client.post(
        "/api/v1/filaments/",
        json={"brand_id": brand.id, "name": IMPORTED_PIPSPOOL_TITLE, "material_type": "PLA"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_FILAMENT_IMPORT_TITLE_FOR_CATALOG"
    assert await db_session.scalar(
        select(Filament.id).where(Filament.name == IMPORTED_PIPSPOOL_TITLE)
    ) is None


@pytest.mark.asyncio
async def test_update_rejects_imported_spool_title_without_changing_catalog_name(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="PipSpool Update Guard Test", slug="pipspool-update-guard-test", active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="PLA Matte Lavender Purple",
        slug="pla-matte-lavender-purple",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()

    response = await admin_client.patch(
        f"/api/v1/filaments/{filament.id}",
        json={"name": IMPORTED_PIPSPOOL_TITLE},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_FILAMENT_IMPORT_TITLE_FOR_CATALOG"
    await db_session.refresh(filament)
    assert filament.name == "PLA Matte Lavender Purple"


@pytest.mark.asyncio
async def test_catalog_product_name_without_import_wrapper_is_allowed(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="Catalog Name Guard Test", slug="catalog-name-guard-test", active=True)
    db_session.add(brand)
    await db_session.flush()

    response = await auth_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "PLA MATT LAVENDER PURPLE - Polymaker",
            "material_type": "PLA",
            "color_name": "Lavender Purple",
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "PLA MATT LAVENDER PURPLE - Polymaker"
