"""Regression tests for stable brand-scoped public filament URLs."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_slug_redirect import FilamentSlugRedirect
from app.services.catalog_url_service import choose_filament_slug


@pytest_asyncio.fixture
async def public_filament(db_session: AsyncSession) -> Filament:
    brand = Brand(name="HexFlow", slug="hexflow", active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="ABS",
        slug="abs-black",
        material_type="ABS",
        color_name="Black",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    return filament


@pytest.mark.asyncio
async def test_filament_detail_resolves_brand_scoped_slug(
    client: AsyncClient,
    public_filament: Filament,
) -> None:
    response = await client.get("/api/v1/filaments/by-slug/hexflow/abs-black")

    assert response.status_code == 200
    assert response.json()["id"] == public_filament.id
    assert response.json()["slug"] == "abs-black"
    assert response.json()["brand_slug"] == "hexflow"


@pytest.mark.asyncio
async def test_catalog_resolver_normalizes_numeric_locale_and_alias_urls(
    client: AsyncClient,
    db_session: AsyncSession,
    public_filament: Filament,
) -> None:
    db_session.add(
        FilamentSlugRedirect(
            filament_id=public_filament.id,
            brand_id=public_filament.brand_id,
            old_slug="abs",
            reason="backfill",
        )
    )
    await db_session.commit()

    canonical = await client.get(
        "/api/v1/catalog-urls/resolve",
        headers={"X-Original-URI": "/ru/brands/hexflow/filaments/abs-black"},
    )
    assert canonical.status_code == 204

    cases = {
        f"/filaments/{public_filament.id}?qr=true": "/brands/hexflow/filaments/abs-black",
        f"/brands/{public_filament.brand_id}": "/brands/hexflow",
        "/brands/hexflow/filaments/abs": "/brands/hexflow/filaments/abs-black",
        "/en/brands/hexflow/filaments/abs-black": "/brands/hexflow/filaments/abs-black",
    }
    for original_uri, expected in cases.items():
        response = await client.get(
            "/api/v1/catalog-urls/resolve",
            headers={"X-Original-URI": original_uri},
        )
        assert response.status_code == 401
        assert response.headers["x-canonical-path"] == expected


@pytest.mark.asyncio
async def test_filament_slug_uses_transliterated_name_not_hex(
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="Local Colours", slug="local-colours", active=True)
    db_session.add(brand)
    await db_session.flush()

    slug = await choose_filament_slug(
        db_session,
        brand_id=brand.id,
        name="ABS",
        color_name="Чёрный",
    )

    assert slug == "abs-chernyi"


@pytest.mark.asyncio
async def test_same_filament_slug_is_allowed_for_different_brands(
    db_session: AsyncSession,
) -> None:
    first = Brand(name="First", slug="first", active=True)
    second = Brand(name="Second", slug="second", active=True)
    db_session.add_all([first, second])
    await db_session.flush()
    db_session.add_all(
        [
            Filament(
                brand_id=first.id,
                name="ABS",
                slug="abs-black",
                material_type="ABS",
                active=True,
            ),
            Filament(
                brand_id=second.id,
                name="ABS",
                slug="abs-black",
                material_type="ABS",
                active=True,
            ),
        ]
    )

    await db_session.commit()


@pytest.mark.asyncio
async def test_sitemap_contains_only_canonical_localized_catalog_urls(
    client: AsyncClient,
    db_session: AsyncSession,
    public_filament: Filament,
) -> None:
    empty_brand = Brand(name="Empty Brand", slug="empty-brand", active=True)
    db_session.add(empty_brand)
    await db_session.commit()

    response = await client.get("/sitemap.xml")

    assert response.status_code == 200
    assert "https://filamenthub.ru/brands/hexflow/filaments/abs-black" in response.text
    assert "https://filamenthub.ru/ru/brands/hexflow/filaments/abs-black" in response.text
    assert "https://filamenthub.ru/zh/brands/hexflow/filaments/abs-black" in response.text
    assert "https://filamenthub.ru/features" in response.text
    assert "https://filamenthub.ru/ru/features" in response.text
    assert "https://filamenthub.ru/zh/features" in response.text
    assert f"https://filamenthub.ru/filaments/{public_filament.id}" not in response.text
    assert f"https://filamenthub.ru/brands/{public_filament.brand_id}" not in response.text
    assert "https://filamenthub.ru/en/" not in response.text
    assert "https://filamenthub.ru/brands/empty-brand" not in response.text
