"""Printer endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin_user
from app.db.session import get_db
from app.models.printer import Printer
from app.models.user import User
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
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterResponse:
    """Создать принтер (admin only)."""
    # Проверяем уникальность slug
    slug_result = await db.execute(select(Printer).where(Printer.slug == data.slug))
    existing = slug_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="Printer with this slug already exists")
    
    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    is_valid, error_msg = await validate_text_field(data.name, db, "Название принтера")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    if data.description:
        is_valid, error_msg = await validate_text_field(data.description, db, "Описание принтера")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
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
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterResponse:
    """Обновить принтер (admin only)."""
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
    
    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    update_data = data.model_dump(exclude_unset=True)
    
    if "name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["name"], db, "Название принтера")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    if "description" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["description"], db, "Описание принтера")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    # Update fields
    for field, value in update_data.items():
        setattr(printer, field, value)
    
    await db.commit()
    await db.refresh(printer)
    
    return PrinterResponse.model_validate(printer)


@router.delete("/{printer_id}", status_code=204)
async def delete_printer(
    printer_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Удалить принтер (admin only)."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    
    await db.delete(printer)
    await db.commit()

