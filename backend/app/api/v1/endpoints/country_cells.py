"""Страновые ячейки бренда и филамента.

Одна глобальная запись по-прежнему описывает один физический товар: страна копию
не создаёт. Здесь живёт только то, что действительно различается по рынкам.

Заполняет администратор. Территориальные права представителей — отдельная
задача, и до неё правка ячеек не выдаётся никому другому.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user_optional, get_current_admin_user
from app.core.errors import (
    ERR_BRAND_NOT_FOUND,
    ERR_COUNTRY_CELL_EXISTS,
    ERR_COUNTRY_CELL_NOT_FOUND,
    ERR_FILAMENT_NOT_FOUND,
    raise_error,
)
from app.db.session import get_db
from app.models.brand import Brand
from app.models.brand_country_cell import BrandCountryCell
from app.models.filament import Filament
from app.models.filament_country_cell import FilamentCountryCell
from app.models.user import User
from app.schemas.country_cell import (
    BrandCountryCellCreate,
    BrandCountryCellResponse,
    BrandCountryCellUpdate,
    FilamentCountryCellCreate,
    FilamentCountryCellResponse,
    FilamentCountryCellUpdate,
)

router = APIRouter(tags=["country-cells"])


async def _require_brand(db: AsyncSession, brand_id: int) -> Brand:
    brand = await db.get(Brand, brand_id)
    if brand is None:
        raise_error(404, ERR_BRAND_NOT_FOUND)
    return brand


async def _require_filament(db: AsyncSession, filament_id: int) -> Filament:
    filament = await db.get(Filament, filament_id)
    if filament is None:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)
    return filament


@router.get("/brands/{brand_id}/country-cells", response_model=list[BrandCountryCellResponse])
async def list_brand_country_cells(
    brand_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    viewer: Annotated[User | None, Depends(get_current_active_user_optional)] = None,
    country: str | None = Query(None, pattern=r"^[A-Za-z]{2}$"),
) -> list[BrandCountryCellResponse]:
    """Ячейки бренда. Неопубликованные видит только администратор."""
    await _require_brand(db, brand_id)

    query = select(BrandCountryCell).where(BrandCountryCell.brand_id == brand_id)
    if country:
        query = query.where(BrandCountryCell.country == country.upper())
    if viewer is None or viewer.role.value != "admin":
        query = query.where(BrandCountryCell.published.is_(True))

    cells = (await db.scalars(query.order_by(BrandCountryCell.country))).all()
    return [BrandCountryCellResponse.model_validate(cell) for cell in cells]


@router.post(
    "/brands/{brand_id}/country-cells",
    response_model=BrandCountryCellResponse,
    status_code=201,
)
async def create_brand_country_cell(
    brand_id: int,
    data: BrandCountryCellCreate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandCountryCellResponse:
    """Завести ячейку бренда в стране."""
    del admin
    await _require_brand(db, brand_id)

    existing = await db.scalar(
        select(BrandCountryCell).where(
            BrandCountryCell.brand_id == brand_id,
            BrandCountryCell.country == data.country,
        )
    )
    if existing is not None:
        raise_error(409, ERR_COUNTRY_CELL_EXISTS)

    cell = BrandCountryCell(brand_id=brand_id, **data.model_dump())
    db.add(cell)
    await db.commit()
    await db.refresh(cell)
    return BrandCountryCellResponse.model_validate(cell)


@router.patch(
    "/brands/{brand_id}/country-cells/{country}",
    response_model=BrandCountryCellResponse,
)
async def update_brand_country_cell(
    brand_id: int,
    country: str,
    data: BrandCountryCellUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandCountryCellResponse:
    """Изменить ячейку бренда."""
    del admin
    cell = await db.scalar(
        select(BrandCountryCell).where(
            BrandCountryCell.brand_id == brand_id,
            BrandCountryCell.country == country.upper(),
        )
    )
    if cell is None:
        raise_error(404, ERR_COUNTRY_CELL_NOT_FOUND)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cell, field, value)

    await db.commit()
    await db.refresh(cell)
    return BrandCountryCellResponse.model_validate(cell)


@router.delete("/brands/{brand_id}/country-cells/{country}", status_code=204)
async def delete_brand_country_cell(
    brand_id: int,
    country: str,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Убрать ячейку. Бренд и его общие данные не затрагиваются."""
    del admin
    cell = await db.scalar(
        select(BrandCountryCell).where(
            BrandCountryCell.brand_id == brand_id,
            BrandCountryCell.country == country.upper(),
        )
    )
    if cell is None:
        raise_error(404, ERR_COUNTRY_CELL_NOT_FOUND)

    await db.delete(cell)
    await db.commit()


@router.get(
    "/filaments/{filament_id}/country-cells",
    response_model=list[FilamentCountryCellResponse],
)
async def list_filament_country_cells(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    viewer: Annotated[User | None, Depends(get_current_active_user_optional)] = None,
    country: str | None = Query(None, pattern=r"^[A-Za-z]{2}$"),
) -> list[FilamentCountryCellResponse]:
    """Ячейки филамента. Неопубликованные видит только администратор."""
    await _require_filament(db, filament_id)

    query = select(FilamentCountryCell).where(FilamentCountryCell.filament_id == filament_id)
    if country:
        query = query.where(FilamentCountryCell.country == country.upper())
    if viewer is None or viewer.role.value != "admin":
        query = query.where(FilamentCountryCell.published.is_(True))

    cells = (await db.scalars(query.order_by(FilamentCountryCell.country))).all()
    return [FilamentCountryCellResponse.model_validate(cell) for cell in cells]


@router.post(
    "/filaments/{filament_id}/country-cells",
    response_model=FilamentCountryCellResponse,
    status_code=201,
)
async def create_filament_country_cell(
    filament_id: int,
    data: FilamentCountryCellCreate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentCountryCellResponse:
    """Завести ячейку филамента в стране."""
    await _require_filament(db, filament_id)

    existing = await db.scalar(
        select(FilamentCountryCell).where(
            FilamentCountryCell.filament_id == filament_id,
            FilamentCountryCell.country == data.country,
        )
    )
    if existing is not None:
        raise_error(409, ERR_COUNTRY_CELL_EXISTS)

    cell = FilamentCountryCell(filament_id=filament_id, **data.model_dump())
    if cell.price is not None:
        cell.price_updated_at = datetime.now(timezone.utc)
        cell.price_updated_by_id = admin.id

    db.add(cell)
    await db.commit()
    await db.refresh(cell)
    return FilamentCountryCellResponse.model_validate(cell)


@router.patch(
    "/filaments/{filament_id}/country-cells/{country}",
    response_model=FilamentCountryCellResponse,
)
async def update_filament_country_cell(
    filament_id: int,
    country: str,
    data: FilamentCountryCellUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentCountryCellResponse:
    """Изменить ячейку филамента."""
    cell = await db.scalar(
        select(FilamentCountryCell).where(
            FilamentCountryCell.filament_id == filament_id,
            FilamentCountryCell.country == country.upper(),
        )
    )
    if cell is None:
        raise_error(404, ERR_COUNTRY_CELL_NOT_FOUND)

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(cell, field, value)

    # Цена и валюта проверяются после применения: частичное обновление могло
    # снять одну и оставить другую.
    if (cell.price is None) != (cell.currency is None):
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", "price"], "msg": "price and currency must be set together"}],
        )

    if "price" in changes:
        cell.price_updated_at = datetime.now(timezone.utc)
        cell.price_updated_by_id = admin.id

    await db.commit()
    await db.refresh(cell)
    return FilamentCountryCellResponse.model_validate(cell)


@router.delete("/filaments/{filament_id}/country-cells/{country}", status_code=204)
async def delete_filament_country_cell(
    filament_id: int,
    country: str,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Убрать ячейку. Сам товар и его общие данные не затрагиваются."""
    del admin
    cell = await db.scalar(
        select(FilamentCountryCell).where(
            FilamentCountryCell.filament_id == filament_id,
            FilamentCountryCell.country == country.upper(),
        )
    )
    if cell is None:
        raise_error(404, ERR_COUNTRY_CELL_NOT_FOUND)

    await db.delete(cell)
    await db.commit()
