"""Printer endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.printer import Printer
from app.schemas.printer import (
    PrinterCreate,
    PrinterListResponse,
    PrinterResponse,
    PrinterUpdate,
)

router = APIRouter(prefix="/printers", tags=["printers"])


@router.get("/", response_model=PrinterListResponse)
async def list_printers(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    manufacturer: str | None = Query(None, min_length=1),
    search: str | None = Query(None, min_length=1),
) -> PrinterListResponse:
    """Получить список принтеров."""
    # Build query
    query = select(Printer)
    
    if active_only:
        query = query.where(Printer.active == True)
    
    if manufacturer:
        query = query.where(Printer.manufacturer.ilike(f"%{manufacturer}%"))
    
    if search:
        query = query.where(
            Printer.name.ilike(f"%{search}%")
            | Printer.manufacturer.ilike(f"%{search}%")
            | Printer.model.ilike(f"%{search}%")
        )
    
    # Count total
    count_query = select(func.count()).select_from(Printer)
    if active_only:
        count_query = count_query.where(Printer.active == True)
    if manufacturer:
        count_query = count_query.where(Printer.manufacturer.ilike(f"%{manufacturer}%"))
    if search:
        count_query = count_query.where(
            Printer.name.ilike(f"%{search}%")
            | Printer.manufacturer.ilike(f"%{search}%")
            | Printer.model.ilike(f"%{search}%")
        )
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(
        Printer.manufacturer.asc(), Printer.name.asc()
    )
    
    # Execute
    result = await db.execute(query)
    printers = result.scalars().all()
    
    pages = (total + size - 1) // size if total > 0 else 0
    
    return PrinterListResponse(
        items=[PrinterResponse.model_validate(printer) for printer in printers],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{printer_id}", response_model=PrinterResponse)
async def get_printer(
    printer_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterResponse:
    """Получить принтер по ID."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    
    return PrinterResponse.model_validate(printer)


@router.post("/", response_model=PrinterResponse, status_code=201)
async def create_printer(
    data: PrinterCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterResponse:
    """Создать принтер (admin only - будет добавлена авторизация позже)."""
    # Проверяем уникальность slug
    slug_result = await db.execute(select(Printer).where(Printer.slug == data.slug))
    existing = slug_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="Printer with this slug already exists")
    
    # Create printer
    printer = Printer(**data.model_dump())
    db.add(printer)
    await db.commit()
    await db.refresh(printer)
    
    return PrinterResponse.model_validate(printer)


@router.patch("/{printer_id}", response_model=PrinterResponse)
async def update_printer(
    printer_id: int,
    data: PrinterUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterResponse:
    """Обновить принтер (admin only - будет добавлена авторизация позже)."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    
    # Проверяем уникальность slug если он обновляется
    if data.slug and data.slug != printer.slug:
        slug_result = await db.execute(select(Printer).where(Printer.slug == data.slug))
        existing = slug_result.scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Printer with this slug already exists")
    
    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(printer, field, value)
    
    await db.commit()
    await db.refresh(printer)
    
    return PrinterResponse.model_validate(printer)


@router.delete("/{printer_id}", status_code=204)
async def delete_printer(
    printer_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Удалить принтер (admin only - будет добавлена авторизация позже)."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    
    await db.delete(printer)
    await db.commit()

