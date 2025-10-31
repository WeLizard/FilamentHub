"""Brand service layer."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand


async def get_brand_by_id(brand_id: int, db: AsyncSession) -> Brand | None:
    """Получить бренд по ID."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    return result.scalar_one_or_none()


async def get_brand_by_slug(slug: str, db: AsyncSession) -> Brand | None:
    """Получить бренд по slug."""
    result = await db.execute(select(Brand).where(Brand.slug == slug))
    return result.scalar_one_or_none()


async def get_brand_by_name(name: str, db: AsyncSession) -> Brand | None:
    """Получить бренд по имени."""
    result = await db.execute(select(Brand).where(Brand.name == name))
    return result.scalar_one_or_none()


async def list_brands(
    db: AsyncSession,
    active_only: bool = True,
    verified_only: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> list[Brand]:
    """Получить список брендов."""
    query = select(Brand)
    
    if active_only:
        query = query.where(Brand.active == True)
    
    if verified_only:
        query = query.where(Brand.verified == True)
    
    query = query.order_by(Brand.name.asc())
    
    if limit:
        query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    return list(result.scalars().all())

