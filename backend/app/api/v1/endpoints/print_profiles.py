"""Print profile endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.print_profile import PrintProfile
from app.models.user import User, UserRole
from app.schemas.print_profile import (
    PrintProfileCreate,
    PrintProfileListResponse,
    PrintProfileResponse,
    PrintProfileUpdate,
)
from app.services.orcaslicer_machine_exporter import export_print_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/print-profiles", tags=["print-profiles"])


@router.get("/", response_model=PrintProfileListResponse)
async def list_print_profiles(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    is_official: bool | None = Query(None),
    owner_user_id: int | None = Query(None, ge=1),
    category: str | None = Query(None, min_length=1),
    search: str | None = Query(None, min_length=1),
) -> PrintProfileListResponse:
    """List print profiles."""

    query = select(PrintProfile).options(
        selectinload(PrintProfile.printer_links),
        selectinload(PrintProfile.filament_links),
    )

    if active_only:
        query = query.where(PrintProfile.active.is_(True))
    if is_official is not None:
        query = query.where(PrintProfile.is_official.is_(is_official))
    if owner_user_id is not None:
        query = query.where(PrintProfile.owner_user_id == owner_user_id)
    if category:
        query = query.where(PrintProfile.category == category)
    if search:
        like = f"%{search.lower()}%"
        query = query.where(
            or_(
                PrintProfile.name.ilike(like),
                PrintProfile.slug.ilike(like),
                PrintProfile.description.ilike(like),
            )
        )

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()

    offset = (page - 1) * size
    query = query.order_by(PrintProfile.created_at.desc()).offset(offset).limit(size)

    profiles = (await db.execute(query)).scalars().all()
    pages = (total + size - 1) // size if total else 0

    return PrintProfileListResponse(
        items=[PrintProfileResponse.model_validate(profile) for profile in profiles],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{profile_id}", response_model=PrintProfileResponse)
async def get_print_profile(
    profile_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintProfileResponse:
    """Get print profile by ID."""

    profile = (
        await db.execute(
            select(PrintProfile)
            .options(
                selectinload(PrintProfile.printer_links),
                selectinload(PrintProfile.filament_links),
            )
            .where(PrintProfile.id == profile_id)
        )
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print profile not found")
    return PrintProfileResponse.model_validate(profile)


@router.post("/", response_model=PrintProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_print_profile(
    data: PrintProfileCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintProfileResponse:
    """Create a print profile."""

    owner_user_id = data.owner_user_id or current_user.id

    if data.is_official and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can publish official profiles")

    if current_user.role != UserRole.ADMIN and owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign owner to another user")

    existing_slug = await db.execute(select(PrintProfile).where(PrintProfile.slug == data.slug))
    if existing_slug.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug already exists")

    from app.services.preset_moderation import validate_text_field

    is_valid, error_msg = await validate_text_field(data.name, db, "Название профиля печати")
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    if data.description:
        is_valid, error_msg = await validate_text_field(data.description, db, "Описание профиля печати")
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    profile = PrintProfile(
        name=data.name,
        slug=data.slug,
        description=data.description,
        category=data.category,
        owner_user_id=owner_user_id,
        is_official=data.is_official if current_user.role == UserRole.ADMIN else False,
        active=data.active,
        source=data.source,
        vendor=data.vendor,
        external_id=data.external_id,
        setting_id=data.setting_id,
        quality_tier=data.quality_tier,
        default_nozzle=data.default_nozzle,
        layer_height_mm=data.layer_height_mm,
        compatible_printers=data.compatible_printers,
        compatible_filaments=data.compatible_filaments,
        orcaslicer_settings=data.orcaslicer_settings or {},
        extra_metadata=data.extra_metadata,
        notes=data.notes,
    )

    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return PrintProfileResponse.model_validate(profile)


@router.patch("/{profile_id}", response_model=PrintProfileResponse)
async def update_print_profile(
    profile_id: int,
    data: PrintProfileUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintProfileResponse:
    """Update a print profile."""

    profile = (await db.execute(select(PrintProfile).where(PrintProfile.id == profile_id))).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print profile not found")

    is_owner = profile.owner_user_id == current_user.id if profile.owner_user_id else False
    if current_user.role != UserRole.ADMIN and not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    update_data = data.model_dump(exclude_unset=True)

    if "slug" in update_data:
        slug_exists = await db.execute(
            select(PrintProfile).where(
                PrintProfile.slug == update_data["slug"],
                PrintProfile.id != profile_id,
            )
        )
        if slug_exists.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug already exists")

    if "is_official" in update_data and update_data["is_official"] and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can set official status")

    if "owner_user_id" in update_data and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can reassign owner")

    from app.services.preset_moderation import validate_text_field

    if "name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["name"], db, "Название профиля печати")
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    if "description" in update_data and update_data["description"]:
        is_valid, error_msg = await validate_text_field(update_data["description"], db, "Описание профиля печати")
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)

    return PrintProfileResponse.model_validate(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_print_profile(
    profile_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a print profile."""

    profile = (await db.execute(select(PrintProfile).where(PrintProfile.id == profile_id))).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print profile not found")

    is_owner = profile.owner_user_id == current_user.id if profile.owner_user_id else False
    if current_user.role != UserRole.ADMIN and not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    await db.delete(profile)
    await db.commit()


@router.get("/{profile_id}/export/orcaslicer.json")
async def export_print_profile_json(
    profile_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """
    Экспортировать профиль печати в формате OrcaSlicer (.json).
    
    Returns:
        JSONResponse: JSON файл профиля печати OrcaSlicer
    """
    # Получаем print profile
    result = await db.execute(
        select(PrintProfile).where(PrintProfile.id == profile_id, PrintProfile.active == True)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Print profile not found")
    
    # Экспортируем в JSON
    try:
        profile_json = export_print_profile(profile)
    except Exception as e:
        logger.error(f"Error exporting print profile {profile_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exporting print profile: {str(e)}")
    
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
