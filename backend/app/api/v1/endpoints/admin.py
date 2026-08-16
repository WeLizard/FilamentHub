"""Admin endpoints for moderation and verification."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin_user
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_ARTICLE_NOT_FOUND,
    ERR_BANNED_WORD_EXISTS,
    ERR_BANNED_WORD_NOT_FOUND,
    ERR_BRAND_ID_REQUIRED_JOIN,
    ERR_BRAND_NAME_SLUG_REQUIRED,
    ERR_BRAND_NOT_FOUND,
    ERR_BRAND_REQUEST_NOT_FOUND,
    ERR_BRAND_SLUG_EXISTS,
    ERR_BRAND_SLUG_INVALID,
    ERR_BRAND_SLUG_RENAME_REQUIRED,
    ERR_BRAND_SLUG_STALE,
    ERR_DATABASE_DUMP_NOT_FOUND,
    ERR_DATABASE_EXPORT_FAILED,
    ERR_FILE_EXT_NOT_ALLOWED,
    ERR_FILE_SIZE_EXCEEDED,
    ERR_INVALID_BADGES,
    ERR_INVALID_FILE_PATH,
    ERR_NOTIFICATION_PREVIEW_REQUIRED,
    ERR_ORCA_SCHEMA_OBSERVATION_NOT_FOUND,
    ERR_PRESET_FILAMENT_REQUIRED,
    ERR_PRESET_NOT_FOUND,
    ERR_PRINTER_NOT_FOUND,
    ERR_PRINTER_REQUEST_NOT_FOUND,
    ERR_PRINTER_SLUG_EXISTS,
    ERR_REQUEST_NOT_PENDING,
    ERR_TABLE_STRUCTURE_ERROR,
    ERR_USER_NOT_FOUND,
    ERR_USER_NOT_IN_BRAND,
    raise_error,
)
from app.core.utils import like_pattern
from app.db.session import get_db

# BadWord импортируется лениво в функциях, где используется
from app.models.brand import Brand
from app.models.brand_request import BrandRequest, BrandRequestStatus
from app.models.brand_territorial_grant import GrantSource
from app.models.email_communication import EmailThread
from app.models.feedback import Feedback, FeedbackStatus
from app.models.orca_schema_observation import OrcaSchemaObservation
from app.models.organization import OrganizationMemberRole, OrganizationMembership
from app.models.preset import Preset, PresetModerationStatus
from app.models.printer import Printer
from app.models.printer_request import PrinterRequest, PrinterRequestStatus
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.schemas.bad_word import BadWordCreate, BadWordListResponse, BadWordResponse, BadWordUpdate
from app.schemas.brand import BrandListResponse, BrandResponse, BrandSlugRename, BrandUpdate
from app.schemas.brand_request import (
    BrandRequestListResponse,
    BrandRequestResponse,
    BrandRequestUpdate,
)
from app.schemas.calculator import (
    CalculatorCountryDefaultsMap,
    CalculatorProfileDefaults,
)
from app.schemas.database import (
    DatabaseExportRequest,
    DatabaseIntegrityResponse,
    DatabaseStatsResponse,
    MigrationHistoryResponse,
    TableStructureResponse,
)
from app.schemas.orca_schema_observation import (
    OrcaSchemaObservationListResponse,
    OrcaSchemaObservationResponse,
    OrcaSchemaObservationUpdate,
)
from app.schemas.preset import PresetResponse
from app.schemas.printer import PrinterCreate, PrinterResponse, PrinterUpdate
from app.schemas.printer_request import (
    PrinterRequestListResponse,
    PrinterRequestResponse,
    PrinterRequestUpdate,
)
from app.schemas.user import AccountDeletionStats, UserListResponse, UserResponse
from app.services.brand_slug_service import apply_brand_slug_rename, choose_brand_slug
from app.services.calculator_defaults_service import (
    get_calculator_profile_defaults,
    get_calculator_country_defaults,
    set_calculator_country_defaults,
    set_calculator_profile_defaults,
)
from app.services.database_service import (
    get_database_stats as get_database_stats_service,
)
from app.services.database_service import (
    get_migration_history as get_migration_history_service,
)
from app.services.database_service import (
    get_table_structure as get_table_structure_service,
)
from app.services.database_service import (
    validate_migration_integrity as validate_migration_integrity_service,
)
from app.services.file_service import (
    BRAND_LOGO_ALLOWED_EXTENSIONS,
    get_upload_root_dir,
    normalize_brand_logo_upload,
)
from app.services.grant_issuing import issue_territorial_grant, settle_territorial_application
from app.services.maintenance_service import (
    get_maintenance_info,
    set_maintenance_mode,
)
from app.services.notification_service import (
    notify_brand_request_approved,
    notify_brand_request_rejected,
    notify_brand_verified,
)
from app.services.orca_field_registry import ORCA_FIELD_REGISTRY_VERSION
from app.services.orca_schema_observer import prune_known_orca_schema_observations
from app.services.organization_access import (
    grant_brand_editor_membership,
    grant_brand_owner_membership,
    revoke_brand_membership,
)
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


@router.get(
    "/orca-schema-observations",
    response_model=OrcaSchemaObservationListResponse,
)
async def list_orca_schema_observations(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    observation_status: Literal["new", "reviewed"] | None = Query(
        None, alias="status"
    ),
    scope: Literal["filament", "process", "machine"] | None = Query(None),
    search: str | None = Query(None, max_length=200),
) -> OrcaSchemaObservationListResponse:
    """List aggregated unknown OrcaSlicer preset fields for admin review."""

    if await prune_known_orca_schema_observations(db):
        await db.commit()

    filters = []
    if observation_status is not None:
        filters.append(OrcaSchemaObservation.status == observation_status)
    if scope is not None:
        filters.append(OrcaSchemaObservation.scope == scope)
    if search:
        filters.append(OrcaSchemaObservation.field_name.ilike(like_pattern(search)))

    total = await db.scalar(select(func.count(OrcaSchemaObservation.id)).where(*filters))
    new_count = await db.scalar(
        select(func.count(OrcaSchemaObservation.id)).where(OrcaSchemaObservation.status == "new")
    )
    query = (
        select(OrcaSchemaObservation)
        .where(*filters)
        .order_by(
            (OrcaSchemaObservation.status == "new").desc(),
            OrcaSchemaObservation.last_seen_at.desc(),
            OrcaSchemaObservation.id.desc(),
        )
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(query)
    items = result.scalars().all()
    total_value = total or 0
    return OrcaSchemaObservationListResponse(
        items=[OrcaSchemaObservationResponse.model_validate(item) for item in items],
        total=total_value,
        new_count=new_count or 0,
        page=page,
        size=size,
        pages=(total_value + size - 1) // size if total_value else 0,
        registry_version=ORCA_FIELD_REGISTRY_VERSION,
    )


@router.patch(
    "/orca-schema-observations/{observation_id}",
    response_model=OrcaSchemaObservationResponse,
)
async def update_orca_schema_observation(
    observation_id: int,
    payload: OrcaSchemaObservationUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrcaSchemaObservationResponse:
    """Mark one observed field as reviewed or return it to new."""

    observation = await db.get(OrcaSchemaObservation, observation_id)
    if observation is None:
        raise_error(
            status.HTTP_404_NOT_FOUND,
            ERR_ORCA_SCHEMA_OBSERVATION_NOT_FOUND,
            {"observation_id": observation_id},
        )
    observation.status = payload.status
    if payload.status == "new":
        observation.reviewed_at = None
        observation.reviewed_by_user_id = None
    else:
        observation.reviewed_at = datetime.now(timezone.utc)
        observation.reviewed_by_user_id = admin.id
    await db.commit()
    await db.refresh(observation)
    return OrcaSchemaObservationResponse.model_validate(observation)


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

    requested_slug = update_data.get("slug")
    if requested_slug is not None and requested_slug != brand.slug:
        raise_error(status.HTTP_409_CONFLICT, ERR_BRAND_SLUG_RENAME_REQUIRED)
    update_data.pop("slug", None)

    if "name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["name"], db, "brand_name")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    if "description" in update_data and update_data["description"]:
        is_valid, error_msg = await validate_text_field(update_data["description"], db, "brand_description")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    # Update fields
    for field, value in update_data.items():
        setattr(brand, field, value)

    await db.commit()
    await db.refresh(brand)

    return BrandResponse.model_validate(brand)


@router.post("/brands/{brand_id}/slug", response_model=BrandResponse)
async def rename_brand_slug_admin(
    brand_id: int,
    data: BrandSlugRename,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandResponse:
    """Rename a published brand URL and preserve the previous slug as an alias."""
    del admin
    brand = await db.scalar(
        select(Brand).where(Brand.id == brand_id).with_for_update()
    )
    if brand is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)
    if data.expected_current_slug != brand.slug:
        raise_error(status.HTTP_409_CONFLICT, ERR_BRAND_SLUG_STALE)

    selected_slug, available = await choose_brand_slug(
        db,
        name=brand.name,
        requested_slug=data.slug,
        exclude_brand_id=brand.id,
    )
    if selected_slug is None:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_BRAND_SLUG_INVALID)
    if not available:
        raise_error(status.HTTP_409_CONFLICT, ERR_BRAND_SLUG_EXISTS)

    try:
        await apply_brand_slug_rename(db, brand=brand, new_slug=selected_slug)
    except ValueError:
        raise_error(status.HTTP_409_CONFLICT, ERR_BRAND_SLUG_EXISTS)
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


@router.get("/communications/unread/count")
async def count_unread_communications(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """Сколько непрочитанного в переписке и обращениях — для метки на вкладке.

    Двумя числами, а не одним: внутри вкладки это разные разделы, и по метке
    должно быть понятно, куда идти.
    """
    del admin
    emails = await db.scalar(
        select(func.coalesce(func.sum(EmailThread.unread_count), 0)).where(
            EmailThread.unread_count > 0
        )
    )
    feedback = await db.scalar(
        select(func.count())
        .select_from(Feedback)
        .where(Feedback.status == FeedbackStatus.OPEN)
    )
    return {"unread_emails": int(emails or 0), "new_feedback": int(feedback or 0)}


# ==================== Preset Moderation ====================


@router.get("/presets/pending/count")
async def count_pending_presets(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """Сколько пресетов ждёт модерации — для метки на вкладке.

    Отдельно от списка: метка рисуется при каждом открытии админки, и тянуть
    ради неё страницу пресетов было бы расточительно.
    """
    del admin
    pending = await db.scalar(
        select(func.count())
        .select_from(Preset)
        .where(
            Preset.moderation_status == PresetModerationStatus.PENDING,
            Preset.is_official == False,
            Preset.active == True,
        )
    )
    return {"pending_count": int(pending or 0)}


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
    if preset.filament_id is None:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_PRESET_FILAMENT_REQUIRED)

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


@router.get("/users", response_model=UserListResponse)
async def list_users(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    role: UserRole | None = Query(None, description="Фильтр по роли (user/admin)"),
    active_only: bool = Query(True),
    with_brand: bool | None = Query(None, description="Фильтр по привязке к бренду (True=только с брендом, False=только без бренда)"),
    search: str | None = Query(None, max_length=200),
) -> UserListResponse:
    """Получить отфильтрованный список пользователей с пагинацией."""
    from sqlalchemy.orm import selectinload

    filters = []
    if active_only:
        filters.append(User.active == True)
    if role:
        filters.append(User.role == role)
    if search and (term := search.strip()):
        pattern = like_pattern(term)
        filters.append(
            or_(
                User.email.ilike(pattern, escape="\\"),
                User.username.ilike(pattern, escape="\\"),
                User.full_name.ilike(pattern, escape="\\"),
            )
        )
    if with_brand is not None:
        if with_brand:
            filters.append(User.brand_id.isnot(None))
        else:
            filters.append(User.brand_id.is_(None))

    total_result = await db.execute(
        select(func.count()).select_from(User).where(*filters)
    )
    total = total_result.scalar_one()

    offset = (page - 1) * size
    query = (
        select(User)
        .options(selectinload(User.brand), selectinload(User.subscription))
        .where(*filters)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    result = await db.execute(query)
    users = result.scalars().all()

    items = []
    for user in users:
        response = UserResponse.model_validate(user)
        # Добавляем название бренда если есть
        if user.brand_id and user.brand:
            response.brand_name = user.brand.name  # type: ignore
        items.append(response)

    return UserListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        total_pages=(total + size - 1) // size if total else 0,
    )


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

    # Проверяем существование бренда
    brand_result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = brand_result.scalar_one_or_none()

    if not brand:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)

    await grant_brand_owner_membership(
        db,
        brand=brand,
        user=user,
        granted_by_id=admin.id,
    )
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

    brand_id = user.brand_id
    if not await revoke_brand_membership(db, user=user, brand_id=brand_id):
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_USER_NOT_IN_BRAND)
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
    refresh: bool = False,
) -> dict:
    """Получить расширенную статистику для админки. refresh=true минует кэш."""
    from app.services.admin_stats_service import get_admin_stats as _admin_stats

    return await _admin_stats(db, force_refresh=refresh)


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

        if request.request_type in (
            BrandRequestType.JOIN,
            BrandRequestType.REPRESENTATIVE,
        ):
            # Для JOIN: привязываем пользователя к существующему бренду
            if not request.brand_id:
                raise_error(status.HTTP_400_BAD_REQUEST, ERR_BRAND_ID_REQUIRED_JOIN
                )
            brand = request.brand or await db.get(Brand, request.brand_id)
            if not brand:
                raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)
            active_owner_exists = False
            if brand.verified and brand.organization_id is not None:
                active_owner_exists = bool(
                    await db.scalar(
                        select(OrganizationMembership.id)
                        .where(
                            OrganizationMembership.organization_id == brand.organization_id,
                            OrganizationMembership.active.is_(True),
                            OrganizationMembership.role == OrganizationMemberRole.OWNER,
                        )
                        .limit(1)
                    )
                )
            if request.request_type == BrandRequestType.REPRESENTATIVE:
                # Документы проверены — марка настоящая, и подтверждает её
                # модерация, а не объём выданного права.
                if not brand.verified:
                    brand.name_correction_available = True
                brand.verified = True
                await backfill_brand_qr_codes(brand, db)
                await settle_territorial_application(
                    db,
                    brand=brand,
                    user=user,
                    country=request.country,
                    organization_name=None,
                    approved_by_id=admin.id,
                )
            elif active_owner_exists:
                # A JOIN request to an already represented brand is a team
                # membership, even when a FilamentHub admin moderates it.
                await grant_brand_editor_membership(
                    db,
                    brand=brand,
                    user=user,
                    granted_by_id=admin.id,
                )
            else:
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
                await db.flush()
                await issue_territorial_grant(
                    db,
                    brand=brand,
                    user=user,
                    country=None,
                    source=GrantSource.application,
                    approved_by_id=admin.id,
                )

        elif request.request_type == BrandRequestType.CREATE:
            # A create request carries what the applicant asked for. Approving it
            # issues that right in the same action: the documents are already
            # reviewed here, and a second moderation round would check the same
            # evidence twice while the applicant waits for an empty record.
            if not request.new_brand_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": ERR_BRAND_NAME_SLUG_REQUIRED},
                )

            selected_slug, available = await choose_brand_slug(
                db,
                name=request.new_brand_name,
                requested_slug=request.new_brand_slug,
            )
            if selected_slug is None:
                raise_error(status.HTTP_400_BAD_REQUEST, ERR_BRAND_SLUG_INVALID)
            if not available:
                raise_error(status.HTTP_400_BAD_REQUEST, ERR_BRAND_SLUG_EXISTS)
            request.new_brand_slug = selected_slug

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

            if request.claim_scope in {"brand", "representative"}:
                await backfill_brand_qr_codes(new_brand, db)
                if request.claim_scope == "representative":
                    await settle_territorial_application(
                        db,
                        brand=new_brand,
                        user=user,
                        country=request.country,
                        organization_name=None,
                        approved_by_id=admin.id,
                    )
                else:
                    await grant_brand_owner_membership(
                        db,
                        brand=new_brand,
                        user=user,
                        granted_by_id=admin.id,
                    )
                    await db.flush()
                    await issue_territorial_grant(
                        db,
                        brand=new_brand,
                        user=user,
                        country=None,
                        source=GrantSource.application,
                        approved_by_id=admin.id,
                    )

    await db.commit()
    await db.refresh(request)

    # Создаем уведомления для пользователя
    if request.user_id:
        try:
            if data.status == BrandRequestStatus.APPROVED:
                # Определяем brand_id для уведомления
                brand_id_for_notification = None
                if request.brand_id:
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


@router.get("/database/stats", response_model=DatabaseStatsResponse)
async def get_database_stats(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DatabaseStatsResponse:
    """Получить статистику базы данных."""
    stats = await get_database_stats_service(db)
    return DatabaseStatsResponse(**stats)


@router.post("/database/export")
async def export_database(
    payload: DatabaseExportRequest,
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Выгрузить базу в файл. Дамп шифруется ключом резервных копий."""
    from app.services.database_service import export_database as export_database_service

    success, message, filename, size = await export_database_service(
        format=payload.format,
        include_data=payload.include_data,
        tables=payload.tables,
    )
    if not success:
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_DATABASE_EXPORT_FAILED)
    logger.info("Admin %s exported the database to %s", admin.id, filename)
    return {
        "success": True,
        "filename": filename,
        "download_url": None,
        "size": size,
        "message": message,
    }


@router.get("/database/dumps")
async def list_database_dumps(
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Список сохранённых дампов."""
    from app.services.database_service import list_database_dumps as list_dumps_service

    return {"dumps": await list_dumps_service()}


@router.delete("/database/dumps/{filename}")
async def delete_database_dump(
    filename: str,
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Удалить дамп."""
    from app.services.database_service import delete_database_dump as delete_dump_service

    success, message = await delete_dump_service(filename)
    if not success:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_DATABASE_DUMP_NOT_FOUND)
    logger.info("Admin %s deleted dump %s", admin.id, filename)
    return {"success": True, "message": message}


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
) -> dict:
    """Reject the retired direct-send route; campaigns require preview and confirmation."""
    del admin
    raise_error(status.HTTP_409_CONFLICT, ERR_NOTIFICATION_PREVIEW_REQUIRED)


@router.post("/notifications/send", response_model=dict)
async def send_notification_to_users(
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Reject the retired direct-send route; campaigns require preview and confirmation."""
    del admin
    raise_error(status.HTTP_409_CONFLICT, ERR_NOTIFICATION_PREVIEW_REQUIRED)


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

@router.get("/users/{user_id}/deletion-preview", response_model=AccountDeletionStats)
async def preview_user_deletion(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccountDeletionStats:
    """Show what disappears with this account before anyone presses delete."""
    del admin
    from app.services.account_deletion import get_deletion_stats

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)
    return AccountDeletionStats(**await get_deletion_stats(user_id, db))


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user_as_admin(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    delete_reviews: bool = Body(
        default=False,
        embed=True,
        description="Удалить отзывы полностью (true) или обезличить их (false)",
    ),
) -> dict[str, bool]:
    """Erase an account on the person's request.

    The law obliges us to delete personal data when asked, and until now the
    panel could only switch an account off — which erases nothing. This runs the
    same routine the person's own profile runs, so related data is handled the
    same way rather than left as broken references.
    """
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)
    if user.id == admin.id:
        # Deleting yourself from the panel leaves the project without an owner.
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_ACCESS_DENIED)
    if user.role == UserRole.ADMIN:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_ACCESS_DENIED)

    from app.services.account_deletion import delete_user_account

    # Written before the row disappears: this is the record that the request was
    # carried out, and afterwards there is nothing left to point at.
    logger.info(
        "Account erased by admin: admin_id=%d target_user_id=%d reviews_deleted=%s",
        admin.id,
        user.id,
        delete_reviews,
    )
    await delete_user_account(
        user=user,
        delete_reviews=delete_reviews,
        release_brand_representation=True,
        db=db,
    )
    return {"deleted": True}


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
        "profile_defaults": (
            await get_calculator_profile_defaults(db)
        ).model_dump(mode="json"),
        "counts": {"trialing": trialing or 0, "active": active or 0},
    }


@router.post("/calculator-settings", response_model=dict)
async def update_calculator_settings(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    paywall_enforced_value: bool = Body(..., alias="paywall_enforced", embed=True),
    trial_days_value: int | None = Body(None, alias="trial_days", embed=True),
    profile_defaults_value: CalculatorProfileDefaults | None = Body(
        None,
        alias="profile_defaults",
        embed=True,
    ),
) -> dict:
    """Изменить глобальные настройки калькулятора (рубильник пейволла + длина триала)."""
    await set_paywall_enforced(db, paywall_enforced_value)
    await set_trial_days(db, trial_days_value)
    if profile_defaults_value is not None:
        await set_calculator_profile_defaults(db, profile_defaults_value)
    profile_defaults = await get_calculator_profile_defaults(db)
    logger.info(
        f"Admin {admin.id} set calculator settings: paywall_enforced={paywall_enforced_value}, "
        f"trial_days={trial_days_value}"
    )
    return {
        "paywall_enforced": paywall_enforced(),
        "trial_days": trial_days(),
        "profile_defaults": profile_defaults.model_dump(mode="json"),
    }


@router.put(
    "/calculator-profile-defaults",
    response_model=CalculatorProfileDefaults,
)
async def update_calculator_profile_defaults(
    profile_defaults: CalculatorProfileDefaults,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalculatorProfileDefaults:
    """Update only the platform defaults used to seed new calculator profiles."""
    await set_calculator_profile_defaults(db, profile_defaults)
    logger.info("Admin %s updated calculator profile defaults", admin.id)
    return await get_calculator_profile_defaults(db)


@router.get(
    "/calculator-country-defaults",
    response_model=CalculatorCountryDefaultsMap,
)
async def read_calculator_country_defaults(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalculatorCountryDefaultsMap:
    """Per-country overrides applied on top of the global starting economics."""
    del admin
    return await get_calculator_country_defaults(db)


@router.put(
    "/calculator-country-defaults",
    response_model=CalculatorCountryDefaultsMap,
)
async def update_calculator_country_defaults(
    country_defaults: CalculatorCountryDefaultsMap,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalculatorCountryDefaultsMap:
    """Replace the whole per-country table in one go."""
    saved = await set_calculator_country_defaults(db, country_defaults)
    logger.info(
        "Admin %s updated calculator country defaults for %d countries",
        admin.id,
        len(saved.countries),
    )
    return saved


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
    bundle_source: dict | None = None
    if bundle_exists:
        bundle_size_mb = round(_ORCA_BUNDLE_PATH.stat().st_size / 1024 / 1024, 2)
        import zipfile as _zip
        with _zip.ZipFile(_ORCA_BUNDLE_PATH) as zf:
            bundle_vendor_count = 0
            for name in zf.namelist():
                if (
                    not name.endswith(".json")
                    or "/" in name
                    or name == "filamenthub-source.json"
                ):
                    continue
                try:
                    value = json.loads(zf.read(name))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict) and value.get("name") and value.get("version"):
                    bundle_vendor_count += 1
            try:
                bundle_source = json.loads(zf.read("filamenthub-source.json"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
                bundle_source = None

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
            "source": bundle_source,
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
