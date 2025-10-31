"""Filament endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.filament import Filament
from app.schemas.filament import (
    FilamentCreate,
    FilamentListResponse,
    FilamentResponse,
    FilamentUpdate,
    FilamentWithBrand,
)

router = APIRouter(prefix="/filaments", tags=["filaments"])


@router.get("/", response_model=FilamentListResponse)
async def list_filaments(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    brand_id: int | None = Query(None),
    material_type: str | None = Query(None),
) -> FilamentListResponse:
    """Получить список материалов."""
    # Build query
    query = select(Filament)
    if active_only:
        query = query.where(Filament.active == True)
    if brand_id:
        query = query.where(Filament.brand_id == brand_id)
    if material_type:
        query = query.where(Filament.material_type == material_type)

    # Count total
    count_query = select(func.count()).select_from(Filament)
    if active_only:
        count_query = count_query.where(Filament.active == True)
    if brand_id:
        count_query = count_query.where(Filament.brand_id == brand_id)
    if material_type:
        count_query = count_query.where(Filament.material_type == material_type)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(Filament.name)

    # Execute
    result = await db.execute(query)
    filaments = result.scalars().all()

    pages = (total + size - 1) // size if total > 0 else 0

    return FilamentListResponse(
        items=[FilamentResponse.model_validate(filament) for filament in filaments],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{filament_id}", response_model=FilamentWithBrand)
async def get_filament(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentWithBrand:
    """Получить материал по ID с информацией о бренде."""
    result = await db.execute(
        select(Filament).where(Filament.id == filament_id).options(selectinload(Filament.brand))
    )
    filament = result.scalar_one_or_none()

    if not filament:
        raise HTTPException(status_code=404, detail="Filament not found")

    return FilamentWithBrand.model_validate(filament)


@router.post("/", response_model=FilamentResponse, status_code=201)
async def create_filament(
    data: FilamentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentResponse:
    """Создать материал."""
    # Check if brand exists
    from app.models.brand import Brand

    brand_result = await db.execute(select(Brand).where(Brand.id == data.brand_id))
    if not brand_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Brand not found")

    # Create filament
    filament = Filament(**data.model_dump())
    db.add(filament)
    await db.commit()
    await db.refresh(filament)

    return FilamentResponse.model_validate(filament)


@router.patch("/{filament_id}", response_model=FilamentResponse)
async def update_filament(
    filament_id: int,
    data: FilamentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentResponse:
    """Обновить материал."""
    result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = result.scalar_one_or_none()

    if not filament:
        raise HTTPException(status_code=404, detail="Filament not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(filament, field, value)

    await db.commit()
    await db.refresh(filament)

    return FilamentResponse.model_validate(filament)


@router.delete("/{filament_id}", status_code=204)
async def delete_filament(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Удалить материал."""
    result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = result.scalar_one_or_none()

    if not filament:
        raise HTTPException(status_code=404, detail="Filament not found")

    await db.delete(filament)
    await db.commit()

