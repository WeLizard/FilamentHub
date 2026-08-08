"""Страновые ячейки бренда и филамента.

Одна глобальная запись по-прежнему описывает один физический товар: страна копию
не создаёт. Здесь живёт только то, что действительно различается по рынкам.

Править ячейку может тот, у кого есть право на эту страну: представитель своей
области или администратор. Чужую страну не трогает никто, общий слой отсюда не
меняется вовсе.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_current_active_user_optional
from app.core.errors import (
    ERR_ACCESS_DENIED,
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
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.country_cell import (
    BrandCountryCellCreate,
    BrandCountryCellResponse,
    BrandCountryCellUpdate,
    FilamentCountryCellCreate,
    FilamentCountryCellResponse,
    FilamentCountryCellUpdate,
)
from app.services.territorial_access import (
    active_grants_for,
    brand_drafts_visible_to,
    can_edit_brand_common,
    can_edit_filament_common,
    can_manage_brand_country,
    can_manage_filament_country,
    filament_drafts_visible_to,
)
from app.services.country_market import filament_cell_has_public_data

router = APIRouter(tags=["country-cells"])


def _published_or_own(model: type, own: set[str]):
    """Показать опубликованное всем, а неопубликованное — только своей области."""
    visible = model.published.is_(True)
    if own:
        visible = or_(visible, model.country.in_(sorted(own)))
    return visible


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
    """Ячейки бренда. Чужие черновики скрыты, свой виден."""
    await _require_brand(db, brand_id)

    query = select(BrandCountryCell).where(BrandCountryCell.brand_id == brand_id)
    if country:
        query = query.where(BrandCountryCell.country == country.upper())

    everywhere, own = await brand_drafts_visible_to(db, viewer, brand_id)
    if not everywhere:
        query = query.where(_published_or_own(BrandCountryCell, own))

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
    actor: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandCountryCellResponse:
    """Завести ячейку бренда в стране."""
    await _require_brand(db, brand_id)
    if not await can_manage_brand_country(db, actor, brand_id, data.country):
        raise_error(403, ERR_ACCESS_DENIED)

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
    actor: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandCountryCellResponse:
    """Изменить ячейку бренда."""
    if not await can_manage_brand_country(db, actor, brand_id, country):
        raise_error(403, ERR_ACCESS_DENIED)

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
    actor: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Убрать ячейку. Бренд и его общие данные не затрагиваются."""
    if not await can_manage_brand_country(db, actor, brand_id, country):
        raise_error(403, ERR_ACCESS_DENIED)

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
    """Ячейки филамента. Чужие черновики скрыты, свой виден."""
    filament = await _require_filament(db, filament_id)

    query = select(FilamentCountryCell).where(FilamentCountryCell.filament_id == filament_id)
    if country:
        query = query.where(FilamentCountryCell.country == country.upper())

    everywhere, own = await filament_drafts_visible_to(db, viewer, filament.brand_id)
    if not everywhere:
        query = query.where(_published_or_own(FilamentCountryCell, own))

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
    actor: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentCountryCellResponse:
    """Завести ячейку филамента в стране."""
    filament = await _require_filament(db, filament_id)
    if not await can_manage_filament_country(db, actor, filament.brand_id, data.country):
        raise_error(403, ERR_ACCESS_DENIED)

    existing = await db.scalar(
        select(FilamentCountryCell).where(
            FilamentCountryCell.filament_id == filament_id,
            FilamentCountryCell.country == data.country,
        )
    )
    if existing is not None:
        raise_error(409, ERR_COUNTRY_CELL_EXISTS)

    cell = FilamentCountryCell(filament_id=filament_id, **data.model_dump())
    cell.published = filament_cell_has_public_data(cell)
    if cell.price is not None:
        cell.price_updated_at = datetime.now(timezone.utc)
        cell.price_updated_by_id = actor.id

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
    actor: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentCountryCellResponse:
    """Изменить ячейку филамента."""
    filament = await _require_filament(db, filament_id)
    if not await can_manage_filament_country(db, actor, filament.brand_id, country):
        raise_error(403, ERR_ACCESS_DENIED)

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

    cell.published = filament_cell_has_public_data(cell)

    # Цена и валюта проверяются после применения: частичное обновление могло
    # снять одну и оставить другую.
    if (cell.price is None) != (cell.currency is None):
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", "price"], "msg": "price and currency must be set together"}],
        )

    if "price" in changes:
        cell.price_updated_at = datetime.now(timezone.utc)
        cell.price_updated_by_id = actor.id

    await db.commit()
    await db.refresh(cell)
    return FilamentCountryCellResponse.model_validate(cell)


@router.delete("/filaments/{filament_id}/country-cells/{country}", status_code=204)
async def delete_filament_country_cell(
    filament_id: int,
    country: str,
    actor: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Убрать ячейку. Сам товар и его общие данные не затрагиваются."""
    filament = await _require_filament(db, filament_id)
    if not await can_manage_filament_country(db, actor, filament.brand_id, country):
        raise_error(403, ERR_ACCESS_DENIED)

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


@router.get("/brands/{brand_id}/my-territories")
async def my_territories(
    brand_id: int,
    actor: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Что человек ведёт в этом бренде и кто ведёт общий слой.

    Интерфейс обязан объяснить границу словами, а не заблокированными полями:
    представитель должен видеть «общее для всех стран» отдельно от «вашей
    области», и знать, к кому идти с общим.
    """
    brand = await _require_brand(db, brand_id)
    grants = await active_grants_for(db, actor, brand_id)

    common_owner: str | None = None
    if brand.organization_id is not None:
        common_owner = await db.scalar(
            select(Organization.name).where(Organization.id == brand.organization_id)
        )

    return {
        "brand_id": brand_id,
        "is_admin": actor.role == UserRole.ADMIN,
        "common_managed_by": common_owner,
        "can_edit_common": await can_edit_brand_common(db, actor, brand_id),
        "can_edit_filament_common": await can_edit_filament_common(db, actor, brand_id),
        "territories": [
            {
                "country": grant.country,
                "manage_brand_country": grant.manage_brand_country,
                "manage_filament_country": grant.manage_filament_country,
                "create_filaments": grant.create_filaments,
            }
            for grant in grants
        ],
    }
