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


@pytest.mark.asyncio
async def test_the_reader_country_substitutes_local_facts(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Есть значение в ячейке — берём его, нет — берём общее."""
    _, filament = await _brand_with_filament(db_session)
    filament.price_per_kg = 1500
    filament.currency = "RUB"
    await db_session.commit()

    await admin_client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        json={
            "country": "RS",
            "price": 2500,
            "currency": "RSD",
            "price_display_unit": "per_spool",
            "availability": "available",
            "product_url": "https://shop.rs/hyper-pla",
            "published": True,
        },
    )

    serbian = await admin_client.get(f"/api/v1/filaments/{filament.id}?country=RS")
    assert serbian.status_code == 200
    local = serbian.json()
    assert local["price_per_kg"] == 2500
    assert local["currency"] == "RSD"
    assert local["price_display_unit"] == "per_spool"
    assert local["market_availability"] == "available"
    assert local["product_url"] == "https://shop.rs/hyper-pla"
    # Витрина обязана суметь подписать цену как местную.
    assert local["market_country"] == "RS"

    # Страна без ячейки видит общее и молчит о местном наличии.
    german = await admin_client.get(f"/api/v1/filaments/{filament.id}?country=DE")
    assert german.json()["price_per_kg"] == 1500
    assert german.json()["currency"] == "RUB"
    assert german.json()["market_country"] is None

    # Без страны — тоже общее.
    plain = await admin_client.get(f"/api/v1/filaments/{filament.id}")
    assert plain.json()["price_per_kg"] == 1500


@pytest.mark.asyncio
async def test_an_unpublished_cell_never_reaches_the_catalogue(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Черновик ячейки не подставляется даже администратору в витрине."""
    _, filament = await _brand_with_filament(db_session)
    filament.price_per_kg = 1500
    filament.currency = "RUB"
    await db_session.commit()

    await admin_client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        json={"country": "RS", "price": 2500, "currency": "RSD"},
    )

    listed = await admin_client.get("/api/v1/filaments/?country=RS&size=100")
    item = next(i for i in listed.json()["items"] if i["id"] == filament.id)
    assert item["price_per_kg"] == 1500
    assert item["market_country"] is None


@pytest.mark.asyncio
async def test_not_sold_here_is_not_discontinued(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Состояние товара у производителя и продажа в стране — разные словари."""
    _, filament = await _brand_with_filament(db_session)
    await db_session.commit()

    for country, market_state in (("RS", "unavailable"), ("FR", "unknown")):
        created = await admin_client.post(
            f"/api/v1/filaments/{filament.id}/country-cells",
            json={"country": country, "availability": market_state, "published": True},
        )
        assert created.status_code == 201

        shown = await admin_client.get(f"/api/v1/filaments/{filament.id}?country={country}")
        assert shown.status_code == 200
        # Товар выпускается, просто на этом рынке его не продают.
        assert shown.json()["availability"] == "available"
        assert shown.json()["market_availability"] == market_state


@pytest.mark.asyncio
async def test_not_sold_here_hides_the_local_price(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Цена товара, который здесь не купить, читателю только противоречит."""
    _, filament = await _brand_with_filament(db_session)
    await db_session.commit()

    created = await admin_client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        json={
            "country": "RS",
            "availability": "unavailable",
            "price": 3000,
            "currency": "RSD",
            "product_url": "https://example.rs/pla",
            "published": True,
        },
    )
    assert created.status_code == 201

    shown = (await admin_client.get(f"/api/v1/filaments/{filament.id}?country=RS")).json()
    assert shown["market_availability"] == "unavailable"
    assert shown["price_per_kg"] != 3000
    assert shown["currency"] != "RSD"
    assert shown["product_url"] != "https://example.rs/pla"

    # Сама ячейка цену помнит: скрыт показ, а не введённые представителем данные.
    cell = (await admin_client.get(f"/api/v1/filaments/{filament.id}/country-cells")).json()[0]
    assert cell["price"] == 3000
