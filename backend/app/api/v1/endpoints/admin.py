"""Admin endpoints for moderation and verification."""

import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.dependencies import get_current_admin_user
from app.db.session import get_db
from app.models.brand import Brand
from app.models.brand_request import BrandRequest, BrandRequestStatus
from app.models.preset import Preset, PresetModerationStatus
from app.models.printer import Printer
from app.models.printer_request import PrinterRequest, PrinterRequestStatus
from app.models.user import User, UserRole
from app.schemas.brand import BrandListResponse, BrandResponse
from app.schemas.brand_request import BrandRequestListResponse, BrandRequestResponse, BrandRequestUpdate
from app.schemas.database import (
    DatabaseDumpDeleteResponse,
    DatabaseDumpInfo,
    DatabaseDumpListResponse,
    DatabaseExportRequest,
    DatabaseExportResponse,
    DatabaseImportRequest,
    DatabaseImportResponse,
    DatabaseIntegrityResponse,
    DatabaseStatsResponse,
    MigrationApplyRequest,
    MigrationApplyResponse,
    MigrationHistoryResponse,
    RecreateTablesResponse,
    TableStructureResponse,
    TableDataRequest,
    TableDataResponse,
)
from app.schemas.preset import PresetResponse
from app.schemas.printer import PrinterCreate, PrinterListResponse, PrinterResponse, PrinterUpdate
from app.schemas.printer_request import (
    PrinterRequestListResponse,
    PrinterRequestResponse,
    PrinterRequestUpdate,
)
from app.schemas.user import UserResponse
from app.services.database_service import (
    apply_migration as apply_migration_service,
    delete_database_dump as delete_database_dump_service,
    downgrade_migration as downgrade_migration_service,
    export_database as export_database_service,
    get_database_stats as get_database_stats_service,
    get_migration_history as get_migration_history_service,
    get_table_data as get_table_data_service,
    get_table_structure as get_table_structure_service,
    import_database as import_database_service,
    list_database_dumps as list_database_dumps_service,
    recreate_missing_tables as recreate_missing_tables_service,
    validate_migration_integrity as validate_migration_integrity_service,
)

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
    from sqlalchemy import or_
    
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
        search_term = f"%{search.lower()}%"
        query = query.where(Brand.name.ilike(search_term))

    # Count total
    count_query = select(func.count()).select_from(Brand)
    if active_only:
        count_query = count_query.where(Brand.active == True)
    if verified is not None:
        count_query = count_query.where(Brand.verified == verified)
    if search:
        search_term = f"%{search.lower()}%"
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    
    brand.verified = True
    await db.commit()
    await db.refresh(brand)
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    
    brand.verified = False
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset not found",
        )
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset not found",
        )
    
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
    role: UserRole | None = Query(None),
    active_only: bool = Query(True),
) -> list[UserResponse]:
    """Получить список пользователей."""
    from sqlalchemy.orm import selectinload
    
    query = select(User).options(selectinload(User.brand))
    
    if active_only:
        query = query.where(User.active == True)
    if role:
        query = query.where(User.role == role)
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    user.role = UserRole.ADMIN
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/unlink-brand", response_model=UserResponse)
async def unlink_user_from_brand(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Отвязать пользователя от бренда (убрать brand_id, вернуть роль user)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if user.role != UserRole.BRAND or not user.brand_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not linked to a brand",
        )
    
    # Отвязываем от бренда и возвращаем роль user
    user.brand_id = None
    user.role = UserRole.USER
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.get("/stats", response_model=dict)
async def get_admin_stats(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Получить статистику для админки."""
    # Users
    users_total = await db.scalar(select(func.count(User.id)))
    users_brands = await db.scalar(select(func.count(User.id)).where(User.role == UserRole.BRAND))
    users_admins = await db.scalar(select(func.count(User.id)).where(User.role == UserRole.ADMIN))
    
    # Brands
    brands_total = await db.scalar(select(func.count(Brand.id)))
    brands_verified = await db.scalar(select(func.count(Brand.id)).where(Brand.verified == True))
    brands_pending = await db.scalar(select(func.count(Brand.id)).where(Brand.verified == False))
    
    # Presets
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
    
    return {
        "users": {
            "total": users_total,
            "brands": users_brands,
            "admins": users_admins,
        },
        "brands": {
            "total": brands_total,
            "verified": brands_verified,
            "pending_verification": brands_pending,
        },
        "presets": {
            "total": presets_total,
            "pending_moderation": presets_pending,
            "approved": presets_approved,
            "rejected": presets_rejected,
        },
    }


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand request not found",
        )
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand request not found",
        )
    
    if request.status != BrandRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only update pending requests",
        )
    
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        # Изменяем роль пользователя на brand
        user.role = UserRole.BRAND
        
        if request.request_type == BrandRequestType.JOIN:
            # Для JOIN: привязываем пользователя к существующему бренду
            if not request.brand_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Brand ID is required for JOIN requests",
                )
            user.brand_id = request.brand_id
            
        elif request.request_type == BrandRequestType.CREATE:
            # Для CREATE: создаем новый бренд и привязываем пользователя
            if not request.new_brand_name or not request.new_brand_slug:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Brand name and slug are required for CREATE requests",
                )
            
            # Проверяем, что бренд еще не создан
            existing_brand = await db.execute(
                select(Brand).where(Brand.slug == request.new_brand_slug)
            )
            if existing_brand.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Brand with this slug already exists",
                )
            
            # Создаем новый бренд
            new_brand = Brand(
                name=request.new_brand_name,
                slug=request.new_brand_slug,
                description=request.new_brand_description,
                website=request.new_brand_website,
                verified=True,  # Автоматически верифицируем после одобрения админом
                active=True,
            )
            db.add(new_brand)
            await db.flush()  # Получаем ID бренда
            
            # Привязываем пользователя к новому бренду
            user.brand_id = new_brand.id
    
    await db.commit()
    await db.refresh(request)
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand request not found",
        )
    
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
        raise HTTPException(status_code=400, detail="Printer with this slug already exists")
    
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
        raise HTTPException(status_code=404, detail="Printer not found")
    
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
        raise HTTPException(status_code=404, detail="Printer request not found")
    
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
        raise HTTPException(status_code=404, detail="Printer request not found")
    
    # Если одобряем запрос, создаём принтер
    if data.status == PrinterRequestStatus.APPROVED:
        # Проверяем, что принтер ещё не создан
        printer_result = await db.execute(select(Printer).where(Printer.slug == request.slug))
        existing_printer = printer_result.scalar_one_or_none()
        
        if existing_printer:
            raise HTTPException(
                status_code=400,
                detail="Принтер с таким slug уже существует в базе"
            )
        
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
    
    dump_file = Path(settings.UPLOAD_DIR) / "database_dumps" / filename
    
    if not dump_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл дампа не найден",
        )
    
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
            detail="Имя файла не указано",
        )
    
    # Проверяем расширение файла
    valid_extensions = {
        'custom': ['.dump'],
        'plain': ['.sql'],
        'tar': ['.tar'],
    }
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in valid_extensions.get(format, []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неверное расширение файла для формата {format}. Ожидается: {', '.join(valid_extensions.get(format, []))}",
        )
    
    # Проверяем размер файла (максимум 1GB)
    MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Файл слишком большой. Максимальный размер: 1GB",
        )
    
    # Сохраняем загруженный файл
    dumps_dir = Path(settings.UPLOAD_DIR) / "database_dumps"
    dumps_dir.mkdir(parents=True, exist_ok=True)
    
    # Используем оригинальное имя файла с timestamp для избежания конфликтов
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    filepath = dumps_dir / safe_filename
    
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
            detail=f"Ошибка импорта: {str(e)}",
        )
    
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
            detail="Недопустимое имя файла",
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
            detail=f"Ошибка получения структуры таблицы: {str(e)}",
        )


@router.get("/database/integrity", response_model=DatabaseIntegrityResponse)
async def check_database_integrity(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: AsyncSession = Depends(get_db),
) -> DatabaseIntegrityResponse:
    """Проверить целостность базы данных."""
    is_valid, missing_tables = await validate_migration_integrity_service(db)
    
    if is_valid:
        message = "База данных в порядке: все необходимые таблицы существуют"
    else:
        message = f"Обнаружены проблемы: отсутствуют таблицы {', '.join(missing_tables)}"
    
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
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка получения данных таблицы: {str(e)}",
        )

