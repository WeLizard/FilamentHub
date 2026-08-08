"""Подстановка страновых сведений в выдачу каталога.

Общие сведения о товаре могут наследоваться, но цена не переносится между
рынками. Если для страны нет местной цены, результат остаётся неизвестным и
пустым, а не получает цену и валюту другого рынка.

Отсутствие ячейки означает «мы не знаем», а не «здесь не продаётся», поэтому
ничего про местное наличие в таком случае не говорится вовсе.

Страна приходит параметром запроса, и это не косметика: общий кеш каталога
ключуется по адресу вместе со строкой запроса. Начнём выводить страну на
сервере — из профиля или по адресу подключения, — не отразив её в адресе, и
первый же прогретый ответ отдаст сербу российские цены.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_country_cell import BrandCountryCell
from app.models.filament_country_cell import CountryAvailability, FilamentCountryCell

# Поля ячейки, которые подменяют общие. Ключ — что отдаём наружу.
_SUBSTITUTED = (
    ("price_per_kg", "price"),
    ("currency", "currency"),
    ("price_display_unit", "price_display_unit"),
    ("color_name", "market_color_name"),
)


def filament_cell_has_public_data(cell: FilamentCountryCell) -> bool:
    """Whether a market cell contains anything useful for the public catalog.

    Publication is derived from the data itself. A representative does not
    manually publish or hide a country version, and the retired availability
    flag is not enough to create one on its own.
    """
    if cell.price is not None or cell.availability != CountryAvailability.unknown:
        return True
    return any(
        isinstance(value, str) and bool(value.strip())
        for value in (cell.product_url, cell.market_note, cell.market_color_name)
    )

async def cells_for(
    db: AsyncSession, filament_ids: list[int], country: str | None
) -> dict[int, FilamentCountryCell]:
    """Опубликованные ячейки одной выборкой, а не запросом на каждую карточку."""
    if not country or not filament_ids:
        return {}

    cells = await db.scalars(
        select(FilamentCountryCell).where(
            FilamentCountryCell.filament_id.in_(filament_ids),
            FilamentCountryCell.country == country.upper(),
            FilamentCountryCell.published.is_(True),
        )
    )
    return {cell.filament_id: cell for cell in cells}


def apply_cell(
    payload: dict,
    cell: FilamentCountryCell | None,
    country: str | None = None,
) -> dict:
    """Подставить местные сведения в готовый ответ по товару."""
    # Запрошенный рынок никогда не наследует legacy-цену общего слоя. Это
    # относится и к существующей ячейке, в которой цена пока не известна.
    if country:
        payload["price_per_kg"] = None
        payload["currency"] = None

    if cell is None:
        return payload

    has_market_data = False
    for public_field, cell_field in _SUBSTITUTED:
        value = getattr(cell, cell_field, None)
        if isinstance(value, str) and not value.strip():
            value = None
        if value is not None:
            payload[public_field] = value.value if hasattr(value, "value") else value
            has_market_data = True

    if cell.product_url:
        payload["product_url"] = cell.product_url
        has_market_data = True
    if cell.market_note:
        payload["market_note"] = cell.market_note
        has_market_data = True
    if cell.availability != CountryAvailability.unknown:
        payload["market_availability"] = (
            CountryAvailability.discontinued.value
            if cell.availability == CountryAvailability.unavailable
            else cell.availability.value
        )
        has_market_data = True

    # Чтобы витрина могла честно подписать: это рекомендованная цена для страны,
    # а не наша общая.
    if has_market_data:
        payload["market_country"] = cell.country
    return payload


async def brand_cell_for(
    db: AsyncSession, brand_id: int, country: str | None
) -> BrandCountryCell | None:
    """Опубликованная витрина бренда в стране читателя."""
    if not country:
        return None
    return await db.scalar(
        select(BrandCountryCell).where(
            BrandCountryCell.brand_id == brand_id,
            BrandCountryCell.country == country.upper(),
            BrandCountryCell.published.is_(True),
        )
    )


def apply_brand_cell(payload: dict, cell: BrandCountryCell | None) -> dict:
    """Подставить местные сайт и магазины бренда. Пусто — остаётся общее."""
    if cell is None:
        return payload

    if cell.website and cell.website.strip():
        payload["website"] = cell.website
    if cell.shop_links:
        payload["shop_links"] = cell.shop_links
    if cell.description and cell.description.strip():
        payload["description"] = cell.description
    if cell.social_media_urls:
        payload["social_media_urls"] = cell.social_media_urls
    payload["market_country"] = cell.country
    return payload
