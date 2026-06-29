"""Filament line endpoints (группировка вариантов-цвета бренда)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_BRAND_NOT_FOUND,
    ERR_FILAMENT_LINE_NOT_FOUND,
    ERR_NO_PERMISSION_EDIT_FILAMENT,
    raise_error,
)
from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament, FilamentAvailability
from app.models.filament_line import FilamentLine
from app.models.user import User, UserRole
from app.schemas.filament import (
    FilamentImportResult,
    FilamentImportRowResult,
    FilamentLineCreate,
    FilamentLineResponse,
    FilamentLineUpdate,
    FilamentPaletteCreate,
)
from app.services.preset_moderation import validate_text_field
from app.services.slug_service import generate_unique_slug

router = APIRouter(prefix="/filament-lines", tags=["filament-lines"])


def _can_manage(user: User, brand_id: int) -> bool:
    return user.role == UserRole.ADMIN or user.brand_id == brand_id


async def _to_response(db: AsyncSession, line: FilamentLine) -> FilamentLineResponse:
    count = await db.scalar(
        select(func.count()).select_from(Filament).where(Filament.line_id == line.id)
    )
    return FilamentLineResponse(
        id=line.id,
        brand_id=line.brand_id,
        name=line.name,
        filaments_count=count or 0,
        created_at=line.created_at,
    )


@router.get("", response_model=list[FilamentLineResponse])
async def list_filament_lines(
    db: Annotated[AsyncSession, Depends(get_db)],
    brand_id: int = Query(..., gt=0),
) -> list[FilamentLineResponse]:
    """Линейки бренда (публично, для группировки в каталоге)."""
    result = await db.execute(
        select(FilamentLine).where(FilamentLine.brand_id == brand_id).order_by(FilamentLine.name)
    )
    lines = result.scalars().all()
    return [await _to_response(db, line) for line in lines]


@router.post("", response_model=FilamentLineResponse, status_code=201)
async def create_filament_line(
    data: FilamentLineCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    brand_id: int = Query(..., gt=0),
) -> FilamentLineResponse:
    """Создать линейку бренда."""
    brand = await db.scalar(select(Brand).where(Brand.id == brand_id))
    if brand is None:
        raise_error(404, ERR_BRAND_NOT_FOUND)
    if not _can_manage(current_user, brand_id):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)

    line = FilamentLine(brand_id=brand_id, name=data.name.strip())
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return await _to_response(db, line)


@router.patch("/{line_id}", response_model=FilamentLineResponse)
async def update_filament_line(
    line_id: int,
    data: FilamentLineUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> FilamentLineResponse:
    """Переименовать линейку."""
    line = await db.scalar(select(FilamentLine).where(FilamentLine.id == line_id))
    if line is None:
        raise_error(404, ERR_FILAMENT_LINE_NOT_FOUND)
    if not _can_manage(current_user, line.brand_id):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)

    line.name = data.name.strip()
    await db.commit()
    await db.refresh(line)
    return await _to_response(db, line)


@router.post("/{line_id}/variants", response_model=FilamentImportResult)
async def create_line_variants(
    line_id: int,
    data: FilamentPaletteCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> FilamentImportResult:
    """Создать набор цветов-вариантов в линейке: общие параметры + список цветов.

    Каждый цвет становится отдельным материалом (со своим QR у верифиц. бренда),
    но в одной линейке. Имя по умолчанию — «⟨Линейка⟩ ⟨Цвет⟩», можно переопределить.
    """
    from app.api.v1.endpoints.filaments import _validate_custom_filler

    line = await db.scalar(select(FilamentLine).where(FilamentLine.id == line_id))
    if line is None:
        raise_error(404, ERR_FILAMENT_LINE_NOT_FOUND)
    brand = await db.scalar(select(Brand).where(Brand.id == line.brand_id))
    if brand is None:
        raise_error(404, ERR_BRAND_NOT_FOUND)
    if not _can_manage(current_user, line.brand_id):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)

    # Кастомный наполнитель — только для верифицированного бренда (проверяем один раз).
    await _validate_custom_filler(data.visual_settings, brand, current_user, db)

    material_type = data.material_type.strip()
    availability = FilamentAvailability(data.availability)

    result = FilamentImportResult()
    for index, variant in enumerate(data.variants, start=1):
        color_name = variant.color_name.strip()
        if not color_name:
            result.errors += 1
            result.rows.append(FilamentImportRowResult(
                row=index, status="error", message="ERR_VALIDATION_REQUIRED",
            ))
            continue

        name = (variant.name or f"{line.name} {color_name}").strip()
        is_valid, _ = await validate_text_field(name, db, "filament_name")
        if not is_valid:
            result.errors += 1
            result.rows.append(FilamentImportRowResult(
                row=index, status="error", name=name, message="ERR_VALIDATION_TEXT",
            ))
            continue

        color_hex = variant.color_hex.strip().upper() if variant.color_hex else None

        duplicate = await db.scalar(
            select(Filament.id).where(
                Filament.brand_id == line.brand_id,
                Filament.active.is_(True),
                func.lower(func.trim(Filament.name)) == name.lower(),
                func.lower(func.trim(Filament.material_type)) == material_type.lower(),
                func.coalesce(func.lower(func.trim(Filament.color_name)), "") == color_name.lower(),
            )
        )
        if duplicate is not None:
            result.skipped += 1
            result.rows.append(FilamentImportRowResult(
                row=index, status="skipped", name=name, filament_id=duplicate,
                message="ERR_FILAMENT_ALREADY_EXISTS",
            ))
            continue

        # visual_settings — общие, но первый цвет = цвет варианта.
        visual = None
        if data.visual_settings is not None:
            visual = data.visual_settings.model_dump()
            if color_hex:
                visual["colors"] = [color_hex]

        slug = await generate_unique_slug(db=db, model=Filament, source=name, fallback="filament")
        filament = Filament(
            brand_id=line.brand_id,
            line_id=line_id,
            name=name,
            material_type=material_type,
            color_name=color_name,
            color_hex=color_hex if color_hex and color_hex.startswith("#") else None,
            visual_settings=visual,
            diameter=data.diameter,
            density=data.density,
            price_per_kg=data.price_per_kg,
            spool_weight=data.spool_weight,
            empty_spool_weight_g=data.empty_spool_weight_g,
            description=data.description,
            availability=availability,
            price_display_unit=data.price_display_unit,
            slug=slug,
            active=True,
        )
        db.add(filament)
        await db.flush()

        if brand.verified:
            from app.services.qr_service import generate_short_code, save_qr_code_image
            short_code = generate_short_code(filament.id)
            if await db.scalar(select(Filament.id).where(Filament.qr_code == short_code)):
                short_code = f"{short_code}-{filament.id % 1000}"
            filament.qr_code = short_code
            save_qr_code_image(short_code, sizes=[300, 600, 1200])

        result.created += 1
        result.rows.append(FilamentImportRowResult(
            row=index, status="created", name=name, filament_id=filament.id,
        ))

    await db.commit()
    return result


@router.delete("/{line_id}", status_code=204)
async def delete_filament_line(
    line_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Удалить линейку (филаменты остаются, line_id у них становится NULL)."""
    line = await db.scalar(select(FilamentLine).where(FilamentLine.id == line_id))
    if line is None:
        raise_error(404, ERR_FILAMENT_LINE_NOT_FOUND)
    if not _can_manage(current_user, line.brand_id):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)

    await db.delete(line)
    await db.commit()
