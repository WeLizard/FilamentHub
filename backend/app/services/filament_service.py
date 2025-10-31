"""Filament service layer."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament import Filament
from app.models.brand import Brand


async def get_filament_by_id(filament_id: int, db: AsyncSession) -> Filament | None:
    """Получить материал по ID."""
    result = await db.execute(
        select(Filament).where(Filament.id == filament_id)
    )
    return result.scalar_one_or_none()


async def list_filaments(
    db: AsyncSession,
    active_only: bool = True,
    brand_id: int | None = None,
    material_type: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Filament]:
    """Получить список материалов."""
    query = select(Filament)
    
    if active_only:
        query = query.where(Filament.active == True)
    
    if brand_id:
        query = query.where(Filament.brand_id == brand_id)
    
    if material_type:
        query = query.where(Filament.material_type == material_type)
    
    if search:
        query = query.where(
            Filament.name.ilike(f"%{search}%")
            | Filament.color_name.ilike(f"%{search}%")
        )
    
    query = query.order_by(Filament.name.asc())
    
    if limit:
        query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    return list(result.scalars().all())


async def check_brand_exists(brand_id: int, db: AsyncSession) -> bool:
    """Проверить существование бренда."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    return brand is not None

