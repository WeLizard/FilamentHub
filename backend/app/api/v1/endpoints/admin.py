"""Admin endpoints for moderation and verification."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.schemas.preset import PresetResponse
from app.schemas.printer import PrinterCreate, PrinterListResponse, PrinterResponse, PrinterUpdate
from app.schemas.printer_request import (
    PrinterRequestListResponse,
    PrinterRequestResponse,
    PrinterRequestUpdate,
)
from app.schemas.user import UserResponse

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

