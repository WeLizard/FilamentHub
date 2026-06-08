"""Print profile endpoints."""

import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_CANNOT_ASSIGN_OTHER_OWNER,
    ERR_EXPORT_PRINT_PROFILE_ERROR,
    ERR_NO_PERMISSION,
    ERR_ONLY_ADMIN_OFFICIAL,
    ERR_ONLY_ADMIN_REASSIGN,
    ERR_PRINT_PROFILE_NOT_FOUND,
    ERR_SLUG_EXISTS,
    raise_error,
)
from app.core.utils import like_pattern
from app.db.session import get_db
from app.models.filament import Filament
from app.models.print_profile import PrintProfile
from app.models.print_profile_filament import PrintProfileFilament
from app.models.print_profile_printer import PrintProfilePrinter
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
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


def _extract_base_printer_name(name: str) -> str:
    """Remove the common Orca nozzle suffix from printer profile names."""
    match = re.match(r"^(.*?)\s+\d+(?:\.\d+)?\s*nozzle$", name.strip(), re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return name.strip()


def _slugify_string(value: str, fallback: str = "item") -> str:
    """Generate a stable slug-like value for compatibility links."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


async def _resolve_print_profile_printer_link(
    *,
    db: AsyncSession,
    owner_user_id: int | None,
    identifier: str,
) -> tuple[int | None, str]:
    """Resolve compatible printer entry to a FilamentHub printer link."""
    name = (identifier or "").strip()
    if not name:
        return None, ""

    printer: Printer | None = None

    if name.isdigit():
        printer = await db.get(Printer, int(name))

    if printer is None:
        result = await db.execute(
            select(Printer).where(
                or_(
                    Printer.slug == name,
                    Printer.name == name,
                    Printer.model == name,
                )
            )
        )
        printer = result.scalars().first()

    if printer is not None:
        return printer.id, printer.slug

    printer_profile: PrinterProfile | None = None
    if owner_user_id is not None:
        result = await db.execute(
            select(PrinterProfile).where(
                PrinterProfile.owner_user_id == owner_user_id,
                or_(
                    PrinterProfile.name == name,
                    PrinterProfile.slug == name,
                ),
            )
        )
        printer_profile = result.scalars().first()

    if printer_profile is None:
        result = await db.execute(
            select(PrinterProfile).where(
                or_(
                    PrinterProfile.name == name,
                    PrinterProfile.slug == name,
                )
            )
        )
        printer_profile = result.scalars().first()

    if printer_profile is not None and printer_profile.printer_id:
        printer = await db.get(Printer, printer_profile.printer_id)
        if printer is not None:
            return printer.id, printer.slug

    base_name = _extract_base_printer_name(name)
    if base_name and base_name != name:
        result = await db.execute(
            select(Printer).where(
                or_(
                    Printer.name == base_name,
                    Printer.model == base_name,
                    Printer.slug == _slugify_string(base_name),
                )
            )
        )
        printer = result.scalars().first()
        if printer is not None:
            return printer.id, printer.slug

    return None, _slugify_string(name)[:200]


async def _resolve_print_profile_filament_link(
    *,
    db: AsyncSession,
    identifier: str,
) -> tuple[int | None, str]:
    """Resolve compatible filament entry to a FilamentHub filament link."""
    name = (identifier or "").strip()
    if not name:
        return None, ""

    filament: Filament | None = None
    if name.isdigit():
        filament = await db.get(Filament, int(name))

    if filament is None:
        result = await db.execute(
            select(Filament).where(
                or_(
                    Filament.slug == name,
                    Filament.name == name,
                )
            )
        )
        filament = result.scalars().first()

    if filament is None and "@" in name:
        short_name = name.split("@", 1)[0].strip()
        if short_name:
            result = await db.execute(select(Filament).where(Filament.name == short_name))
            filament = result.scalars().first()

    if filament is not None:
        return filament.id, filament.slug

    return None, _slugify_string(name)[:200]


async def _sync_print_profile_links(
    *,
    db: AsyncSession,
    profile: PrintProfile,
) -> None:
    """Synchronise print profile compatibility junction tables."""
    await profile.awaitable_attrs.printer_links
    await profile.awaitable_attrs.filament_links
    profile.printer_links.clear()
    profile.filament_links.clear()

    printer_slugs: set[str] = set()
    for entry in profile.compatible_printers or []:
        printer_id, printer_slug = await _resolve_print_profile_printer_link(
            db=db,
            owner_user_id=profile.owner_user_id,
            identifier=entry,
        )
        if not printer_slug or printer_slug in printer_slugs:
            continue
        printer_slugs.add(printer_slug)
        profile.printer_links.append(
            PrintProfilePrinter(
                printer_id=printer_id,
                printer_slug=printer_slug,
                relation_type="explicit",
            )
        )

    condition = ""
    if isinstance(profile.extra_metadata, dict):
        condition = str(profile.extra_metadata.get("compatible_printers_condition") or "").strip()
    if condition:
        condition_slug = _slugify_string(condition, fallback="condition")[:200]
        if condition_slug in printer_slugs:
            condition_slug = f"{condition_slug}-{len(printer_slugs) + 1}"[:200]
        profile.printer_links.append(
            PrintProfilePrinter(
                printer_id=None,
                printer_slug=condition_slug,
                relation_type="condition",
                condition=condition,
            )
        )

    filament_slugs: set[str] = set()
    for entry in profile.compatible_filaments or []:
        filament_id, filament_slug = await _resolve_print_profile_filament_link(
            db=db,
            identifier=entry,
        )
        if not filament_slug or filament_slug in filament_slugs:
            continue
        filament_slugs.add(filament_slug)
        profile.filament_links.append(
            PrintProfileFilament(
                filament_id=filament_id,
                filament_slug=filament_slug,
                relation_type="explicit",
            )
        )

    await db.flush()


async def _load_print_profile_with_links(
    *,
    db: AsyncSession,
    profile_id: int,
) -> PrintProfile | None:
    """Load a print profile with compatibility links eagerly fetched."""
    return (
        await db.execute(
            select(PrintProfile)
            .options(
                selectinload(PrintProfile.printer_links),
                selectinload(PrintProfile.filament_links),
            )
            .where(PrintProfile.id == profile_id)
        )
    ).scalar_one_or_none()


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
        like = like_pattern(search)
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

    profile = await _load_print_profile_with_links(db=db, profile_id=profile_id)
    if profile is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRINT_PROFILE_NOT_FOUND)
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
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ONLY_ADMIN_OFFICIAL)

    if current_user.role != UserRole.ADMIN and owner_user_id != current_user.id:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_CANNOT_ASSIGN_OTHER_OWNER)

    existing_slug = await db.execute(select(PrintProfile).where(PrintProfile.slug == data.slug))
    if existing_slug.scalar_one_or_none():
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_SLUG_EXISTS)

    from app.services.preset_moderation import validate_text_field

    is_valid, error_msg = await validate_text_field(data.name, db, "print_profile_name")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)  # bad words validation

    if data.description:
        is_valid, error_msg = await validate_text_field(data.description, db, "print_profile_description")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)  # bad words validation

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
    await db.flush()
    await _sync_print_profile_links(db=db, profile=profile)
    await db.commit()

    profile_with_links = await _load_print_profile_with_links(db=db, profile_id=profile.id)
    if profile_with_links is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRINT_PROFILE_NOT_FOUND)

    return PrintProfileResponse.model_validate(profile_with_links)


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
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRINT_PROFILE_NOT_FOUND)

    is_owner = profile.owner_user_id == current_user.id if profile.owner_user_id else False
    if current_user.role != UserRole.ADMIN and not is_owner:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_NO_PERMISSION)

    update_data = data.model_dump(exclude_unset=True)

    if "slug" in update_data:
        slug_exists = await db.execute(
            select(PrintProfile).where(
                PrintProfile.slug == update_data["slug"],
                PrintProfile.id != profile_id,
            )
        )
        if slug_exists.scalar_one_or_none():
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_SLUG_EXISTS)

    if "is_official" in update_data and update_data["is_official"] and current_user.role != UserRole.ADMIN:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ONLY_ADMIN_OFFICIAL)

    if "owner_user_id" in update_data and current_user.role != UserRole.ADMIN:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ONLY_ADMIN_REASSIGN)

    from app.services.preset_moderation import validate_text_field

    if "name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["name"], db, "print_profile_name")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)  # bad words validation

    if "description" in update_data and update_data["description"]:
        is_valid, error_msg = await validate_text_field(update_data["description"], db, "print_profile_description")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)  # bad words validation

    for field, value in update_data.items():
        setattr(profile, field, value)

    await _sync_print_profile_links(db=db, profile=profile)
    await db.commit()

    profile_with_links = await _load_print_profile_with_links(db=db, profile_id=profile_id)
    if profile_with_links is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRINT_PROFILE_NOT_FOUND)

    return PrintProfileResponse.model_validate(profile_with_links)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_print_profile(
    profile_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a print profile."""

    profile = (await db.execute(select(PrintProfile).where(PrintProfile.id == profile_id))).scalar_one_or_none()
    if profile is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRINT_PROFILE_NOT_FOUND)

    is_owner = profile.owner_user_id == current_user.id if profile.owner_user_id else False
    if current_user.role != UserRole.ADMIN and not is_owner:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_NO_PERMISSION)

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
    # Получаем print profile с связями для правильного экспорта
    result = await db.execute(
        select(PrintProfile)
        .options(
            selectinload(PrintProfile.printer_links),
            selectinload(PrintProfile.filament_links),
        )
        .where(PrintProfile.id == profile_id, PrintProfile.active == True)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise_error(404, ERR_PRINT_PROFILE_NOT_FOUND)

    # Экспортируем в JSON
    try:
        profile_json = await export_print_profile(profile, db)
    except Exception as e:
        logger.error(f"Error exporting print profile {profile_id}: {str(e)}", exc_info=True)
        raise_error(500, ERR_EXPORT_PRINT_PROFILE_ERROR)

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
