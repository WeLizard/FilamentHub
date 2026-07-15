"""Brand endpoints."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_active_user,
    get_current_admin_user,
    get_current_user,
)
from app.core.errors import (
    ERR_BRAND_NAME_CORRECTION_USED,
    ERR_BRAND_NAME_EXISTS,
    ERR_BRAND_NOT_FOUND,
    ERR_BRAND_SLUG_EXISTS,
    ERR_BRAND_SLUG_INVALID,
    ERR_BRAND_SLUG_RENAME_REQUIRED,
    ERR_FILE_EXT_NOT_ALLOWED,
    ERR_FILE_SIZE_EXCEEDED,
    ERR_INVALID_FILE_PATH,
    ERR_NO_PERMISSION,
    raise_error,
)
from app.core.utils import like_pattern
from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.organization import OrganizationMembership
from app.models.preset import Preset
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.models.user_spool import UserSpool
from app.schemas.brand import (
    BrandCreate,
    BrandListResponse,
    BrandResponse,
    BrandSlugSuggestionResponse,
    BrandUpdate,
    BrandUsageResponse,
    PopularPrinterItem,
)
from app.services.brand_slug_service import (
    choose_brand_slug,
    resolve_brand_identifier,
    suggest_brand_slug,
)
from app.services.file_service import (
    BRAND_LOGO_ALLOWED_EXTENSIONS,
    get_upload_root_dir,
    normalize_brand_logo_upload,
)
from app.services.organization_access import can_edit_brand_catalog, can_view_private_brand_data

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

    # Build query
    query = select(Brand)
    if active_only:
        query = query.where(Brand.active == True)

    # Search filter
    if search:
        search_term = like_pattern(search)
        query = query.where(Brand.name.ilike(search_term))

    # Count total
    count_query = select(func.count()).select_from(Brand)
    if active_only:
        count_query = count_query.where(Brand.active == True)
    if search:
        search_term = like_pattern(search)
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


@router.get("/slug-suggestion", response_model=BrandSlugSuggestionResponse)
async def get_brand_slug_suggestion(
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Query(..., min_length=1, max_length=100),
) -> BrandSlugSuggestionResponse:
    """Suggest a canonical, currently available slug for a new brand."""
    return BrandSlugSuggestionResponse(slug=await suggest_brand_slug(db, name))


@router.get("/{identifier}", response_model=BrandResponse)
async def get_brand(
    identifier: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_employees_count: bool = Query(False, description="Включить количество сотрудников"),
) -> BrandResponse:
    """Resolve a brand by numeric ID, current slug or historical slug."""
    brand, _redirected_from = await resolve_brand_identifier(db, identifier)

    if not brand:
        raise_error(404, ERR_BRAND_NOT_FOUND)

    response = BrandResponse.model_validate(brand)

    # Если запрошено количество сотрудников - добавляем его
    if include_employees_count:
        if brand.organization_id is not None:
            employees_count = int(
                await db.scalar(
                    select(func.count(OrganizationMembership.id)).where(
                        OrganizationMembership.organization_id == brand.organization_id,
                        OrganizationMembership.active.is_(True),
                    )
                )
                or 0
            )
        else:
            # Compatibility fallback for brands that predate the organization
            # backfill. ``User.brand_id`` is never used as authorization.
            employees_count = int(
                await db.scalar(
                    select(func.count(User.id)).where(User.brand_id == brand.id)
                )
                or 0
            )
        response.employees_count = employees_count

    return response


@router.get("/{brand_id}/usage", response_model=BrandUsageResponse)
async def get_brand_usage(
    brand_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandUsageResponse:
    """Статистика использования материалов бренда для кабинета бренда."""
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one_or_none()
    if not brand:
        raise_error(404, ERR_BRAND_NOT_FOUND)

    if not await can_view_private_brand_data(db, current_user, brand_id):
        raise_error(403, ERR_NO_PERMISSION)

    printers_result = await db.execute(
        select(
            Printer.id,
            Printer.name,
            Printer.manufacturer,
            func.count(PresetPrinter.id).label("cnt"),
        )
        .select_from(PresetPrinter)
        .join(Preset, Preset.id == PresetPrinter.preset_id)
        .join(Filament, Filament.id == Preset.filament_id)
        .join(Printer, Printer.id == PresetPrinter.printer_id)
        .where(Filament.brand_id == brand_id, Preset.active == True)
        .group_by(Printer.id, Printer.name, Printer.manufacturer)
        .order_by(func.count(PresetPrinter.id).desc())
        .limit(10)
    )
    popular_printers = [
        PopularPrinterItem(
            printer_id=row.id, name=row.name, manufacturer=row.manufacturer, count=row.cnt
        )
        for row in printers_result.all()
    ]

    spools_tracked = (
        await db.execute(
            select(func.count(UserSpool.id))
            .select_from(UserSpool)
            .join(Filament, Filament.id == UserSpool.filament_id)
            .where(Filament.brand_id == brand_id)
        )
    ).scalar() or 0

    usage_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Preset.usage_count), 0),
                func.count(Preset.id),
            )
            .select_from(Preset)
            .join(Filament, Filament.id == Preset.filament_id)
            .where(Filament.brand_id == brand_id)
        )
    ).one()

    return BrandUsageResponse(
        popular_printers=popular_printers,
        spools_tracked=int(spools_tracked),
        total_preset_usage=int(usage_row[0] or 0),
        presets_count=int(usage_row[1] or 0),
    )


@router.post("/{brand_id}/backfill-qr")
async def backfill_brand_qr(
    brand_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """Сгенерировать QR-коды для материалов бренда, у которых их ещё нет.

    Для верифицированного бренда: закрывает материалы, созданные до верификации
    (напр. юзерами до прихода представителя). Доступно бренду или админу.
    """
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one_or_none()
    if not brand:
        raise_error(404, ERR_BRAND_NOT_FOUND)
    if not await can_edit_brand_catalog(db, current_user, brand_id):
        raise_error(403, ERR_NO_PERMISSION)

    from app.services.qr_service import backfill_brand_qr_codes
    assigned = await backfill_brand_qr_codes(brand, db)
    await db.commit()
    return {"assigned": assigned}


@router.post("/", response_model=BrandResponse, status_code=201)
async def create_brand(
    data: BrandCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BrandResponse:
    """Создать производителя."""
    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    is_valid, error_msg = await validate_text_field(data.name, db, "brand_name")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    if data.description:
        is_valid, error_msg = await validate_text_field(data.description, db, "brand_description")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    selected_slug, available = await choose_brand_slug(
        db,
        name=data.name,
        requested_slug=data.slug,
    )
    if selected_slug is None:
        raise_error(400, ERR_BRAND_SLUG_INVALID)
    if not available:
        raise_error(400, ERR_BRAND_SLUG_EXISTS)

    # Verification is a server-controlled state. Public brand creation must
    # never allow a caller to self-assign the verified manufacturer badge.
    brand_data = data.model_dump()
    brand_data["verified"] = False
    brand_data["slug"] = selected_slug

    # Create brand
    brand = Brand(**brand_data)
    db.add(brand)
    await db.commit()
    await db.refresh(brand)

    return BrandResponse.model_validate(brand)


@router.patch("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: int,
    data: BrandUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BrandResponse:
    """Обновить производителя."""
    result = await db.execute(
        select(Brand).where(Brand.id == brand_id).with_for_update()
    )
    brand = result.scalar_one_or_none()

    if not brand:
        raise_error(404, ERR_BRAND_NOT_FOUND)

    is_admin = current_user.role == UserRole.ADMIN
    is_employee = await can_edit_brand_catalog(db, current_user, brand_id)

    if not is_admin and not is_employee:
        raise_error(403, ERR_NO_PERMISSION)

    update_data = data.model_dump(exclude_unset=True)

    requested_slug = update_data.get("slug")
    if requested_slug is not None and requested_slug != brand.slug:
        raise_error(409, ERR_BRAND_SLUG_RENAME_REQUIRED)
    update_data.pop("slug", None)

    # A representative may correct the community-authored name exactly once
    # after the first verified claim. The existing slug is deliberately kept:
    # public links must not break as a side effect of correcting display text.
    if not is_admin:
        admin_only = {"verified", "active"}
        for field in admin_only:
            update_data.pop(field, None)

        requested_name = update_data.get("name")
        if requested_name is not None:
            requested_name = requested_name.strip()
            if requested_name == brand.name:
                update_data.pop("name", None)
            elif not brand.name_correction_available:
                raise_error(409, ERR_BRAND_NAME_CORRECTION_USED)
            else:
                duplicate = await db.scalar(
                    select(Brand.id).where(
                        Brand.id != brand.id,
                        func.lower(Brand.name) == requested_name.casefold(),
                    )
                )
                if duplicate is not None:
                    raise_error(409, ERR_BRAND_NAME_EXISTS)
                update_data["name"] = requested_name
                brand.name_correction_available = False
                brand.name_corrected_at = datetime.now(timezone.utc)

    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field

    if "name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["name"], db, "brand_name")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    if "description" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["description"], db, "brand_description")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    # Update fields
    for field, value in update_data.items():
        setattr(brand, field, value)

    await db.commit()
    await db.refresh(brand)

    return BrandResponse.model_validate(brand)


@router.post("/{brand_id}/logo", response_model=BrandResponse)
async def upload_brand_logo(
    brand_id: int,
    file: UploadFile = File(...),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> BrandResponse:
    """Upload brand logo. Allowed for brand employees and admins."""
    import uuid
    from pathlib import Path

    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise_error(404, ERR_BRAND_NOT_FOUND)

    is_admin = current_user.role == UserRole.ADMIN
    is_employee = await can_edit_brand_catalog(db, current_user, brand_id)
    if not is_admin and not is_employee:
        raise_error(403, ERR_NO_PERMISSION)

    allowed_ext = BRAND_LOGO_ALLOWED_EXTENSIONS
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in allowed_ext:
        raise_error(
            400,
            ERR_FILE_EXT_NOT_ALLOWED,
            {"ext": file_ext, "allowed": ", ".join(sorted(allowed_ext))},
        )

    content = await file.read()
    max_size = 2 * 1024 * 1024
    if len(content) > max_size:
        raise_error(
            400,
            ERR_FILE_SIZE_EXCEEDED,
            {"size_mb": f"{len(content) / (1024*1024):.2f}", "max_mb": "2"},
        )
    content, stored_ext = normalize_brand_logo_upload(content, file_ext)

    base_upload_dir = get_upload_root_dir()
    logo_dir = base_upload_dir / "brand_logos"
    logo_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{brand_id}_{uuid.uuid4().hex[:8]}{stored_ext}"
    file_path = (logo_dir / file_name).resolve()

    if not str(file_path).startswith(str(logo_dir.resolve())):
        raise_error(400, ERR_INVALID_FILE_PATH)

    with open(file_path, "wb") as f:
        f.write(content)

    brand.logo_url = f"/uploads/brand_logos/{file_name}"
    await db.commit()
    await db.refresh(brand)

    return BrandResponse.model_validate(brand)


@router.delete("/{brand_id}", status_code=204)
async def delete_brand(
    brand_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> None:
    """Удалить производителя."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise_error(404, ERR_BRAND_NOT_FOUND)

    await db.delete(brand)
    await db.commit()


