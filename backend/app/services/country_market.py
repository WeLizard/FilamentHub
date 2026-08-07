"""Подстановка страновых сведений в выдачу каталога.

Правило одно: пусто значит «как у всех». Есть значение в ячейке — берём его,
нет — берём общее. Глобальный товар с одной ценой ничего не заполняет и везде
выглядит одинаково.

Отсутствие ячейки означает «мы не знаем», а не «здесь не продаётся», поэтому
ничего про местное наличие в таком случае не говорится вовсе.

Страна приходит параметром запроса, и это не косметика: общий кеш каталога
ключуется по адресу вместе со строкой запроса. Начнём выводить страну на
сервере — из профиля или по адресу подключения, — не отразив её в адресе, и
первый же прогретый ответ отдаст сербу российские цены.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament_country_cell import FilamentCountryCell

# Поля ячейки, которые подменяют общие. Ключ — что отдаём наружу.
_SUBSTITUTED = (
    ("price_per_kg", "price"),
    ("currency", "currency"),
    ("price_display_unit", "price_display_unit"),
    ("name", "market_display_name"),
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


def apply_cell(payload: dict, cell: FilamentCountryCell | None) -> dict:
    """Подставить местные сведения в готовый ответ по товару."""
    if cell is None:
        return payload

    for public_field, cell_field in _SUBSTITUTED:
        value = getattr(cell, cell_field, None)
        if isinstance(value, str) and not value.strip():
            value = None
        if value is not None:
            payload[public_field] = value.value if hasattr(value, "value") else value

    # Наличие в стране и состояние товара у производителя — разные вещи:
    # «снят с производства» и «здесь не продаётся» не заменяют друг друга.
    payload["market_availability"] = cell.availability.value

    if cell.product_url:
        payload["product_url"] = cell.product_url
    if cell.purchase_links:
        payload["purchase_links"] = cell.purchase_links
    if cell.market_note:
        payload["market_note"] = cell.market_note

    # Чтобы витрина могла честно подписать: это рекомендованная цена для страны,
    # а не наша общая.
    payload["market_country"] = cell.country
    return payload
