"""Printer profile endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.printer_profile import PrinterProfile
from app.models.user import User, UserRole
from app.schemas.printer_profile import (
    PrinterProfileCreate,
    PrinterProfileListResponse,
    PrinterProfileResponse,
    PrinterProfileUpdate,
)
from app.services.orcaslicer_machine_exporter import export_printer_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/printer-profiles", tags=["printer-profiles"])


@router.get("/", response_model=PrinterProfileListResponse)
async def list_printer_profiles(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    is_official: bool | None = Query(None),
    printer_id: int | None = Query(None, ge=1),
    owner_user_id: int | None = Query(None, ge=1),
    search: str | None = Query(None, min_length=1),
) -> PrinterProfileListResponse:
    """List printer profiles with optional filtering."""

    query = select(PrinterProfile).options(selectinload(PrinterProfile.printer))

    if active_only:
        query = query.where(PrinterProfile.active.is_(True))
    if is_official is not None:
        query = query.where(PrinterProfile.is_official.is_(is_official))
    if printer_id is not None:
        query = query.where(PrinterProfile.printer_id == printer_id)
    if owner_user_id is not None:
        query = query.where(PrinterProfile.owner_user_id == owner_user_id)
    if search:
        like = f"%{search.lower()}%"
        query = query.where(
            or_(
                PrinterProfile.name.ilike(like),
                PrinterProfile.slug.ilike(like),
                PrinterProfile.description.ilike(like),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * size
    query = query.order_by(PrinterProfile.created_at.desc()).offset(offset).limit(size)

    result = await db.execute(query.options(selectinload(PrinterProfile.printer)))
    profiles = result.scalars().all()

    pages = (total + size - 1) // size if total else 0

    return PrinterProfileListResponse(
        items=[PrinterProfileResponse.model_validate(profile) for profile in profiles],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{profile_id}", response_model=PrinterProfileResponse)
async def get_printer_profile(
    profile_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterProfileResponse:
    """Get printer profile by ID."""

    result = await db.execute(
        select(PrinterProfile).options(selectinload(PrinterProfile.printer)).where(PrinterProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer profile not found")

    return PrinterProfileResponse.model_validate(profile)


@router.post("/", response_model=PrinterProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_printer_profile(
    data: PrinterProfileCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterProfileResponse:
    """Create a printer profile."""

    owner_user_id = data.owner_user_id or current_user.id

    if data.is_official and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can publish official profiles")

    if current_user.role != UserRole.ADMIN and owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign owner to another user")

    existing_slug = await db.execute(select(PrinterProfile).where(PrinterProfile.slug == data.slug))
    if existing_slug.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug already exists")

    from app.services.preset_moderation import validate_text_field

    is_valid, error_msg = await validate_text_field(data.name, db, "Название профиля принтера")
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    if data.description:
        is_valid, error_msg = await validate_text_field(data.description, db, "Описание профиля принтера")
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    profile = PrinterProfile(
        name=data.name,
        slug=data.slug,
        description=data.description,
        printer_id=data.printer_id,
        owner_user_id=owner_user_id,
        is_official=data.is_official if current_user.role == UserRole.ADMIN else False,
        active=data.active,
        source=data.source,
        vendor=data.vendor,
        external_id=data.external_id,
        setting_id=data.setting_id,
        nozzle_diameters=data.nozzle_diameters,
        printable_area=data.printable_area,
        printable_height_mm=data.printable_height_mm,
        default_print_profile_slug=data.default_print_profile_slug,
        orcaslicer_settings=data.orcaslicer_settings or {},
        extra_metadata=data.extra_metadata,
        start_gcode=data.start_gcode,
        end_gcode=data.end_gcode,
        notes=data.notes,
    )

    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return PrinterProfileResponse.model_validate(profile)


@router.patch("/{profile_id}", response_model=PrinterProfileResponse)
async def update_printer_profile(
    profile_id: int,
    data: PrinterProfileUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterProfileResponse:
    """Update a printer profile."""

    result = await db.execute(select(PrinterProfile).where(PrinterProfile.id == profile_id))
    profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer profile not found")

    is_owner = profile.owner_user_id == current_user.id if profile.owner_user_id else False

    if current_user.role != UserRole.ADMIN and not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    update_data = data.model_dump(exclude_unset=True)

    if "slug" in update_data:
        slug_result = await db.execute(select(PrinterProfile).where(PrinterProfile.slug == update_data["slug"], PrinterProfile.id != profile_id))
        if slug_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug already exists")

    if "is_official" in update_data and update_data["is_official"] and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can set official status")

    from app.services.preset_moderation import validate_text_field

    if "name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["name"], db, "Название профиля принтера")
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    if "description" in update_data and update_data["description"]:
        is_valid, error_msg = await validate_text_field(update_data["description"], db, "Описание профиля принтера")
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    if "owner_user_id" in update_data and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can reassign owner")

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return PrinterProfileResponse.model_validate(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_printer_profile(
    profile_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a printer profile."""

    result = await db.execute(select(PrinterProfile).where(PrinterProfile.id == profile_id))
    profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer profile not found")

    is_owner = profile.owner_user_id == current_user.id if profile.owner_user_id else False

    if current_user.role != UserRole.ADMIN and not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    await db.delete(profile)
    await db.commit()


@router.get("/{profile_id}/export/orcaslicer.json")
async def export_printer_profile_json(
    profile_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """
    Экспортировать профиль принтера в формате OrcaSlicer (.json).
    
    Returns:
        JSONResponse: JSON файл профиля принтера OrcaSlicer
    """
    # Получаем printer profile с printer
    result = await db.execute(
        select(PrinterProfile)
        .options(selectinload(PrinterProfile.printer))
        .where(PrinterProfile.id == profile_id, PrinterProfile.active == True)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Printer profile not found")
    
    # Экспортируем в JSON
    try:
        profile_json = await export_printer_profile(profile, db)
    except Exception as e:
        logger.error(f"Error exporting printer profile {profile_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exporting printer profile: {str(e)}")
    
    # Формируем безопасное имя файла
    def to_safe_filename(text: str) -> str:
        """Преобразует текст в безопасное имя файла, сохраняя кириллицу и пробелы."""
        if not text:
            return ""
        safe = text.replace("<", "_").replace(">", "_").replace(":", "_")
        safe = safe.replace('"', "_").replace("/", "_").replace("\\", "_")
        safe = safe.replace("|", "_").replace("?", "_").replace("*", "_")
        while "__" in safe:
            safe = safe.replace("__", "_")
        return safe.strip(" _")
    
    filename = to_safe_filename(profile.name) + ".json"
    
    # Возвращаем JSON файл
    return Response(
        content=profile_json,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
