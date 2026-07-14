"""Admin endpoints for moderation and verification."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin_user
from app.core.errors import (
    ERR_ARTICLE_NOT_FOUND,
    ERR_BANNED_WORD_EXISTS,
    ERR_BANNED_WORD_NOT_FOUND,
    ERR_BRAND_ID_REQUIRED_JOIN,
    ERR_BRAND_NAME_SLUG_REQUIRED,
    ERR_BRAND_NOT_FOUND,
    ERR_BRAND_REQUEST_NOT_FOUND,
    ERR_BRAND_SLUG_EXISTS,
    ERR_DATA_REQUIRED,
    ERR_DB_IMPORT_ERROR,
    ERR_DUMP_NOT_FOUND,
    ERR_FILE_EXT_NOT_ALLOWED,
    ERR_FILE_SIZE_EXCEEDED,
    ERR_FILE_TOO_LARGE,
    ERR_FILENAME_REQUIRED,
    ERR_INVALID_BADGES,
    ERR_INVALID_FILE_EXT,
    ERR_INVALID_FILE_PATH,
    ERR_INVALID_FILENAME,
    ERR_NO_ACTIVE_USERS_FOUND,
    ERR_PRESET_NOT_FOUND,
    ERR_PRIMARY_KEY_REQUIRED,
    ERR_PRINTER_NOT_FOUND,
    ERR_PRINTER_REQUEST_NOT_FOUND,
    ERR_PRINTER_SLUG_EXISTS,
    ERR_REQUEST_NOT_PENDING,
    ERR_TABLE_DATA_ERROR,
    ERR_TABLE_DELETE_ERROR,
    ERR_TABLE_NOT_FOUND,
    ERR_TABLE_STRUCTURE_ERROR,
    ERR_TABLE_UPDATE_ERROR,
    ERR_USER_ALREADY_IN_BRAND,
    ERR_USER_IDS_EMPTY,
    ERR_USER_NOT_FOUND,
    ERR_USER_NOT_IN_BRAND,
    raise_error,
)
from app.core.utils import like_pattern
from app.db.session import get_db

# BadWord импортируется лениво в функциях, где используется
from app.models.brand import Brand
from app.models.brand_request import BrandRequest, BrandRequestStatus
from app.models.notification import NotificationType
from app.models.preset import Preset, PresetModerationStatus
from app.models.printer import Printer
from app.models.printer_request import PrinterRequest, PrinterRequestStatus
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.schemas.bad_word import BadWordCreate, BadWordListResponse, BadWordResponse, BadWordUpdate
from app.schemas.brand import BrandListResponse, BrandResponse, BrandUpdate
from app.schemas.brand_request import (
    BrandRequestListResponse,
    BrandRequestResponse,
    BrandRequestUpdate,
)
from app.schemas.database import (
    DatabaseDumpDeleteResponse,
    DatabaseDumpInfo,
    DatabaseDumpListResponse,
    DatabaseExportRequest,
    DatabaseExportResponse,
    DatabaseImportResponse,
    DatabaseIntegrityResponse,
    DatabaseStatsResponse,
    MigrationApplyRequest,
    MigrationApplyResponse,
    MigrationHistoryResponse,
    MigrationStampRequest,
    MigrationStampResponse,
    RecreateTablesResponse,
    TableDataResponse,
    TableDataUpdateRequest,
    TableStructureResponse,
)
from app.schemas.preset import PresetResponse
from app.schemas.printer import PrinterCreate, PrinterResponse, PrinterUpdate
from app.schemas.printer_request import (
    PrinterRequestListResponse,
    PrinterRequestResponse,
    PrinterRequestUpdate,
)
from app.schemas.user import UserResponse
from app.services.database_service import (
    apply_migration as apply_migration_service,
)
from app.services.database_service import (
    delete_database_dump as delete_database_dump_service,
)
from app.services.database_service import (
    downgrade_migration as downgrade_migration_service,
)
from app.services.database_service import (
    export_database as export_database_service,
)
from app.services.database_service import (
    get_database_stats as get_database_stats_service,
)
from app.services.database_service import (
    get_migration_history as get_migration_history_service,
)
from app.services.database_service import (
    get_table_data as get_table_data_service,
)
from app.services.database_service import (
    get_table_structure as get_table_structure_service,
)
from app.services.database_service import (
    import_database as import_database_service,
)
from app.services.database_service import (
    list_database_dumps as list_database_dumps_service,
)
from app.services.database_service import (
    recreate_missing_tables as recreate_missing_tables_service,
)
from app.services.database_service import (
    stamp_migration as stamp_migration_service,
)
from app.services.database_service import (
    validate_migration_integrity as validate_migration_integrity_service,
)
from app.services.file_service import (
    BRAND_LOGO_ALLOWED_EXTENSIONS,
    get_upload_root_dir,
    normalize_brand_logo_upload,
)
from app.services.maintenance_service import (
    get_maintenance_info,
    set_maintenance_mode,
)
from app.services.notification_service import (
    notify_all_users,
    notify_brand_request_approved,
    notify_brand_request_rejected,
    notify_brand_verified,
)
from app.services.organization_access import grant_brand_owner_membership
from app.services.qr_service import backfill_brand_qr_codes
from app.services.subscription_service import (
    get_or_create_subscription,
    paywall_enforced,
    set_paywall_enforced,
    set_trial_days,
    trial_days,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ==================== Brand Verification ====================


@router.get("/brands", response_model=BrandListResponse)
async def list_brands_admin(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    verified: bool | None = Query(None, description="Фильтр по верификации (True/False/None=все)"),
    active_only: bool = Query(True),
    search: str | None = Query(None, description="Поиск по названию бренда"),
) -> BrandListResponse:
    """Получить список всех брендов (для админа) с фильтрацией и пагинацией."""

    # Build query
    query = select(Brand)

    # Active filter
    if active_only:
        query = query.where(Brand.active == True)

    # Verified filter
    if verified is not None:
        query = query.where(Brand.verified == verified)

    # Search filter
    if search:
        search_term = like_pattern(search)
        query = query.where(Brand.name.ilike(search_term))

    # Count total
    count_query = select(func.count()).select_from(Brand)
    if active_only:
        count_query = count_query.where(Brand.active == True)
    if verified is not None:
        count_query = count_query.where(Brand.verified == verified)
    if search:
        search_term = like_pattern(search)
        count_query = count_query.where(Brand.name.ilike(search_term))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(Brand.created_at.desc())

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


@router.post("/brands/{brand_id}/verify", response_model=BrandResponse)
async def verify_brand(
    brand_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandResponse:
    """Верифицировать бренд (производителя)."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)

    brand.verified = True
    # Бэкофилл QR для материалов, созданных до верификации (юзерами или брендом).
    await backfill_brand_qr_codes(brand, db)
    await db.commit()
    await db.refresh(brand)

    # Создаем уведомления для всех пользователей, связанных с этим брендом
    try:
        users_result = await db.execute(
            select(User).where(User.brand_id == brand.id)
        )
        users = users_result.scalars().all()

        for user in users:
            try:
                await notify_brand_verified(
                    user_id=user.id,
                    brand_name=brand.name,
                    brand_id=brand.id,
                    db=db,
                )
            except Exception as e:
                logger.error(f"Failed to create notification for user {user.id} (brand {brand.id}): {e}")
    except Exception as e:
        logger.error(f"Failed to create notifications for brand {brand.id} verification: {e}")

    return BrandResponse.model_validate(brand)


@router.post("/brands/{brand_id}/unverify", response_model=BrandResponse)
async def unverify_brand(
    brand_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandResponse:
    """Отозвать верификацию бренда."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)

    brand.verified = False
    await db.commit()
    await db.refresh(brand)

    return BrandResponse.model_validate(brand)


@router.patch("/brands/{brand_id}", response_model=BrandResponse)
async def update_brand_admin(
    brand_id: int,
    data: BrandUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandResponse:
    """Обновить бренд (только для админа)."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()

    if not brand:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)

    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    update_data = data.model_dump(exclude_unset=True)

    if "name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["name"], db, "brand_name")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    if "description" in update_data and update_data["description"]:
        is_valid, error_msg = await validate_text_field(update_data["description"], db, "brand_description")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    # Проверка уникальности slug, если он изменяется
    if "slug" in update_data and update_data["slug"] != brand.slug:
        existing_brand = await db.execute(
            select(Brand).where(Brand.slug == update_data["slug"]).where(Brand.id != brand_id)
        )
        if existing_brand.scalar_one_or_none():
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_BRAND_SLUG_EXISTS)

    # Update fields
    for field, value in update_data.items():
        setattr(brand, field, value)

    await db.commit()
    await db.refresh(brand)

    return BrandResponse.model_validate(brand)


@router.post("/brands/{brand_id}/logo", response_model=BrandResponse)
async def upload_brand_logo(
    brand_id: int,
    file: UploadFile = File(...),
    admin: Annotated[User, Depends(get_current_admin_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> BrandResponse:
    """Upload brand logo image."""
    import uuid
    from pathlib import Path

    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)

    # Validate extension
    allowed_ext = BRAND_LOGO_ALLOWED_EXTENSIONS
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in allowed_ext:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ERR_FILE_EXT_NOT_ALLOWED,
            {"ext": file_ext, "allowed": ", ".join(sorted(allowed_ext))},
        )

    # Read and validate size (max 2 MB)
    content = await file.read()
    max_size = 2 * 1024 * 1024
    if len(content) > max_size:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ERR_FILE_SIZE_EXCEEDED,
            {"size_mb": f"{len(content) / (1024*1024):.2f}", "max_mb": "2"},
        )
    content, stored_ext = normalize_brand_logo_upload(content, file_ext)

    # Save file
    base_upload_dir = get_upload_root_dir()
    logo_dir = base_upload_dir / "brand_logos"
    logo_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{brand_id}_{uuid.uuid4().hex[:8]}{stored_ext}"
    file_path = (logo_dir / file_name).resolve()

    if not str(file_path).startswith(str(logo_dir.resolve())):
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FILE_PATH)

    with open(file_path, "wb") as f:
        f.write(content)

    # Update brand logo_url
    brand.logo_url = f"/uploads/brand_logos/{file_name}"
    await db.commit()
    await db.refresh(brand)

    return BrandResponse.model_validate(brand)


# ==================== Preset Moderation ====================


@router.get("/presets/pending", response_model=list[PresetResponse])
async def list_pending_presets(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
) -> list[PresetResponse]:
    """Получить список пресетов, ожидающих модерации."""
    offset = (page - 1) * size

    result = await db.execute(
        select(Preset)
        .where(
            Preset.moderation_status == PresetModerationStatus.PENDING,
            Preset.is_official == False,  # Только пользовательские
            Preset.active == True,
        )
        .order_by(Preset.created_at)
        .offset(offset)
        .limit(size)
    )
    presets = result.scalars().all()

    return [PresetResponse.model_validate(preset) for preset in presets]


@router.post("/presets/{preset_id}/approve", response_model=PresetResponse)
async def approve_preset(
    preset_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PresetResponse:
    """Одобрить пресет."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRESET_NOT_FOUND)

    preset.moderation_status = PresetModerationStatus.APPROVED
    preset.moderated_by = admin.id
    preset.moderated_at = datetime.utcnow()
    preset.moderation_reason = None

    await db.commit()
    await db.refresh(preset)

    return PresetResponse.model_validate(preset)


@router.post("/presets/{preset_id}/reject", response_model=PresetResponse)
async def reject_preset(
    preset_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    reason: str = Query(..., description="Причина отклонения"),
) -> PresetResponse:
    """Отклонить пресет с указанием причины."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_PRESET_NOT_FOUND)

    preset.moderation_status = PresetModerationStatus.REJECTED
    preset.moderated_by = admin.id
    preset.moderated_at = datetime.utcnow()
    preset.moderation_reason = reason
    preset.active = False  # Отклоненные не показываем

    await db.commit()
    await db.refresh(preset)

    return PresetResponse.model_validate(preset)


# ==================== User Management ====================


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    role: UserRole | None = Query(None, description="Фильтр по роли (user/admin)"),
    active_only: bool = Query(True),
    with_brand: bool | None = Query(None, description="Фильтр по привязке к бренду (True=только с брендом, False=только без бренда)"),
) -> list[UserResponse]:
    """Получить список пользователей."""
    from sqlalchemy.orm import selectinload

    query = select(User).options(selectinload(User.brand), selectinload(User.subscription))

    if active_only:
        query = query.where(User.active == True)
    if role:
        query = query.where(User.role == role)
    if with_brand is not None:
        if with_brand:
            query = query.where(User.brand_id.isnot(None))
        else:
            query = query.where(User.brand_id.is_(None))

    offset = (page - 1) * size
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset(offset).limit(size)
    )
    users = result.scalars().all()

    items = []
    for user in users:
        response = UserResponse.model_validate(user)
        # Добавляем название бренда если есть
        if user.brand_id and user.brand:
            response.brand_name = user.brand.name  # type: ignore
        items.append(response)

    return items


@router.post("/users/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Активировать пользователя."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

    user.active = True
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Деактивировать пользователя."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

    user.active = False
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/promote-admin", response_model=UserResponse)
async def promote_to_admin(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Назначить пользователя администратором."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

    # Админ может оставаться привязанным к бренду, поэтому brand_id не обнуляем
    user.role = UserRole.ADMIN
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/demote-to-user", response_model=UserResponse)
async def demote_to_user(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Изменить роль пользователя на USER."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

    # Меняем только роль, привязка к бренду остается без изменений
    user.role = UserRole.USER
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/link-brand", response_model=UserResponse)
async def link_user_to_brand(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    brand_id: int = Query(..., description="ID бренда для привязки"),
) -> UserResponse:
    """Привязать пользователя к бренду."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

    if user.brand_id:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_USER_ALREADY_IN_BRAND)

    # Проверяем существование бренда
    brand_result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = brand_result.scalar_one_or_none()

    if not brand:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)

    # Привязываем к бренду (роль не меняем)
    user.brand_id = brand_id
    await db.commit()

    # Загружаем пользователя с брендом для корректной сериализации
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.brand))
    )
    user = result.scalar_one()

    response = UserResponse.model_validate(user)
    if user.brand:
        response.brand_name = user.brand.name  # type: ignore

    return response


@router.post("/users/{user_id}/unlink-brand", response_model=UserResponse)
async def unlink_user_from_brand(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Отвязать пользователя от бренда."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

    if not user.brand_id:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_USER_NOT_IN_BRAND)

    # Отвязываем от бренда (роль не меняем)
    user.brand_id = None
    await db.commit()

    # Загружаем пользователя с брендом для корректной сериализации
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.brand))
    )
    user = result.scalar_one()

    response = UserResponse.model_validate(user)
    if user.brand:
        response.brand_name = user.brand.name  # type: ignore

    return response


@router.get("/stats", response_model=dict)
async def get_admin_stats(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Получить расширенную статистику для админки."""
    from datetime import timedelta

    from app.models.filament import Filament
    from app.models.filament_review import FilamentReview
    from app.models.notification import Notification
    from app.models.preset_gate_state import PresetGateState
    from app.models.printer_profile import PrinterProfile
    from app.models.sync_device import SyncDevice
    from app.models.user_printer_device import UserPrinterDevice
    from app.models.user_spool import UserSpool
    from app.models.wiki_article import WikiArticle

    # Use naive UTC datetimes — all timestamp columns are TIMESTAMP WITHOUT TIME ZONE
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # --- Users ---
    users_total = await db.scalar(select(func.count(User.id)))
    users_brands = await db.scalar(select(func.count(User.id)).where(User.brand_id.isnot(None)))
    users_admins = await db.scalar(select(func.count(User.id)).where(User.role == UserRole.ADMIN))
    users_24h = await db.scalar(
        select(func.count(User.id)).where(User.created_at >= day_ago)
    )
    users_7d = await db.scalar(
        select(func.count(User.id)).where(User.created_at >= week_ago)
    )
    users_30d = await db.scalar(
        select(func.count(User.id)).where(User.created_at >= month_ago)
    )
    users_active_24h = await db.scalar(
        select(func.count(User.id)).where(User.last_login >= day_ago)
    )
    users_active_7d = await db.scalar(
        select(func.count(User.id)).where(User.last_login >= week_ago)
    )

    # --- Brands ---
    brands_total = await db.scalar(select(func.count(Brand.id)))
    brands_verified = await db.scalar(select(func.count(Brand.id)).where(Brand.verified == True))
    brands_pending = await db.scalar(select(func.count(Brand.id)).where(Brand.verified == False))

    # --- Presets ---
    presets_total = await db.scalar(select(func.count(Preset.id)))
    presets_pending = await db.scalar(
        select(func.count(Preset.id)).where(Preset.moderation_status == PresetModerationStatus.PENDING)
    )
    presets_approved = await db.scalar(
        select(func.count(Preset.id)).where(Preset.moderation_status == PresetModerationStatus.APPROVED)
    )
    presets_rejected = await db.scalar(
        select(func.count(Preset.id)).where(Preset.moderation_status == PresetModerationStatus.REJECTED)
    )

    # --- Filaments ---
    filaments_total = await db.scalar(select(func.count(Filament.id)))

    # --- Reviews ---
    reviews_total = await db.scalar(select(func.count(FilamentReview.id)))
    reviews_7d = await db.scalar(
        select(func.count(FilamentReview.id)).where(FilamentReview.created_at >= week_ago)
    )

    # --- Printers & Profiles ---
    printers_total = await db.scalar(select(func.count(Printer.id)))
    printer_profiles_total = await db.scalar(select(func.count(PrinterProfile.id)))

    # --- Devices (user's physical printers) ---
    devices_total = await db.scalar(select(func.count(UserPrinterDevice.id)))

    # --- Spools ---
    spools_total = await db.scalar(select(func.count(UserSpool.id)))

    # --- Gate states (slot assignments) ---
    gates_total = await db.scalar(select(func.count(PresetGateState.id)))
    gates_with_preset = await db.scalar(
        select(func.count(PresetGateState.id)).where(PresetGateState.preset_id.isnot(None))
    )

    # --- Sync devices (OrcaSlicer installations) ---
    sync_devices_total = await db.scalar(select(func.count(SyncDevice.id)))
    sync_devices_active_7d = await db.scalar(
        select(func.count(SyncDevice.id)).where(SyncDevice.last_sync_at >= week_ago)
    )

    # --- Wiki ---
    wiki_articles = await db.scalar(select(func.count(WikiArticle.id)))

    # --- Notifications ---
    notifications_unread = await db.scalar(
        select(func.count(Notification.id)).where(Notification.read == False)
    )

    return {
        "users": {
            "total": users_total or 0,
            "brands": users_brands or 0,
            "admins": users_admins or 0,
            "registered_24h": users_24h or 0,
            "registered_7d": users_7d or 0,
            "registered_30d": users_30d or 0,
            "active_24h": users_active_24h or 0,
            "active_7d": users_active_7d or 0,
        },
        "brands": {
            "total": brands_total or 0,
            "verified": brands_verified or 0,
            "pending_verification": brands_pending or 0,
        },
        "presets": {
            "total": presets_total or 0,
            "pending_moderation": presets_pending or 0,
            "approved": presets_approved or 0,
            "rejected": presets_rejected or 0,
        },
        "content": {
            "filaments": filaments_total or 0,
            "printers": printers_total or 0,
            "printer_profiles": printer_profiles_total or 0,
            "reviews_total": reviews_total or 0,
            "reviews_7d": reviews_7d or 0,
            "wiki_articles": wiki_articles or 0,
        },
        "hardware": {
            "devices": devices_total or 0,
            "spools": spools_total or 0,
            "gate_slots": gates_total or 0,
            "gate_slots_assigned": gates_with_preset or 0,
            "sync_devices": sync_devices_total or 0,
            "sync_devices_active_7d": sync_devices_active_7d or 0,
        },
        "notifications": {
            "unread": notifications_unread or 0,
        },
    }


# ==================== Admin Settings (Redis) ====================

ADMIN_SETTINGS_PREFIX = "admin:settings:"


async def _get_redis():
    import redis.asyncio as aioredis

    from app.core.config import settings as cfg
    return aioredis.from_url(cfg.REDIS_URL, decode_responses=True)


@router.get("/settings/{key}")
async def get_admin_setting(
    key: str,
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Get an admin setting from Redis."""
    r = await _get_redis()
    val = await r.get(f"{ADMIN_SETTINGS_PREFIX}{key}")
    await r.aclose()
    return {"key": key, "value": val}


@router.put("/settings/{key}")
async def set_admin_setting(
    key: str,
    admin: Annotated[User, Depends(get_current_admin_user)],
    body: dict = Body(...),
) -> dict:
    """Save an admin setting to Redis."""
    r = await _get_redis()
    val = body.get("value", "")
    if val:
        await r.set(f"{ADMIN_SETTINGS_PREFIX}{key}", str(val))
    else:
        await r.delete(f"{ADMIN_SETTINGS_PREFIX}{key}")
    await r.aclose()
    return {"key": key, "value": val}


# ==================== Docker Stats ====================


@router.get("/docker-stats")
async def get_docker_stats(
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Get Docker container metrics (on-demand, not cached)."""
    import asyncio
    import json

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "stats", "--no-stream", "--format",
            '{"name":"{{.Name}}","cpu":"{{.CPUPerc}}","mem_usage":"{{.MemUsage}}","mem_perc":"{{.MemPerc}}","net_io":"{{.NetIO}}","block_io":"{{.BlockIO}}","pids":"{{.PIDs}}"}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

        if proc.returncode != 0:
            logger.warning("docker stats failed: %s", stderr.decode())
            return {"containers": [], "error": "Docker stats unavailable"}

        containers = []
        for line in stdout.decode().strip().split("\n"):
            if line.strip():
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # Get restart counts via docker inspect
        for c in containers:
            try:
                insp = await asyncio.create_subprocess_exec(
                    "docker", "inspect", "--format",
                    '{{.RestartCount}} {{.State.Status}}',
                    c["name"],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out, _ = await asyncio.wait_for(insp.communicate(), timeout=5)
                parts = out.decode().strip().split(" ", 1)
                c["restart_count"] = int(parts[0]) if parts[0].isdigit() else 0
                c["status"] = parts[1] if len(parts) > 1 else "unknown"
            except Exception:
                c["restart_count"] = 0
                c["status"] = "unknown"

        return {"containers": containers}

    except asyncio.TimeoutError:
        return {"containers": [], "error": "Docker stats timeout"}
    except FileNotFoundError:
        return {"containers": [], "error": "Docker CLI not available"}
    except Exception as e:
        logger.warning("Docker stats error: %s", e, exc_info=True)
        return {"containers": [], "error": "Docker stats unavailable"}


# ==================== Brand Requests ====================


@router.get("/brand-requests", response_model=BrandRequestListResponse)
async def list_brand_requests(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    status: BrandRequestStatus | None = Query(None),
) -> BrandRequestListResponse:
    """Получить список всех заявок на верификацию брендов."""

    from sqlalchemy.orm import selectinload

    query = select(BrandRequest).options(
        selectinload(BrandRequest.user),
        selectinload(BrandRequest.brand)
    )
    if status:
        query = query.where(BrandRequest.status == status)

    # Count total
    count_query = select(func.count()).select_from(BrandRequest)
    if status:
        count_query = count_query.where(BrandRequest.status == status)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(BrandRequest.created_at.desc())

    # Execute
    result = await db.execute(query)
    requests = result.scalars().all()

    items = []
    for req in requests:
        response = BrandRequestResponse.model_validate(req)
        # Добавляем email пользователя
        if req.user:
            response.user_email = req.user.email
        # Добавляем название бренда для JOIN заявок
        if req.brand_id and req.brand:
            response.brand_name = req.brand.name
        # Файлы уже парсятся через валидатор в схеме, конвертация выполняется автоматически
        if req.social_media_urls and not response.social_media_urls:
            import json
            try:
                response.social_media_urls = json.loads(req.social_media_urls)
            except (json.JSONDecodeError, TypeError):
                response.social_media_urls = []
        items.append(response)

    return BrandRequestListResponse(
        items=items,
        total=total,
    )


@router.get("/brand-requests/{id}", response_model=BrandRequestResponse)
async def get_brand_request(
    id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandRequestResponse:
    """Получить заявку на верификацию бренда по ID."""

    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(BrandRequest)
        .where(BrandRequest.id == id)
        .options(
            selectinload(BrandRequest.user),
            selectinload(BrandRequest.brand)
        )
    )
    request = result.scalar_one_or_none()

    if not request:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_REQUEST_NOT_FOUND)

    response = BrandRequestResponse.model_validate(request)
    # Добавляем email пользователя
    if request.user:
        response.user_email = request.user.email
    # Добавляем название бренда для JOIN заявок
    if request.brand_id and request.brand:
        response.brand_name = request.brand.name
    # Убедимся, что файлы и соцсети правильно распарсены
    if request.proof_files and not response.proof_files:
        from app.services.file_service import parse_proof_files
        response.proof_files = parse_proof_files(request.proof_files)
    if request.social_media_urls and not response.social_media_urls:
        import json
        try:
            response.social_media_urls = json.loads(request.social_media_urls)
        except (json.JSONDecodeError, TypeError):
            response.social_media_urls = []
    return response


@router.patch("/brand-requests/{id}", response_model=BrandRequestResponse)
async def update_brand_request(
    id: int,
    data: BrandRequestUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandRequestResponse:
    """Обновить статус заявки на верификацию бренда (одобрить/отклонить)."""

    from sqlalchemy.orm import selectinload

    from app.models.brand_request import BrandRequestType

    result = await db.execute(
        select(BrandRequest)
        .where(BrandRequest.id == id)
        .options(selectinload(BrandRequest.user), selectinload(BrandRequest.brand))
    )
    request = result.scalar_one_or_none()

    if not request:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_REQUEST_NOT_FOUND)

    if request.status != BrandRequestStatus.PENDING:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_REQUEST_NOT_PENDING)

    # Обновляем статус
    request.status = data.status
    request.processed_by_id = admin.id
    request.processed_at = datetime.utcnow()

    if data.rejection_reason:
        request.rejection_reason = data.rejection_reason

    # Если одобряем заявку
    if data.status == BrandRequestStatus.APPROVED:
        user = request.user
        if not user:
            raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

        # Просто привязываем к бренду, роль не меняем (админ может быть привязан к бренду, но оставаться админом)

        if request.request_type == BrandRequestType.JOIN:
            # Для JOIN: привязываем пользователя к существующему бренду
            if not request.brand_id:
                raise_error(status.HTTP_400_BAD_REQUEST, ERR_BRAND_ID_REQUIRED_JOIN
                )
            brand = request.brand or await db.get(Brand, request.brand_id)
            if not brand:
                raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)
            if not brand.verified:
                brand.name_correction_available = True
            brand.verified = True
            await grant_brand_owner_membership(
                db,
                brand=brand,
                user=user,
                granted_by_id=admin.id,
            )
            await backfill_brand_qr_codes(brand, db)

        elif request.request_type == BrandRequestType.CREATE:
            # Для CREATE: создаем новый бренд и привязываем пользователя
            if not request.new_brand_name or not request.new_brand_slug:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": ERR_BRAND_NAME_SLUG_REQUIRED},
                )

            # Проверяем, что бренд еще не создан
            existing_brand = await db.execute(
                select(Brand).where(Brand.slug == request.new_brand_slug)
            )
            if existing_brand.scalar_one_or_none():
                raise_error(status.HTTP_400_BAD_REQUEST, ERR_BRAND_SLUG_EXISTS)

            # Создаем новый бренд
            new_brand = Brand(
                name=request.new_brand_name,
                slug=request.new_brand_slug,
                description=request.new_brand_description,
                website=request.new_brand_website,
                verified=True,  # Автоматически верифицируем после одобрения админом
                name_correction_available=True,
                active=True,
            )
            db.add(new_brand)
            await db.flush()  # Получаем ID бренда

            await grant_brand_owner_membership(
                db,
                brand=new_brand,
                user=user,
                granted_by_id=admin.id,
            )

    await db.commit()
    await db.refresh(request)

    # Создаем уведомления для пользователя
    if request.user_id:
        try:
            if data.status == BrandRequestStatus.APPROVED:
                # Определяем brand_id для уведомления
                brand_id_for_notification = None
                if request.request_type == BrandRequestType.JOIN and request.brand_id:
                    brand_id_for_notification = request.brand_id
                elif request.request_type == BrandRequestType.CREATE:
                    # После flush() new_brand.id уже доступен
                    if request.request_type == BrandRequestType.CREATE:
                        brand_result = await db.execute(
                            select(Brand).where(Brand.slug == request.new_brand_slug)
                        )
                        created_brand = brand_result.scalar_one_or_none()
                        if created_brand:
                            brand_id_for_notification = created_brand.id

                brand_name = request.brand.name if request.brand else (request.new_brand_name or "brand")
                if brand_id_for_notification:
                    await notify_brand_request_approved(
                        user_id=request.user_id,
                        brand_name=brand_name,
                        brand_id=brand_id_for_notification,
                        db=db,
                    )
            elif data.status == BrandRequestStatus.REJECTED:
                brand_name = request.brand.name if request.brand else (request.new_brand_name or "brand")
                await notify_brand_request_rejected(
                    user_id=request.user_id,
                    brand_name=brand_name,
                    reason=data.rejection_reason,
                    db=db,
                )
        except Exception as e:
            logger.error(f"Failed to create notification for brand request {request.id}: {e}")

    response = BrandRequestResponse.model_validate(request)
    # Добавляем email пользователя
    if request.user:
        response.user_email = request.user.email
    # Убедимся, что файлы и соцсети правильно распарсены
    if request.proof_files and not response.proof_files:
        from app.services.file_service import parse_proof_files
        response.proof_files = parse_proof_files(request.proof_files)
    if request.social_media_urls and not response.social_media_urls:
        import json
        try:
            response.social_media_urls = json.loads(request.social_media_urls)
        except (json.JSONDecodeError, TypeError):
            response.social_media_urls = []
    return response


@router.delete("/brand-requests/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand_request(
    id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Удалить заявку на верификацию бренда (только для админа). Удаляет также все связанные файлы."""

    from sqlalchemy.orm import selectinload

    from app.services.file_service import delete_proof_files

    result = await db.execute(
        select(BrandRequest)
        .where(BrandRequest.id == id)
        .options(selectinload(BrandRequest.user))
    )
    request = result.scalar_one_or_none()

    if not request:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_REQUEST_NOT_FOUND)

    # Удаляем все файлы связанные с заявкой
    if request.proof_files:
        await delete_proof_files(request.proof_files)

    # Удаляем заявку из базы
    await db.delete(request)
    await db.commit()

    return None


# ==================== Printer Management ====================


@router.post("/printers", response_model=PrinterResponse, status_code=201)
async def create_printer_admin(
    data: PrinterCreate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterResponse:
    """Создать принтер (admin only)."""
    # Проверяем уникальность slug
    slug_result = await db.execute(select(Printer).where(Printer.slug == data.slug))
    existing = slug_result.scalar_one_or_none()

    if existing:
        raise_error(400, ERR_PRINTER_SLUG_EXISTS)

    # Create printer
    printer = Printer(**data.model_dump())
    db.add(printer)
    await db.commit()
    await db.refresh(printer)

    return PrinterResponse.model_validate(printer)


@router.patch("/printers/{printer_id}", response_model=PrinterResponse)
async def update_printer_admin(
    printer_id: int,
    data: PrinterUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterResponse:
    """Обновить принтер (admin only)."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()

    if not printer:
        raise_error(404, ERR_PRINTER_NOT_FOUND)

    # Проверяем уникальность slug если он обновляется
    if data.slug and data.slug != printer.slug:
        slug_result = await db.execute(select(Printer).where(Printer.slug == data.slug))
        existing = slug_result.scalar_one_or_none()
        if existing:
            raise_error(400, ERR_PRINTER_SLUG_EXISTS)

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(printer, field, value)

    await db.commit()
    await db.refresh(printer)

    return PrinterResponse.model_validate(printer)


@router.delete("/printers/{printer_id}", status_code=204)
async def delete_printer_admin(
    printer_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Удалить принтер (admin only)."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()

    if not printer:
        raise_error(404, ERR_PRINTER_NOT_FOUND)

    await db.delete(printer)
    await db.commit()


# ==================== Printer Request Management ====================


@router.get("/printer-requests", response_model=PrinterRequestListResponse)
async def list_printer_requests_admin(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    status: PrinterRequestStatus | None = Query(None, description="Фильтр по статусу"),
) -> PrinterRequestListResponse:
    """Получить список запросов на добавление принтеров (для админа) с пагинацией."""
    from sqlalchemy.orm import selectinload

    # Build query
    query = select(PrinterRequest).options(selectinload(PrinterRequest.user))

    if status:
        query = query.where(PrinterRequest.status == status)

    # Count total
    count_query = select(func.count()).select_from(PrinterRequest)
    if status:
        count_query = count_query.where(PrinterRequest.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(PrinterRequest.created_at.desc())

    # Execute
    result = await db.execute(query)
    requests = result.scalars().all()

    items = []
    for req in requests:
        try:
            response = PrinterRequestResponse.model_validate(req)
            # Добавляем email пользователя
            if req.user:
                response.user_email = req.user.email
            # Парсим файлы если они есть
            if req.proof_files:
                from app.services.file_service import parse_proof_files
                response.proof_files = parse_proof_files(req.proof_files)
            else:
                # Убеждаемся, что proof_files установлен в None или пустой список
                response.proof_files = None
            items.append(response)
        except Exception as e:
            # Логируем ошибку валидации для отладки
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error validating PrinterRequest {req.id}: {e}")
            # Пропускаем проблемную запись или возвращаем базовые данные
            continue

    return PrinterRequestListResponse(
        items=items,
        total=total,
    )


@router.get("/printer-requests/{request_id}", response_model=PrinterRequestResponse)
async def get_printer_request_admin(
    request_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterRequestResponse:
    """Получить запрос на добавление принтера по ID (для админа)."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(PrinterRequest)
        .where(PrinterRequest.id == request_id)
        .options(selectinload(PrinterRequest.user))
    )
    printer_request = result.scalar_one_or_none()

    if not printer_request:
        raise_error(404, ERR_PRINTER_REQUEST_NOT_FOUND)

    response = PrinterRequestResponse.model_validate(printer_request)
    # Добавляем email пользователя
    if printer_request.user:
        response.user_email = printer_request.user.email
    if printer_request.proof_files:
        from app.services.file_service import parse_proof_files
        response.proof_files = parse_proof_files(printer_request.proof_files)
    return response


@router.patch("/printer-requests/{request_id}", response_model=PrinterRequestResponse)
async def update_printer_request_admin(
    request_id: int,
    data: PrinterRequestUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterRequestResponse:
    """Обновить статус запроса на добавление принтера (approve/reject)."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(PrinterRequest)
        .where(PrinterRequest.id == request_id)
        .options(selectinload(PrinterRequest.user))
    )
    request = result.scalar_one_or_none()

    if not request:
        raise_error(404, ERR_PRINTER_REQUEST_NOT_FOUND)

    # Если одобряем запрос, создаём принтер
    if data.status == PrinterRequestStatus.APPROVED:
        # Проверяем, что принтер ещё не создан
        printer_result = await db.execute(select(Printer).where(Printer.slug == request.slug))
        existing_printer = printer_result.scalar_one_or_none()

        if existing_printer:
            raise_error(400, ERR_PRINTER_SLUG_EXISTS)

        # Создаём принтер из данных запроса
        printer = Printer(
            name=request.name,
            manufacturer=request.manufacturer,
            model=request.model,
            slug=request.slug,
            description=request.description,
            build_volume_x=request.build_volume_x,
            build_volume_y=request.build_volume_y,
            build_volume_z=request.build_volume_z,
            nozzle_diameter=request.nozzle_diameter,
            max_extruder_temp=request.max_extruder_temp,
            max_bed_temp=request.max_bed_temp,
            image_url=request.image_url,
            active=True,
        )
        db.add(printer)
        await db.flush()  # Получаем ID принтера

    # Обновляем статус запроса
    request.status = data.status
    request.processed_by_id = admin.id
    request.processed_at = datetime.now()
    if data.rejection_reason:
        request.rejection_reason = data.rejection_reason

    await db.commit()
    await db.refresh(request)

    response = PrinterRequestResponse.model_validate(request)
    # Добавляем email пользователя
    if request.user:
        response.user_email = request.user.email
    if request.proof_files:
        from app.services.file_service import parse_proof_files
        response.proof_files = parse_proof_files(request.proof_files)
    return response


# ==================== Database Management ====================


@router.get("/database/migrations", response_model=MigrationHistoryResponse)
async def get_migration_history(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MigrationHistoryResponse:
    """Получить историю миграций Alembic."""
    history = await get_migration_history_service(db)
    return MigrationHistoryResponse(**history)


@router.post("/database/migrations/apply", response_model=MigrationApplyResponse)
async def apply_migration(
    data: MigrationApplyRequest,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: AsyncSession = Depends(get_db),
) -> MigrationApplyResponse:
    """Применить миграцию Alembic с валидацией и записью в историю."""
    applied_by = f"{admin.email} ({admin.id})"
    success, message, current_revision, validation_errors = await apply_migration_service(data.revision, applied_by=applied_by)
    return MigrationApplyResponse(
        success=success,
        message=message,
        current_revision=current_revision,
        validation_errors=validation_errors,
    )


@router.post("/database/migrations/downgrade", response_model=MigrationApplyResponse)
async def downgrade_migration(
    data: MigrationApplyRequest,
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> MigrationApplyResponse:
    """Откатить миграцию Alembic с записью в историю."""
    downgraded_by = f"{admin.email} ({admin.id})"
    success, message, current_revision = await downgrade_migration_service(data.revision, downgraded_by=downgraded_by)
    return MigrationApplyResponse(
        success=success,
        message=message,
        current_revision=current_revision,
    )


@router.post("/database/migrations/stamp", response_model=MigrationStampResponse)
async def stamp_migration(
    data: MigrationStampRequest,
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> MigrationStampResponse:
    """
    Пометить миграцию как применённую БЕЗ выполнения SQL.

    Используйте когда:
    - Миграция частично применилась (например, enum создан, но таблица нет)
    - Нужно синхронизировать состояние alembic_version с реальной БД
    - БД была настроена вручную и нужно пометить миграции

    ВНИМАНИЕ: Это НЕ выполняет SQL из миграции, только обновляет alembic_version.
    """
    stamped_by = f"{admin.email} ({admin.id})"
    success, message, current_revision = await stamp_migration_service(data.revision, stamped_by=stamped_by)
    return MigrationStampResponse(
        success=success,
        message=message,
        current_revision=current_revision,
    )


@router.get("/database/stats", response_model=DatabaseStatsResponse)
async def get_database_stats(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DatabaseStatsResponse:
    """Получить статистику базы данных."""
    stats = await get_database_stats_service(db)
    return DatabaseStatsResponse(**stats)


@router.post("/database/export", response_model=DatabaseExportResponse)
async def export_database(
    data: DatabaseExportRequest,
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> DatabaseExportResponse:
    """Экспортировать базу данных."""
    success, message, filename, size = await export_database_service(
        format=data.format,
        include_data=data.include_data,
        tables=data.tables,
    )

    download_url = None
    if success and filename:
        # Формируем полный URL для скачивания
        # В продакшене нужно использовать settings.BACKEND_URL или определять из запроса
        download_url = f"/api/v1/admin/database/download/{filename}"

    return DatabaseExportResponse(
        success=success,
        message=message,
        filename=filename,
        download_url=download_url,
        size=size,
    )


@router.get("/database/download/{filename}")
async def download_database_dump(
    filename: str,
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> FileResponse:
    """Скачать файл дампа базы данных."""
    from pathlib import Path

    from app.core.config import settings

    if '/' in filename or '\\' in filename or '..' in filename:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FILENAME)

    dump_file = Path(settings.UPLOAD_DIR) / "database_dumps" / filename

    if not dump_file.exists():
        raise_error(status.HTTP_404_NOT_FOUND, ERR_DUMP_NOT_FOUND)

    return FileResponse(
        path=str(dump_file),
        filename=filename,
        media_type="application/octet-stream",
    )


@router.post("/database/import", response_model=DatabaseImportResponse)
async def import_database(
    admin: Annotated[User, Depends(get_current_admin_user)],
    file: UploadFile = File(...),
    format: str = Query("custom", description="Формат импорта: custom, plain, tar"),
    clean: bool = Query(False, description="Очистить базу перед импортом"),
    create: bool = Query(False, description="Создать базу если не существует"),
) -> DatabaseImportResponse:
    """Импортировать базу данных из файла дампа."""
    from pathlib import Path

    from app.core.config import settings

    # Валидация файла
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": ERR_FILENAME_REQUIRED},
        )

    # Проверяем расширение файла
    valid_extensions = {
        'custom': ['.dump'],
        'plain': ['.sql'],
        'tar': ['.tar'],
    }
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in valid_extensions.get(format, []):
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FILE_EXT, {"ext": file_ext, "expected": ", ".join(valid_extensions.get(format, []))})

    # Проверяем размер файла (максимум 1GB)
    MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_FILE_TOO_LARGE, {"max_size": "1GB"})

    # Сохраняем загруженный файл
    dumps_dir = (Path(settings.UPLOAD_DIR) / "database_dumps").resolve()
    dumps_dir.mkdir(parents=True, exist_ok=True)

    # Never include the client-supplied filename in a filesystem path. Keep only
    # the validated extension and generate the storage name server-side.
    import uuid

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{uuid.uuid4().hex}{file_ext}"
    filepath = (dumps_dir / safe_filename).resolve()
    if not filepath.is_relative_to(dumps_dir):
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FILE_PATH)

    with open(filepath, "wb") as f:
        f.write(content)

    # Импортируем базу данных
    logger.info(f"Начинаем импорт базы данных: файл={safe_filename}, формат={format}, clean={clean}, create={create}")
    try:
        success, message = await import_database_service(
            filepath=safe_filename,
            format=format,
            clean=clean,
            create=create,
        )
        logger.info(f"Импорт завершён: success={success}, message={message}")
    except Exception as e:
        logger.error(f"Ошибка при импорте базы данных: {e}", exc_info=True)
        # Удаляем временный файл при ошибке
        if filepath.exists():
            filepath.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": ERR_DB_IMPORT_ERROR},
        ) from e

    # Удаляем временный файл после импорта
    if filepath.exists():
        filepath.unlink()

    return DatabaseImportResponse(
        success=success,
        message=message,
    )


@router.get("/database/dumps", response_model=DatabaseDumpListResponse)
async def list_database_dumps(
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> DatabaseDumpListResponse:
    """Получить список всех дампов базы данных."""
    dumps = await list_database_dumps_service()
    return DatabaseDumpListResponse(dumps=[DatabaseDumpInfo(**dump) for dump in dumps])


@router.delete("/database/dumps/{filename}", response_model=DatabaseDumpDeleteResponse)
async def delete_database_dump(
    filename: str,
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> DatabaseDumpDeleteResponse:
    """Удалить файл дампа базы данных."""
    # Безопасность: проверяем, что filename не содержит путь
    if '/' in filename or '\\' in filename or '..' in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": ERR_INVALID_FILENAME},
        )

    success, message = await delete_database_dump_service(filename)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=message,
        )

    return DatabaseDumpDeleteResponse(success=success, message=message)


@router.get("/database/tables/{table_name}/structure", response_model=TableStructureResponse)
async def get_table_structure(
    table_name: str,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    schema_name: str = Query("public", description="Имя схемы"),
) -> TableStructureResponse:
    """Получить структуру таблицы (колонки, индексы, ограничения)."""
    try:
        structure = await get_table_structure_service(db, table_name, schema_name)
        return TableStructureResponse(**structure)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": ERR_TABLE_STRUCTURE_ERROR},
        ) from e


@router.get("/database/integrity", response_model=DatabaseIntegrityResponse)
async def check_database_integrity(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: AsyncSession = Depends(get_db),
) -> DatabaseIntegrityResponse:
    """Проверить целостность базы данных."""
    is_valid, missing_tables = await validate_migration_integrity_service(db)

    if is_valid:
        message = "database_ok"
    else:
        message = f"database_missing_tables: {', '.join(missing_tables)}"

    return DatabaseIntegrityResponse(
        is_valid=is_valid,
        missing_tables=missing_tables,
        message=message,
    )


@router.post("/database/recreate-tables", response_model=RecreateTablesResponse)
async def recreate_tables(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: AsyncSession = Depends(get_db),
) -> RecreateTablesResponse:
    """Восстановить все недостающие таблицы на основе моделей SQLAlchemy."""
    success, message, created_tables = await recreate_missing_tables_service(db)

    return RecreateTablesResponse(
        success=success,
        message=message,
        created_tables=created_tables,
    )


@router.get("/database/tables/{table_name}/data", response_model=TableDataResponse)
async def get_table_data(
    table_name: str,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    schema_name: str = Query("public", description="Имя схемы"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    size: int = Query(50, ge=1, le=1000, description="Размер страницы"),
    order_by: Optional[str] = Query(None, description="Колонка для сортировки"),
    order_desc: bool = Query(False, description="Сортировка по убыванию"),
    search: Optional[str] = Query(None, description="Поиск по всем колонкам"),
) -> TableDataResponse:
    """Получить данные из таблицы с пагинацией."""
    try:
        table_data = await get_table_data_service(
            db,
            table_name=table_name,
            schema_name=schema_name,
            page=page,
            size=size,
            order_by=order_by,
            order_desc=order_desc,
            search=search,
        )
        return TableDataResponse(**table_data)
    except ValueError:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_TABLE_NOT_FOUND)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": ERR_TABLE_DATA_ERROR},
        ) from e


@router.patch("/database/tables/{table_name}/data", response_model=dict)
async def update_table_data(
    table_name: str,
    request: TableDataUpdateRequest,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    schema_name: str = Query("public", description="Имя схемы"),
) -> dict:
    """Обновить данные в таблице."""
    from app.services.database_service import (
        update_table_row_service as update_table_row_service_func,
    )

    try:
        primary_key = request.primary_key
        update_data = request.data

        if not primary_key:
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_PRIMARY_KEY_REQUIRED)

        if not update_data:
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_DATA_REQUIRED)

        success, message = await update_table_row_service_func(
            db,
            table_name=table_name,
            schema_name=schema_name,
            primary_key=primary_key,
            update_data=update_data,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message,
            )

        return {"success": True, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": ERR_TABLE_UPDATE_ERROR},
        ) from e


@router.delete("/database/tables/{table_name}/data", response_model=dict)
async def delete_table_data(
    table_name: str,
    primary_key: dict[str, Any] = Body(..., description="Значения первичного ключа для идентификации строки"),
    admin: Annotated[User, Depends(get_current_admin_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    schema_name: str = Query("public", description="Имя схемы"),
) -> dict:
    """Удалить строку из таблицы."""
    from app.services.database_service import delete_table_row_service

    try:
        if not primary_key:
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_PRIMARY_KEY_REQUIRED)

        success, message = await delete_table_row_service(
            db,
            table_name=table_name,
            schema_name=schema_name,
            primary_key=primary_key,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message,
            )

        return {"success": True, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": ERR_TABLE_DELETE_ERROR},
        ) from e


# ==================== Bad Words Management ====================


@router.get("/bad-words", response_model=BadWordListResponse)
async def list_bad_words(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    language: str | None = Query(None, description="Фильтр по языку (ru, en)"),
    search: str | None = Query(None, description="Поиск по слову"),
) -> BadWordListResponse:
    """Получить список запрещенных слов."""
    # Ленивый импорт, чтобы не падать при отсутствии таблицы
    from app.models.bad_word import BadWord

    query = select(BadWord)

    # Language filter
    if language:
        query = query.where(BadWord.language == language)

    # Search filter
    if search:
        search_term = like_pattern(search)
        query = query.where(BadWord.word.ilike(search_term))

    # Count total
    count_query = select(func.count()).select_from(BadWord)
    if language:
        count_query = count_query.where(BadWord.language == language)
    if search:
        search_term = like_pattern(search)
        count_query = count_query.where(BadWord.word.ilike(search_term))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(BadWord.word)

    # Execute
    result = await db.execute(query)
    words = result.scalars().all()

    pages = (total + size - 1) // size if total > 0 else 0

    return BadWordListResponse(
        items=[BadWordResponse.model_validate(word) for word in words],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.post("/bad-words", response_model=BadWordResponse, status_code=status.HTTP_201_CREATED)
async def create_bad_word(
    data: BadWordCreate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BadWordResponse:
    """Добавить запрещенное слово."""
    # Ленивый импорт, чтобы не падать при отсутствии таблицы
    from app.models.bad_word import BadWord

    # Проверяем, существует ли уже такое слово
    result = await db.execute(
        select(BadWord).where(
            BadWord.word.ilike(data.word.lower()),
            BadWord.language == data.language,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_BANNED_WORD_EXISTS, {"word": data.word, "language": data.language})

    bad_word = BadWord(word=data.word.lower(), language=data.language)
    db.add(bad_word)
    await db.commit()
    await db.refresh(bad_word)

    # Сбрасываем кэш в сервисе модерации
    from app.services.preset_moderation import _BAD_WORDS_CACHE
    _BAD_WORDS_CACHE.clear()

    return BadWordResponse.model_validate(bad_word)


@router.get("/bad-words/{word_id}", response_model=BadWordResponse)
async def get_bad_word(
    word_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BadWordResponse:
    # Ленивый импорт, чтобы не падать при отсутствии таблицы
    from app.models.bad_word import BadWord
    """Получить информацию о запрещенном слове."""
    result = await db.execute(select(BadWord).where(BadWord.id == word_id))
    word = result.scalar_one_or_none()

    if not word:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BANNED_WORD_NOT_FOUND)

    return BadWordResponse.model_validate(word)


@router.patch("/bad-words/{word_id}", response_model=BadWordResponse)
async def update_bad_word(
    word_id: int,
    data: BadWordUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BadWordResponse:
    """Обновить запрещенное слово."""
    # Ленивый импорт, чтобы не падать при отсутствии таблицы
    from app.models.bad_word import BadWord

    result = await db.execute(select(BadWord).where(BadWord.id == word_id))
    word = result.scalar_one_or_none()

    if not word:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BANNED_WORD_NOT_FOUND)

    # Проверяем уникальность, если меняем слово или язык
    update_data = data.model_dump(exclude_unset=True)

    if "word" in update_data or "language" in update_data:
        new_word = update_data.get("word", word.word).lower()
        new_language = update_data.get("language", word.language)

        # Проверяем, не существует ли уже такое слово
        check_result = await db.execute(
            select(BadWord).where(
                BadWord.word.ilike(new_word),
                BadWord.language == new_language,
                BadWord.id != word_id,
            )
        )
        existing = check_result.scalar_one_or_none()

        if existing:
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_BANNED_WORD_EXISTS, {"word": new_word, "language": new_language})

    # Обновляем поля
    for field, value in update_data.items():
        if field == "word":
            setattr(word, field, value.lower())
        else:
            setattr(word, field, value)

    await db.commit()
    await db.refresh(word)

    # Сбрасываем кэш в сервисе модерации
    from app.services.preset_moderation import _BAD_WORDS_CACHE
    _BAD_WORDS_CACHE.clear()

    return BadWordResponse.model_validate(word)


@router.delete("/bad-words/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bad_word(
    word_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Удалить запрещенное слово."""
    # Ленивый импорт, чтобы не падать при отсутствии таблицы
    from app.models.bad_word import BadWord

    result = await db.execute(select(BadWord).where(BadWord.id == word_id))
    word = result.scalar_one_or_none()

    if not word:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BANNED_WORD_NOT_FOUND)

    await db.delete(word)
    await db.commit()

    # Сбрасываем кэш в сервисе модерации
    from app.services.preset_moderation import _BAD_WORDS_CACHE
    _BAD_WORDS_CACHE.clear()


# ==================== Notifications ====================


@router.post("/notifications/broadcast", response_model=dict)
async def broadcast_notification(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    title: str = Body(..., description="Заголовок сообщения"),
    message: str = Body(..., description="Текст сообщения"),
    link: str | None = Body(None, description="Ссылка (опционально)"),
    active_only: bool = Body(True, description="Отправлять только активным пользователям"),
) -> dict:
    """
    Массовая рассылка уведомлений всем пользователям (только для админов).

    Создает уведомление типа ADMIN_MESSAGE для всех активных пользователей.
    """
    count = await notify_all_users(
        notification_type=NotificationType.ADMIN_MESSAGE,
        title=title,
        message=message,
        db=db,
        link=link,
        active_only=active_only,
    )

    logger.info(f"Admin {admin.id} sent broadcast notification to {count} users. Title: {title}")

    return {
        "success": True,
        "message": "notification_sent",
        "count": count,
    }


@router.post("/notifications/send", response_model=dict)
async def send_notification_to_users(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_ids: list[int] = Body(..., description="Список ID пользователей для отправки"),
    title: str = Body(..., description="Заголовок сообщения"),
    message: str = Body(..., description="Текст сообщения"),
    link: str | None = Body(None, description="Ссылка (опционально)"),
) -> dict:
    """
    Отправить уведомление конкретным пользователям (только для админов).

    Создает уведомление типа ADMIN_MESSAGE для указанных пользователей.
    """
    if not user_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": ERR_USER_IDS_EMPTY},
        )

    # Проверяем, что пользователи существуют и активны
    existing_users = await db.execute(
        select(User.id).where(User.id.in_(user_ids), User.active == True)
    )
    valid_user_ids = list(existing_users.scalars().all())

    if not valid_user_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": ERR_NO_ACTIVE_USERS_FOUND},
        )

    from app.services.notification_service import create_bulk_notifications

    count = await create_bulk_notifications(
        user_ids=valid_user_ids,
        notification_type=NotificationType.ADMIN_MESSAGE,
        title=title,
        message=message,
        db=db,
        link=link,
    )

    logger.info(f"Admin {admin.id} sent notification to {count} users (IDs: {valid_user_ids}). Title: {title}")

    return {
        "success": True,
        "message": "notification_sent",
        "count": count,
        "sent_to": valid_user_ids,
    }


@router.patch(
    "/users/{user_id}/badges",
    response_model=dict,
    summary="Управление бейджами пользователя",
    description="Добавить или удалить бейджи пользователя. Доступные бейджи: founder, beta_tester, contributor, verified, early_adopter, supporter",
)
async def manage_user_badges(
    user_id: int,
    badges: list[str] = Body(..., description="Список бейджей пользователя"),
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Управление бейджами пользователя (только для администраторов).

    Доступные бейджи:
    - founder: Основатель (первые пользователи)
    - beta_tester: Бета-тестер
    - contributor: Контрибьютор (помог с разработкой)
    - verified: Верифицированный (производитель)
    - early_adopter: Ранний последователь
    - supporter: Поддержал проект
    """
    # Валидация бейджей
    valid_badges = {"founder", "beta_tester", "contributor", "verified", "early_adopter", "supporter"}
    invalid_badges = [b for b in badges if b not in valid_badges]

    if invalid_badges:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_BADGES, {"invalid": ", ".join(invalid_badges), "valid": ", ".join(valid_badges)})

    # Получаем пользователя
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

    # Обновляем бейджи
    old_badges = user.badges or []
    user.badges = badges if badges else None
    await db.commit()
    await db.refresh(user)

    logger.info(
        f"Admin {admin.id} updated badges for user {user_id} "
        f"(from {old_badges} to {badges})"
    )

    return {
        "success": True,
        "message": "badges_updated",
        "user_id": user_id,
        "badges": user.badges,
    }


# ============================================================================
# Maintenance Mode (Технические работы)
# ============================================================================

@router.get("/maintenance", response_model=dict)
async def get_maintenance_status(
    admin: User = Depends(get_current_admin_user),
) -> dict:
    """
    Получить текущий статус режима технических работ.
    Доступно только администраторам.
    """
    return get_maintenance_info()


@router.post("/maintenance", response_model=dict)
async def set_maintenance_status(
    enabled: bool = Body(..., description="Включить или выключить технические работы"),
    message: Optional[str] = Body(None, description="Сообщение для пользователей"),
    admin: User = Depends(get_current_admin_user),
) -> dict:
    """
    Установить режим технических работ.
    Доступно только администраторам.

    Когда включен режим технических работ:
    - Все запросы к API (кроме /health и /api/v1/admin/maintenance) возвращают 503
    - Фронтенд должен показывать сообщение о технических работах
    """
    set_maintenance_mode(enabled, message)

    logger.info(
        f"Admin {admin.id} {'enabled' if enabled else 'disabled'} maintenance mode"
        + (f" with message: {message}" if message else "")
    )

    return {
        "success": True,
        "message": "maintenance_mode_updated",
        "maintenance_mode": get_maintenance_info(),
    }


# ============================================================================
# Calculator Pro / subscriptions
# ============================================================================

@router.patch("/users/{user_id}/pro-access", response_model=UserResponse)
async def set_user_pro_access(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    grant: bool = Body(..., embed=True, description="Выдать (true) / отозвать (false) комплиментарный Pro"),
) -> UserResponse:
    """Выдать/отозвать комплиментарный (ручной, без оплаты) Pro-доступ к калькулятору."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(User).options(selectinload(User.subscription)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

    sub = await get_or_create_subscription(db, user)
    if grant:
        sub.status = SubscriptionStatus.ACTIVE
        sub.is_comp = True
        sub.current_period_end = None  # complimentary — never expires
    else:
        # Revoking a complimentary grant must revoke access, not silently start
        # or restore an unlimited trial.
        sub.status = SubscriptionStatus.EXPIRED
        sub.is_comp = False
        sub.current_period_end = None
    await db.commit()
    await db.refresh(user, attribute_names=["subscription"])

    logger.info(f"Admin {admin.id} {'granted' if grant else 'revoked'} comp Pro for user {user_id}")
    return UserResponse.model_validate(user)


@router.get("/calculator-settings", response_model=dict)
async def get_calculator_settings(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Настройки калькулятора: платный доступ, длина триала (дней; null = бессрочно) + счётчики подписок."""
    trialing = await db.scalar(
        select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.TRIALING)
    )
    active = await db.scalar(
        select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.ACTIVE)
    )
    return {
        "paywall_enforced": paywall_enforced(),
        "trial_days": trial_days(),
        "counts": {"trialing": trialing or 0, "active": active or 0},
    }


@router.post("/calculator-settings", response_model=dict)
async def update_calculator_settings(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    paywall_enforced_value: bool = Body(..., alias="paywall_enforced", embed=True),
    trial_days_value: int | None = Body(None, alias="trial_days", embed=True),
) -> dict:
    """Изменить глобальные настройки калькулятора (рубильник пейволла + длина триала)."""
    await set_paywall_enforced(db, paywall_enforced_value)
    await set_trial_days(db, trial_days_value)
    logger.info(
        f"Admin {admin.id} set calculator settings: paywall_enforced={paywall_enforced_value}, "
        f"trial_days={trial_days_value}"
    )
    return {"paywall_enforced": paywall_enforced(), "trial_days": trial_days()}


# ==================== Wiki Sync ====================


@router.post("/wiki/sync", response_model=dict)
async def sync_wiki_from_files(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Синхронизировать Wiki из markdown файлов.

    Читает все .md файлы из backend/wiki_content/ и обновляет/создаёт статьи в БД.
    - Новые статьи создаются
    - Существующие статьи обновляются (по slug)
    - Файлы без нужных метаданных пропускаются

    Формат .md файла:
    ```
    ---
    title: "Заголовок статьи"
    category: beginners
    slug: article-slug
    tags: ["тег1", "тег2"]
    status: published
    ---
    # Контент статьи в Markdown
    ```
    """
    from app.services.wiki_sync_service import sync_wiki_from_markdown

    result = await sync_wiki_from_markdown(db)

    logger.info(
        f"Admin {admin.id} synced wiki: {result['created']} created, "
        f"{result['updated']} updated, {result['errors']} errors"
    )

    return result


@router.post("/wiki/export", response_model=dict)
async def export_wiki_to_files(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Экспортировать все Wiki статьи из БД в .md файлы на сервере.

    Сохраняет файлы в backend/wiki_content/{category_slug}/{slug}.md
    с восстановлением frontmatter.
    """
    from app.services.wiki_sync_service import export_articles_to_markdown

    result = await export_articles_to_markdown(db)

    logger.info(
        f"Admin {admin.id} exported wiki: {result['exported']} files, "
        f"{result['errors']} errors"
    )

    return result


@router.get("/wiki/export/{article_id}")
async def export_wiki_article(
    article_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    """Скачать одну Wiki статью как .md файл."""
    import tempfile

    from app.services.wiki_sync_service import export_article_to_markdown

    filename, content = await export_article_to_markdown(db, article_id)

    if not filename or not content:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_ARTICLE_NOT_FOUND)

    # Write to temp file for FileResponse
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    tmp.write(content)
    tmp.close()

    return FileResponse(
        path=tmp.name,
        filename=filename,
        media_type="text/markdown",
    )


@router.post("/presets/enrich-all", response_model=dict)
async def enrich_all_draft_presets(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Batch enrich all unenriched draft presets with material defaults."""
    from app.services.preset_enrichment_service import enrich_drafts_batch

    stats = await enrich_drafts_batch(db)
    await db.commit()
    return stats


# ─── Printer catalog: data sources ────────────────────────────────────────
#
# The FilamentHub printer catalog can be populated from multiple external
# sources (OrcaSlicer profiles today; PrusaSlicer / Cura / Bambu Studio in
# the future). Each source ships a pre-packed bundle inside the backend
# container under backend/data/catalog_sources/<source>/bundle.zip and an
# admin endpoint that unpacks + imports it idempotently.

# From .../backend/app/api/v1/endpoints/admin.py:
#   parents[3] = backend/app  (WRONG — that's where I was looking before)
#   parents[4] = backend       (CORRECT — bundle lives under backend/data/...)
_CATALOG_SOURCES_DIR = Path(__file__).resolve().parents[4] / "data" / "catalog_sources"
_ORCA_BUNDLE_PATH = _CATALOG_SOURCES_DIR / "orca" / "bundle.zip"


@router.get("/catalog/sources/orca/info", response_model=dict)
async def get_catalog_source_orca_info(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return state of the OrcaSlicer catalog source bundle and current catalog."""
    bundle_exists = _ORCA_BUNDLE_PATH.exists()
    bundle_size_mb: float | None = None
    bundle_vendor_count: int | None = None
    if bundle_exists:
        bundle_size_mb = round(_ORCA_BUNDLE_PATH.stat().st_size / 1024 / 1024, 2)
        import zipfile as _zip
        with _zip.ZipFile(_ORCA_BUNDLE_PATH) as zf:
            # Vendor manifests are top-level *.json (no slash in name)
            bundle_vendor_count = sum(
                1 for n in zf.namelist() if n.endswith(".json") and "/" not in n
            )

    printers_total = await db.scalar(select(func.count(Printer.id)))
    printers_system = await db.scalar(
        select(func.count(Printer.id)).where(Printer.source == "system")
    )

    return {
        "bundle": {
            "exists": bundle_exists,
            "path": str(_ORCA_BUNDLE_PATH),
            "size_mb": bundle_size_mb,
            "vendor_count": bundle_vendor_count,
        },
        "catalog": {
            "printers_total": printers_total or 0,
            "printers_system": printers_system or 0,
        },
    }


@router.post("/catalog/sources/orca/import", response_model=dict)
async def import_catalog_source_orca(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Deprecated alias — wraps BundleService for the system OrcaSlicer bundle.

    Kept for the existing AdminCatalogSources UI button. New uploads should
    use POST /api/v1/admin/catalog/bundles. This endpoint reuses an existing
    Bundle row when the system bundle hasn't changed (same sha256) so repeated
    clicks don't fail with ERR_BUNDLE_DUPLICATE.
    """
    import hashlib

    from app.models.bundle import Bundle, BundleSource
    from app.services.bundle_service import BundleService, BundleServiceError

    if not _ORCA_BUNDLE_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ERR_BUNDLE_NOT_FOUND", "params": {"path": str(_ORCA_BUNDLE_PATH)}},
        )

    file_bytes = _ORCA_BUNDLE_PATH.read_bytes()
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    service = BundleService(db)
    existing = await db.scalar(select(Bundle).where(Bundle.sha256 == sha256))
    try:
        if existing is None:
            bundle = await service.upload(
                file_bytes=file_bytes,
                filename=_ORCA_BUNDLE_PATH.name,
                source=BundleSource.ORCA,
                uploaded_by_user_id=admin.id,
            )
        else:
            bundle = existing
            # Make sure validation_summary is fresh for the preview UI.
            await service.revalidate(bundle.id)

        audit = await service.import_bundle(
            bundle_id=bundle.id, triggered_by_user_id=admin.id
        )
        await db.commit()
        summary = audit.summary or {}
    except BundleServiceError as exc:
        await db.commit()  # persist audit row created before failure
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT
            if exc.code == "ERR_BUNDLE_NOT_VALIDATED"
            else status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": exc.code, "params": exc.params},
        ) from exc

    printers_total = await db.scalar(select(func.count(Printer.id)))
    printers_system = await db.scalar(
        select(func.count(Printer.id)).where(Printer.source == "system")
    )

    return {
        "summary": summary,
        "bundle_id": bundle.id,
        "catalog": {
            "printers_total": printers_total or 0,
            "printers_system": printers_system or 0,
        },
    }

