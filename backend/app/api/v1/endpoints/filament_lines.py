"""Filament line endpoints (группировка вариантов-цвета бренда)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_BRAND_NOT_FOUND,
    ERR_FILAMENT_LINE_NOT_FOUND,
    ERR_NO_PERMISSION_EDIT_FILAMENT,
    raise_error,
)
from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_line import FilamentLine
from app.models.user import User, UserRole
from app.schemas.filament import (
    FilamentLineCreate,
    FilamentLineResponse,
    FilamentLineUpdate,
)

router = APIRouter(prefix="/filament-lines", tags=["filament-lines"])


def _can_manage(user: User, brand_id: int) -> bool:
    return user.role == UserRole.ADMIN or user.brand_id == brand_id


async def _to_response(db: AsyncSession, line: FilamentLine) -> FilamentLineResponse:
    count = await db.scalar(
        select(func.count()).select_from(Filament).where(Filament.line_id == line.id)
    )
    return FilamentLineResponse(
        id=line.id,
        brand_id=line.brand_id,
        name=line.name,
        filaments_count=count or 0,
        created_at=line.created_at,
    )


@router.get("", response_model=list[FilamentLineResponse])
async def list_filament_lines(
    db: Annotated[AsyncSession, Depends(get_db)],
    brand_id: int = Query(..., gt=0),
) -> list[FilamentLineResponse]:
    """Линейки бренда (публично, для группировки в каталоге)."""
    result = await db.execute(
        select(FilamentLine).where(FilamentLine.brand_id == brand_id).order_by(FilamentLine.name)
    )
    lines = result.scalars().all()
    return [await _to_response(db, line) for line in lines]


@router.post("", response_model=FilamentLineResponse, status_code=201)
async def create_filament_line(
    data: FilamentLineCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    brand_id: int = Query(..., gt=0),
) -> FilamentLineResponse:
    """Создать линейку бренда."""
    brand = await db.scalar(select(Brand).where(Brand.id == brand_id))
    if brand is None:
        raise_error(404, ERR_BRAND_NOT_FOUND)
    if not _can_manage(current_user, brand_id):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)

    line = FilamentLine(brand_id=brand_id, name=data.name.strip())
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return await _to_response(db, line)


@router.patch("/{line_id}", response_model=FilamentLineResponse)
async def update_filament_line(
    line_id: int,
    data: FilamentLineUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> FilamentLineResponse:
    """Переименовать линейку."""
    line = await db.scalar(select(FilamentLine).where(FilamentLine.id == line_id))
    if line is None:
        raise_error(404, ERR_FILAMENT_LINE_NOT_FOUND)
    if not _can_manage(current_user, line.brand_id):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)

    line.name = data.name.strip()
    await db.commit()
    await db.refresh(line)
    return await _to_response(db, line)


@router.delete("/{line_id}", status_code=204)
async def delete_filament_line(
    line_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Удалить линейку (филаменты остаются, line_id у них становится NULL)."""
    line = await db.scalar(select(FilamentLine).where(FilamentLine.id == line_id))
    if line is None:
        raise_error(404, ERR_FILAMENT_LINE_NOT_FOUND)
    if not _can_manage(current_user, line.brand_id):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)

    await db.delete(line)
    await db.commit()
