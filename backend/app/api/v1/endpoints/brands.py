"""Brand endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.brand import Brand
from app.schemas.brand import BrandCreate, BrandListResponse, BrandResponse, BrandUpdate

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("/", response_model=BrandListResponse)
async def list_brands(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    search: str | None = Query(None, description="Поиск по названию бренда"),
) -> BrandListResponse:
    """Получить список производителей."""
    from sqlalchemy import or_
    
    # Build query
    query = select(Brand)
    if active_only:
        query = query.where(Brand.active == True)
    
    # Search filter
    if search:
        search_term = f"%{search.lower()}%"
        query = query.where(Brand.name.ilike(search_term))

    # Count total
    count_query = select(func.count()).select_from(Brand)
    if active_only:
        count_query = count_query.where(Brand.active == True)
    if search:
        search_term = f"%{search.lower()}%"
        count_query = count_query.where(Brand.name.ilike(search_term))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(Brand.name)

    # Execute
    result = await db.execute(query)
    brands = result.scalars().all()

    pages = (total + size - 1) // size if total > 0 else 0

    return BrandListResponse(
        items=[BrandResponse.model_validate(brand) for brand in brands],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand(
    brand_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandResponse:
    """Получить производителя по ID."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    return BrandResponse.model_validate(brand)


@router.post("/", response_model=BrandResponse, status_code=201)
async def create_brand(
    data: BrandCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandResponse:
    """Создать производителя."""
    # Check if slug exists
    existing = await db.execute(select(Brand).where(Brand.slug == data.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Brand with this slug already exists")

    # Create brand
    brand = Brand(**data.model_dump())
    db.add(brand)
    await db.commit()
    await db.refresh(brand)

    return BrandResponse.model_validate(brand)


@router.patch("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: int,
    data: BrandUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandResponse:
    """Обновить производителя."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(brand, field, value)

    await db.commit()
    await db.refresh(brand)

    return BrandResponse.model_validate(brand)


@router.delete("/{brand_id}", status_code=204)
async def delete_brand(
    brand_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Удалить производителя."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    await db.delete(brand)
    await db.commit()

    """Удалить производителя."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    await db.delete(brand)
    await db.commit()


