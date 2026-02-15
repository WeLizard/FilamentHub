"""Printer endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_admin_user
from app.core.utils import like_pattern
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
        query = query.where(Printer.manufacturer.ilike(like_pattern(manufacturer)))

    if search:
        search_pat = like_pattern(search)
        query = query.where(
            Printer.name.ilike(search_pat)
            | Printer.manufacturer.ilike(search_pat)
            | Printer.model.ilike(search_pat)
        )

    # Count total
    count_query = select(func.count()).select_from(Printer)
    if active_only:
        count_query = count_query.where(Printer.active == True)
    if manufacturer:
        count_query = count_query.where(Printer.manufacturer.ilike(like_pattern(manufacturer)))
    if search:
        search_pat = like_pattern(search)
        count_query = count_query.where(
            Printer.name.ilike(search_pat)
            | Printer.manufacturer.ilike(search_pat)
            | Printer.model.ilike(search_pat)
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


@router.get("/{printer_id}/compatible-filaments", response_model=list[dict])
async def get_compatible_filaments(
    printer_id: int,
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> list[dict]:
    """
    Получить список филаментов, совместимых с принтером.
    
    Использует VIEW filament_printer_compatibility_view для вывода совместимости
    на основе существующих связей через Preset и PrintProfile.
    """
    from sqlalchemy import text
    from app.models.filament import Filament
    from app.models.brand import Brand
    
    # Проверяем существование принтера
    printer = await db.get(Printer, printer_id)
    if not printer:
        raise HTTPException(status_code=404, detail="Принтер не найден")
    
    # Используем VIEW для получения совместимых филаментов
    query = text("""
        SELECT DISTINCT
            filament_id,
            filament_slug,
            filament_name,
            relation_source,
            MAX(confidence_score) as confidence_score
        FROM filament_printer_compatibility_view
        WHERE printer_id = :printer_id
          AND confidence_score >= :min_confidence
        GROUP BY filament_id, filament_slug, filament_name, relation_source
        ORDER BY confidence_score DESC, filament_name
    """)
    
    result = await db.execute(query, {"printer_id": printer_id, "min_confidence": min_confidence})
    rows = result.fetchall()
    
    # Получаем дополнительную информацию о филаментах
    filament_ids = [row[0] for row in rows]
    if not filament_ids:
        return []
    
    filaments_query = select(Filament).options(selectinload(Filament.brand)).where(Filament.id.in_(filament_ids))
    filaments_result = await db.execute(filaments_query)
    filaments = {f.id: f for f in filaments_result.scalars().all()}
    
    # Формируем ответ
    compatible_filaments = []
    for row in rows:
        filament_id, filament_slug, filament_name, relation_source, confidence_score = row
        filament = filaments.get(filament_id)
        if filament:
            compatible_filaments.append({
                "id": filament.id,
                "slug": filament.slug,
                "name": filament.name,
                "material_type": filament.material_type,
                "brand_name": filament.brand.name if filament.brand else None,
                "relation_source": relation_source,
                "confidence_score": float(confidence_score),
            })
    
    return compatible_filaments

