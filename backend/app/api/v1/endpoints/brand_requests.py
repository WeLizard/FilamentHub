"""Brand request endpoints."""

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_current_admin_user
from app.core.config import settings
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_BRAND_NOT_FOUND,
    ERR_BRAND_REQUEST_PENDING_CREATE,
    ERR_BRAND_REQUEST_PENDING_JOIN,
    ERR_BRAND_SLUG_EXISTS,
    ERR_FILE_NOT_FOUND_IN_REQUEST,
    ERR_REQUEST_NOT_FOUND,
    ERR_REQUEST_NOT_PENDING,
)
from app.db.session import get_db
from app.models.brand_request import BrandRequest, BrandRequestStatus, BrandRequestType
from app.models.brand import Brand
from app.models.user import User, UserRole
from app.schemas.brand_request import (
    BrandRequestCreate,
    BrandRequestListResponse,
    BrandRequestResponse,
    BrandRequestUpdate,
)
from app.services.file_service import (
    delete_proof_files,
    parse_proof_files,
    save_proof_file,
    serialize_proof_files,
)
from app.services.email_validator import is_email_requiring_documents, normalize_website_url

router = APIRouter(prefix="/brand-requests", tags=["brand-requests"])


@router.post("/", response_model=BrandRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_brand_request(
    data: BrandRequestCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandRequestResponse:
    """Создать заявку на вступление в бренд или создание нового бренда."""
    
    # Валидация в зависимости от типа заявки
    if data.request_type == BrandRequestType.JOIN:
        if not data.brand_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для заявок на вступление необходим brand_id",
            )
        
        # Проверяем, что бренд существует
        result = await db.execute(select(Brand).where(Brand.id == data.brand_id))
        brand = result.scalar_one_or_none()
        if not brand:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ERR_BRAND_NOT_FOUND,
            )
        
        # Проверяем, есть ли у бренда сотрудники (пользователи с brand_id = brand.id)
        from app.models.user import User
        employees_count_result = await db.execute(
            select(func.count(User.id)).where(User.brand_id == brand.id)
        )
        employees_count = employees_count_result.scalar() or 0
        has_employees = employees_count > 0
        
        # Если бренд не верифицирован ИЛИ у бренда нет сотрудников - требуем полную заявку как для CREATE
        if not brand.verified or not has_employees:
            # Нормализуем URL сайта перед проверкой
            normalized_website = None
            if data.company_website:
                normalized_website = normalize_website_url(data.company_website)
            
            # Проверяем, требуются ли документы для email
            requires_documents = is_email_requiring_documents(
                email=data.company_email or "",
                website=normalized_website,
            )
            
            # Если требуются документы → описание обязательно
            if requires_documents:
                if not data.proof_text or not data.proof_text.strip():
                    brand_type = "неверифицированного" if not brand.verified else "верифицированного без сотрудников"
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Для {brand_type} бренда необходимо указать описание подтверждающих документов. Пожалуйста, укажите описание документов, подтверждающих, что вы представляете этот бренд.",
                    )
        
        # Проверяем, что у пользователя еще нет активной заявки на этот бренд
        existing_request = await db.execute(
            select(BrandRequest).where(
                BrandRequest.user_id == current_user.id,
                BrandRequest.brand_id == data.brand_id,
                BrandRequest.request_type == BrandRequestType.JOIN,
                BrandRequest.status == BrandRequestStatus.PENDING,
            )
        )
        if existing_request.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERR_BRAND_REQUEST_PENDING_JOIN,
            )
    
    elif data.request_type == BrandRequestType.CREATE:
        if not data.new_brand_name or not data.new_brand_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для заявок на создание бренда необходимы название и slug",
            )
        
        # Проверяем, что slug бренда не существует
        existing_brand = await db.execute(
            select(Brand).where(Brand.slug == data.new_brand_slug)
        )
        if existing_brand.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERR_BRAND_SLUG_EXISTS,
            )
        
        # Проверяем, что у пользователя еще нет активной заявки на создание этого бренда
        existing_request = await db.execute(
            select(BrandRequest).where(
                BrandRequest.user_id == current_user.id,
                BrandRequest.new_brand_slug == data.new_brand_slug,
                BrandRequest.request_type == BrandRequestType.CREATE,
                BrandRequest.status == BrandRequestStatus.PENDING,
            )
        )
        if existing_request.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERR_BRAND_REQUEST_PENDING_CREATE,
            )
    
        # Проверка текстовых полей на плохие слова
        from app.services.preset_moderation import validate_text_field
        if data.new_brand_name:
            is_valid, error_msg = await validate_text_field(data.new_brand_name, db, "Название бренда")
            if not is_valid:
                raise HTTPException(status_code=400, detail=error_msg)
        
        if data.new_brand_description:
            is_valid, error_msg = await validate_text_field(data.new_brand_description, db, "Описание бренда")
            if not is_valid:
                raise HTTPException(status_code=400, detail=error_msg)
    
    # Проверка текстовых полей на плохие слова (для всех типов заявок)
    if data.message:
        is_valid, error_msg = await validate_text_field(data.message, db, "Сообщение")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    if data.proof_text:
        is_valid, error_msg = await validate_text_field(data.proof_text, db, "Описание документов")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    # Валидация: для CREATE заявок проверяем корпоративность email и обязательность документов
    # Для JOIN заявок: если у бренда есть сотрудники - упрощенная заявка, если нет - полная как для CREATE
    if data.request_type == BrandRequestType.CREATE:
        # Нормализуем URL сайта перед проверкой
        normalized_website = None
        if data.company_website:
            normalized_website = normalize_website_url(data.company_website)
        
        # Проверяем, требуются ли документы для email
        requires_documents = is_email_requiring_documents(
            email=data.company_email or "",
            website=normalized_website,  # Используем нормализованный URL
        )
        
        # Если требуются документы → описание обязательно
        # Файлы могут быть загружены после создания заявки через отдельный эндпоинт
        if requires_documents:
            # Описание обязательно для личной/не-корпоративной почты
            if not data.proof_text or not data.proof_text.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Для использования личной или некорпоративной почты необходимо указать описание подтверждающих документов. Пожалуйста, укажите описание документов, подтверждающих, что вы представляете этот бренд и имеете разрешение компании на его регистрацию.",
                )
            # Файлы не проверяем при создании - они могут быть загружены позже через /upload эндпоинт
        # Если email корпоративный → документы необязательны, описание тоже можно сделать необязательным
        # (но оставляем возможность указать для ускорения верификации)
    
    # Сериализуем файлы если они есть
    proof_files_str = serialize_proof_files(data.proof_files) if data.proof_files else None
    
    # Сериализуем соцсети если они есть
    social_media_str = None
    if data.social_media_urls:
        social_media_str = json.dumps(data.social_media_urls)
    
    # Нормализуем URL сайта перед сохранением (если еще не нормализован)
    company_website_normalized = None
    if data.company_website:
        company_website_normalized = normalize_website_url(data.company_website) or data.company_website
    
    # Нормализуем URL сайта для нового бренда (если есть)
    new_brand_website_normalized = None
    if data.new_brand_website:
        new_brand_website_normalized = normalize_website_url(data.new_brand_website) or data.new_brand_website
    
    # Создаем заявку
    brand_request = BrandRequest(
        user_id=current_user.id,
        request_type=data.request_type,
        brand_id=data.brand_id,
        new_brand_name=data.new_brand_name,
        new_brand_slug=data.new_brand_slug,
        new_brand_description=data.new_brand_description,
        new_brand_website=new_brand_website_normalized,  # Сохраняем нормализованный URL
        message=data.message,
        # Структурированные поля для подтверждающих документов
        company_email=data.company_email,
        company_website=company_website_normalized,  # Сохраняем нормализованный URL
        social_media_urls=social_media_str,
        proof_text=data.proof_text,
        proof_files=proof_files_str,
        status=BrandRequestStatus.PENDING,
    )
    
    db.add(brand_request)
    await db.commit()
    await db.refresh(brand_request)
    
    # ВАЖНО: Авто-верификация по домену почты работает ТОЛЬКО после подтверждения email
    # Пока email не подтвержден, любой может указать любой домен
    # После добавления email verification (в продакшене) можно будет делать так:
    # if current_user.email_verified:
    #     email_domain = current_user.email.split('@')[1] if '@' in current_user.email else None
    #     # Проверяем домен компании (например, h-t-p.ru)
    #     # И автоматически одобряем заявку если домен совпадает
    # 
    # Сейчас просто создаем заявку в статусе PENDING
    
    response = BrandRequestResponse.model_validate(brand_request)
    # Файлы уже парсятся через валидатор в схеме, конвертация выполняется автоматически
    # Парсим соцсети если есть
    if brand_request.social_media_urls:
        try:
            response.social_media_urls = json.loads(brand_request.social_media_urls)
        except (json.JSONDecodeError, TypeError):
            response.social_media_urls = []
    return response


@router.get("/my", response_model=list[BrandRequestResponse])
async def get_my_brand_requests(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BrandRequestResponse]:
    """Получить список моих заявок."""
    result = await db.execute(
        select(BrandRequest)
        .where(BrandRequest.user_id == current_user.id)
        .order_by(BrandRequest.created_at.desc())
    )
    requests = result.scalars().all()
    responses = []
    for req in requests:
        response = BrandRequestResponse.model_validate(req)
        # Файлы уже парсятся через валидатор в схеме, конвертация выполняется автоматически
        if req.social_media_urls:
            try:
                response.social_media_urls = json.loads(req.social_media_urls)
            except (json.JSONDecodeError, TypeError):
                response.social_media_urls = []
        responses.append(response)
    return responses


@router.get("/", response_model=BrandRequestListResponse)
async def list_brand_requests(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    status_filter: BrandRequestStatus | None = Query(None, alias="status"),
) -> BrandRequestListResponse:
    """Получить список всех заявок (только для админов)."""
    
    query = select(BrandRequest)
    if status_filter:
        query = query.where(BrandRequest.status == status_filter)
    
    # Count total
    count_query = select(func.count()).select_from(BrandRequest)
    if status_filter:
        count_query = count_query.where(BrandRequest.status == status_filter)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(BrandRequest.created_at.desc())
    
    # Execute
    result = await db.execute(query)
    requests = result.scalars().all()
    
    pages = (total + size - 1) // size if total > 0 else 0
    
    return BrandRequestListResponse(
        items=[BrandRequestResponse.model_validate(req) for req in requests],
        total=total,
    )


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_brand_request(
    request_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Отозвать свою заявку (можно отозвать только pending заявки)."""
    
    result = await db.execute(
        select(BrandRequest).where(
            BrandRequest.id == request_id,
            BrandRequest.user_id == current_user.id,
        )
    )
    request = result.scalar_one_or_none()
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_REQUEST_NOT_FOUND,
        )
    
    if request.status != BrandRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_REQUEST_NOT_PENDING,
        )
    
    # Удаляем прикрепленные файлы
    if request.proof_files:
        await delete_proof_files(request.proof_files)
    
    await db.delete(request)
    await db.commit()


@router.patch("/{request_id}", response_model=BrandRequestResponse)
async def update_brand_request(
    request_id: int,
    data: BrandRequestUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandRequestResponse:
    """Обновить статус заявки (одобрить/отклонить) - только для админов."""
    
    result = await db.execute(
        select(BrandRequest).where(BrandRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_REQUEST_NOT_FOUND,
        )
    
    if request.status != BrandRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_REQUEST_NOT_PENDING,
        )
    
    # Обновляем статус
    request.status = data.status
    request.processed_by_id = admin.id
    request.processed_at = datetime.utcnow()
    
    if data.status == BrandRequestStatus.REJECTED:
        request.rejection_reason = data.rejection_reason
    
    # Если заявка одобрена и это JOIN - привязываем пользователя к бренду
    if data.status == BrandRequestStatus.APPROVED:
        if request.request_type == BrandRequestType.JOIN:
            user = await db.get(User, request.user_id)
            if user:
                # Просто привязываем к бренду, роль не меняем
                user.brand_id = request.brand_id
        elif request.request_type == BrandRequestType.CREATE:
            # Создаем бренд и привязываем пользователя
            new_brand = Brand(
                name=request.new_brand_name,
                slug=request.new_brand_slug,
                description=request.new_brand_description,
                website=request.new_brand_website,
                verified=True,  # Автоматически верифицируем после одобрения админом
                active=True,
            )
            db.add(new_brand)
            await db.flush()  # Чтобы получить ID бренда
            
            user = await db.get(User, request.user_id)
            if user:
                # Просто привязываем к бренду, роль не меняем
                user.brand_id = new_brand.id
    
    await db.commit()
    await db.refresh(request)
    
    return BrandRequestResponse.model_validate(request)


@router.get("/{request_id}", response_model=BrandRequestResponse)
async def get_brand_request(
    request_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandRequestResponse:
    """Получить заявку по ID."""
    
    result = await db.execute(
        select(BrandRequest).where(BrandRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_REQUEST_NOT_FOUND,
        )
    
    # Пользователь может видеть только свои заявки (или админ - все)
    if request.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы можете просматривать только свои заявки",
        )
    
    response = BrandRequestResponse.model_validate(request)
    # Файлы уже парсятся через валидатор в схеме, конвертация выполняется автоматически
    # Парсим соцсети если есть
    if request.social_media_urls:
        try:
            response.social_media_urls = json.loads(request.social_media_urls)
        except (json.JSONDecodeError, TypeError):
            response.social_media_urls = []
    return response


@router.post("/{request_id}/upload", response_model=BrandRequestResponse)
async def upload_proof_file(
    request_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
) -> BrandRequestResponse:
    """Загрузить файл доказательства для заявки."""
    
    # Проверяем, что заявка существует и принадлежит пользователю
    result = await db.execute(
        select(BrandRequest).where(BrandRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_REQUEST_NOT_FOUND,
        )
    
    if request.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Загружать файлы можно только в свои заявки",
        )
    
    # Проверяем, что заявка в статусе pending
    if request.status != BrandRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_REQUEST_NOT_PENDING,
        )
    
    # Получаем существующие файлы для проверки лимита
    existing_files = parse_proof_files(request.proof_files)
    
    # Сохраняем файл (с проверкой лимита)
    file_path = await save_proof_file(
        file=file,
        request_id=request_id,
        user_id=current_user.id,
        request_type="brand",
        existing_files=existing_files,
    )
    
    # Проверяем, не добавлен ли файл уже (по пути)
    file_path_str = file_path.get("path") if isinstance(file_path, dict) else file_path
    already_exists = any(
        (item.get("path") if isinstance(item, dict) else item) == file_path_str
        for item in existing_files
    )
    
    # Добавляем файл в список только если его еще нет
    if not already_exists:
        existing_files.append(file_path)
    request.proof_files = serialize_proof_files(existing_files)
    
    await db.commit()
    await db.refresh(request)
    
    response = BrandRequestResponse.model_validate(request)
    # Файлы уже парсятся через валидатор в схеме, конвертация выполняется автоматически
    # Парсим соцсети если есть
    if request.social_media_urls:
        try:
            response.social_media_urls = json.loads(request.social_media_urls)
        except (json.JSONDecodeError, TypeError):
            response.social_media_urls = []
    return response


@router.delete("/{request_id}/files/{file_path:path}", response_model=BrandRequestResponse)
async def delete_proof_file_endpoint(
    request_id: int,
    file_path: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandRequestResponse:
    """Удалить файл подтверждающего документа из заявки."""
    
    # Проверяем, что заявка существует и принадлежит пользователю
    result = await db.execute(
        select(BrandRequest).where(BrandRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_REQUEST_NOT_FOUND,
        )
    
    if request.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Удалять файлы можно только из своих заявок",
        )
    
    # Проверяем, что заявка в статусе pending
    if request.status != BrandRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERR_REQUEST_NOT_PENDING,
        )
    
    # Удаляем файл из списка
    existing_files = parse_proof_files(request.proof_files)
    # Ищем файл по пути (может быть как объект, так и строка в старом формате)
    file_to_remove = None
    for file_info in existing_files:
        if isinstance(file_info, dict):
            if file_info.get("path") == file_path:
                file_to_remove = file_info
                break
        elif isinstance(file_info, str) and file_info == file_path:
            file_to_remove = file_info
            break
    
    if file_to_remove is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERR_FILE_NOT_FOUND_IN_REQUEST,
        )
    
    existing_files.remove(file_to_remove)
    
    # Удаляем файл с диска
    from app.services.file_service import delete_proof_file
    await delete_proof_file(file_path)
    
    # Обновляем заявку
    if existing_files:
        request.proof_files = serialize_proof_files(existing_files)
    else:
        request.proof_files = None
    
    await db.commit()
    await db.refresh(request)
    
    response = BrandRequestResponse.model_validate(request)
    # Файлы уже парсятся через валидатор в схеме, конвертация выполняется автоматически
    return response

