"""Страновые ячейки: один товар, разные рынки."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament


async def _brand_with_filament(db: AsyncSession) -> tuple[Brand, Filament]:
    brand = Brand(name="Creality Cells", slug="creality-cells", active=True)
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id, name="Hyper PLA", slug="hyper-pla-cells", material_type="PLA"
    )
    db.add(filament)
    await db.commit()
    await db.refresh(brand)
    await db.refresh(filament)
    return brand, filament


@pytest.mark.asyncio
async def test_one_country_one_cell(admin_client: AsyncClient, db_session: AsyncSession):
    """Пара «бренд + страна» уникальна, иначе у страны появятся две витрины."""
    brand, _ = await _brand_with_filament(db_session)

    first = await admin_client.post(
        f"/api/v1/brands/{brand.id}/country-cells",
        json={"country": "RU", "website": "https://creality.ru", "published": True},
    )
    assert first.status_code == 201

    second = await admin_client.post(
        f"/api/v1/brands/{brand.id}/country-cells", json={"country": "RU"}
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "ERR_COUNTRY_CELL_EXISTS"


@pytest.mark.asyncio
async def test_country_code_is_normalised_on_write(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """ru и RU — одна страна, иначе ячеек станет две."""
    brand, _ = await _brand_with_filament(db_session)

    created = await admin_client.post(
        f"/api/v1/brands/{brand.id}/country-cells", json={"country": "de"}
    )
    assert created.status_code == 201
    assert created.json()["country"] == "DE"

    duplicate = await admin_client.post(
        f"/api/v1/brands/{brand.id}/country-cells", json={"country": "DE"}
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_an_unpublished_cell_stays_out_of_the_shop_window(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Наполовину заполненная ячейка не уезжает в витрину при сохранении."""
    brand, _ = await _brand_with_filament(db_session)
    await admin_client.post(
        f"/api/v1/brands/{brand.id}/country-cells",
        json={"country": "RS", "website": "https://example.rs"},
    )

    # Фикстуры admin_client и client — один объект: гостя изображаем, снимая
    # заголовок у самого запроса.
    anonymous = {"Authorization": ""}

    public = await admin_client.get(
        f"/api/v1/brands/{brand.id}/country-cells", headers=anonymous
    )
    assert public.status_code == 200
    assert public.json() == []

    for_admin = await admin_client.get(f"/api/v1/brands/{brand.id}/country-cells")
    assert [cell["country"] for cell in for_admin.json()] == ["RS"]

    await admin_client.patch(
        f"/api/v1/brands/{brand.id}/country-cells/rs", json={"published": True}
    )
    published = await admin_client.get(
        f"/api/v1/brands/{brand.id}/country-cells", headers=anonymous
    )
    assert [cell["country"] for cell in published.json()] == ["RS"]


@pytest.mark.asyncio
async def test_price_and_currency_are_written_together(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Цена без валюты унаследовала бы чужую: сербская цена в рублях."""
    _, filament = await _brand_with_filament(db_session)

    lonely_price = await admin_client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        json={"country": "RS", "price": 2500},
    )
    assert lonely_price.status_code == 422

    both = await admin_client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        json={"country": "RS", "price": 2500, "currency": "RSD"},
    )
    assert both.status_code == 201

    # Частичное обновление тоже не должно разлучать их.
    broken = await admin_client.patch(
        f"/api/v1/filaments/{filament.id}/country-cells/RS", json={"currency": None}
    )
    assert broken.status_code == 422


@pytest.mark.asyncio
async def test_the_price_remembers_who_set_it(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Цену правят несколько организаций — нужно видеть, кто и когда."""
    _, filament = await _brand_with_filament(db_session)

    created = await admin_client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        json={"country": "RU", "price": 1800, "currency": "RUB", "price_display_unit": "per_kg"},
    )
    assert created.status_code == 201
    assert created.json()["price_updated_at"] is not None

    # Правка, не касающаяся цены, след не переписывает.
    stamped = created.json()["price_updated_at"]
    other = await admin_client.patch(
        f"/api/v1/filaments/{filament.id}/country-cells/RU",
        json={"product_url": "https://shop.example/hyper-pla"},
    )
    assert other.json()["price_updated_at"] == stamped


@pytest.mark.asyncio
async def test_availability_says_unknown_rather_than_guessing(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Ячейка могла появиться ради цены и ничего не утверждать о наличии."""
    _, filament = await _brand_with_filament(db_session)

    created = await admin_client.post(
        f"/api/v1/filaments/{filament.id}/country-cells", json={"country": "DE"}
    )
    assert created.status_code == 201
    assert created.json()["availability"] == "unknown"

    stated = await admin_client.patch(
        f"/api/v1/filaments/{filament.id}/country-cells/DE",
        json={"availability": "unavailable"},
    )
    assert stated.json()["availability"] == "unavailable"


@pytest.mark.asyncio
async def test_cells_leave_with_what_they_describe(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Удаление товара уносит его ячейки: осиротевшая цена никому не нужна."""
    from sqlalchemy import func, select

    from app.models.filament_country_cell import FilamentCountryCell

    _, filament = await _brand_with_filament(db_session)
    await admin_client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        json={"country": "RU", "price": 1800, "currency": "RUB"},
    )

    removed = await admin_client.delete(f"/api/v1/filaments/{filament.id}")
    assert removed.status_code == 204

    left = await db_session.scalar(
        select(func.count()).select_from(FilamentCountryCell)
        .where(FilamentCountryCell.filament_id == filament.id)
    )
    assert left == 0
