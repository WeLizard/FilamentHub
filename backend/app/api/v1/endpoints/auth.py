"""Authentication endpoints."""

from datetime import datetime

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status

from app.core.config import settings
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user, get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    decode_email_verification_token,
    decode_password_reset_token,
    generate_api_key,
    generate_email_verification_token,
    generate_password_reset_token,
    get_password_hash,
    verify_password,
)
from app.services.email_validator import is_personal_email, normalize_website_url
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.brand import Brand
from app.models.preset import Preset
from app.models.user_saved_preset import UserSavedPreset
from app.schemas.user import (
    APIKeyResponse,
    AccountDeleteRequest,
    AccountDeletionStats,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    Token,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.schemas.preset import PresetListResponse, PresetResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# Импортируем limiter из core
from app.core.limiter import limiter


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")  # Rate limiting: 3 попытки в минуту
async def register(
    request: Request,
    data: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Регистрация нового пользователя."""
    
    import logging
    logger = logging.getLogger(__name__)
    
    # Проверка существования email
    result = await db.execute(select(User).where(User.email == data.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Проверка существования username
    result = await db.execute(select(User).where(User.username == data.username))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )
    
    # Роль всегда "user" при регистрации - роль "brand" присваивается только после верификации email
    # если email совпадает с доменом существующего верифицированного бренда
    user_role = UserRole.USER
    
    # Хеширование пароля
    try:
        password_hash = get_password_hash(data.password)
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process password",
        )
    
    # Создание пользователя
    user = User(
        email=data.email,
        username=data.username,
        password_hash=password_hash,
        role=user_role,
        brand_id=None,  # Привязка к бренду происходит только после верификации email
        full_name=data.full_name if data.full_name else None,
        bio=data.bio if data.bio else None,
        active=True,
        email_verified=False,
    )
    
    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"User registered successfully: {user.email} (id={user.id})")
        
        # Генерируем токен для верификации email
        verification_token = generate_email_verification_token(user.id, user.email)
        
        # TODO: Отправить email с токеном верификации
        # Ссылка: {FRONTEND_URL}/verify-email?token={verification_token}
        logger.info(f"Email verification token generated for user {user.email}: {verification_token[:20]}...")
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating user: {str(e)}", exc_info=True)
        # Если это ошибка уникальности (например, если пользователь создался между проверками)
        error_str = str(e).lower()
        if "unique" in error_str or "duplicate" in error_str:
            if "email" in error_str:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered",
                )
            elif "username" in error_str:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken",
                )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user. Please try again.",
        )
    
    # Возвращаем ответ
    try:
        return UserResponse.model_validate(user)
    except Exception as e:
        logger.error(f"Error serializing user response: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user response",
        )


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")  # Rate limiting: 5 попыток в минуту
async def login(
    request: Request,
    data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """Вход пользователя (получить JWT token)."""
    
    # Find user by email
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()
    
    # Create tokens
    token_data = {"sub": user.email, "user_id": user.id, "role": user.role.value}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)
    
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshTokenResponse:
    """Обновить access token используя refresh token."""
    # Декодируем refresh token
    payload = decode_refresh_token(data.refresh_token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Получаем email из payload
    email: str | None = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Проверяем существование пользователя
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    # Создаём новый access token
    token_data = {"sub": user.email, "user_id": user.id, "role": user.role.value}
    access_token = create_access_token(data=token_data)
    
    return RefreshTokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserResponse:
    """Получить информацию о текущем пользователе."""
    return UserResponse.model_validate(current_user)


@router.get("/my-presets", response_model=PresetListResponse)
async def get_my_presets(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    updated_since: datetime | None = Query(
        None,
        description="ISO 8601 timestamp. Возвращает только пресеты, обновленные после указанного времени (инкрементальная синхронизация).",
    ),
) -> PresetListResponse:
    """
    Получить все пресеты пользователя (созданные + сохраненные из каталога).
    
    Используется для синхронизации пресетов в OrcaSlicer.
    Поддерживает инкрементальную синхронизацию через параметр updated_since.
    """
    preset_ids: set[int] = set()
    presets_dict: dict[int, Preset] = {}
    
    # 1. Получаем созданные пресеты (где user_id == current_user.id)
    created_query = select(Preset).where(
        Preset.user_id == current_user.id,
        Preset.active == True,
    )
    
    if updated_since:
        created_query = created_query.where(Preset.updated_at >= updated_since)
    
    created_result = await db.execute(created_query.options(selectinload(Preset.filament)))
    created_presets = created_result.scalars().all()
    
    for preset in created_presets:
        preset_ids.add(preset.id)
        presets_dict[preset.id] = preset
    
    # 2. Получаем сохраненные пресеты (из каталога)
    saved_query = select(UserSavedPreset).where(
        UserSavedPreset.user_id == current_user.id,
    )
    
    if updated_since:
        # Для сохраненных пресетов проверяем либо saved_at, либо updated_at самого пресета
        saved_query = saved_query.join(Preset).where(
            or_(
                UserSavedPreset.saved_at >= updated_since,
                Preset.updated_at >= updated_since,
            ),
        )
    else:
        saved_query = saved_query.join(Preset)
    
    saved_result = await db.execute(
        saved_query.options(selectinload(UserSavedPreset.preset).selectinload(Preset.filament))
    )
    saved_presets_relations = saved_result.scalars().all()
    
    for saved_preset_relation in saved_presets_relations:
        preset = saved_preset_relation.preset
        if preset.active:  # Проверяем, что пресет активен
            preset_id = preset.id
            if preset_id not in preset_ids:  # Убираем дубликаты (если пресет и создан, и сохранен)
                preset_ids.add(preset_id)
                presets_dict[preset_id] = preset
    
    # 3. Формируем список пресетов
    presets_list = [presets_dict[pid] for pid in sorted(preset_ids)]
    
    # 4. Преобразуем в PresetResponse
    preset_responses = [PresetResponse.model_validate(p) for p in presets_list]
    
    return PresetListResponse(
        items=preset_responses,
        total=len(preset_responses),
        page=1,
        size=len(preset_responses),
        pages=1,
    )


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Обновить профиль текущего пользователя."""
    from app.models.brand import Brand
    
    # Обновляем поля пользователя
    update_data = data.model_dump(exclude_unset=True)
    
    # Если обновляется пароль, хешируем его
    if "password" in update_data and update_data["password"]:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))
    
    # Если обновляется email или username, проверяем уникальность
    if "email" in update_data and update_data["email"]:
        result = await db.execute(select(User).where(User.email == update_data["email"]))
        existing_user = result.scalar_one_or_none()
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
    
    if "username" in update_data and update_data["username"]:
        result = await db.execute(select(User).where(User.username == update_data["username"]))
        existing_user = result.scalar_one_or_none()
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )
    
    # Если обновляется brand_id, проверяем что бренд существует
    if "brand_id" in update_data and update_data["brand_id"]:
        result = await db.execute(select(Brand).where(Brand.id == update_data["brand_id"]))
        brand = result.scalar_one_or_none()
        if not brand:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Brand not found",
            )
    
    # Применяем обновления
    for key, value in update_data.items():
        if key == "password_hash":
            setattr(current_user, "password_hash", value)
        elif hasattr(current_user, key):
            setattr(current_user, key, value)
    
    await db.commit()
    await db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)


@router.post("/api-key", response_model=APIKeyResponse)
async def generate_api_key_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> APIKeyResponse:
    """Сгенерировать API key для OrcaSlicer интеграции."""
    # Generate new API key
    new_api_key = generate_api_key()
    
    # Update user
    current_user.api_key = new_api_key
    await db.commit()
    
    return APIKeyResponse(api_key=new_api_key)


@router.get("/deletion-stats", response_model=AccountDeletionStats)
async def get_deletion_stats(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccountDeletionStats:
    """Получить статистику данных пользователя перед удалением аккаунта."""
    from app.services.account_deletion import get_deletion_stats
    
    stats = await get_deletion_stats(current_user.id, db)
    return AccountDeletionStats(**stats)


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str = Body(..., embed=True),
) -> UserResponse:
    """
    Верифицировать email пользователя по токену.
    
    После верификации автоматически проверяет, можно ли присвоить роль brand,
    если домен email совпадает с доменом сайта существующего верифицированного бренда.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Декодируем токен верификации
    payload = decode_email_verification_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )
    
    user_id: int | None = payload.get("user_id")
    email: str | None = payload.get("email")
    
    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token",
        )
    
    # Получаем пользователя
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Проверяем, что email совпадает
    if user.email != email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email mismatch",
        )
    
    # Проверяем, не верифицирован ли уже
    if user.email_verified:
        logger.info(f"Email already verified for user {user.email} (id={user.id})")
        return UserResponse.model_validate(user)
    
    # Устанавливаем email_verified = True
    user.email_verified = True
    
    # Проверяем, можно ли автоматически присвоить роль brand
    # Если email не личный и есть существующий верифицированный бренд с таким доменом сайта
    if not is_personal_email(user.email):
        # Извлекаем домен email
        email_domain = user.email.split("@")[1].lower() if "@" in user.email else None
        
        if email_domain:
            # Ищем верифицированные бренды с таким доменом сайта
            result = await db.execute(
                select(Brand).where(Brand.active == True, Brand.verified == True)
            )
            brands = result.scalars().all()
            
            for brand in brands:
                if brand.website:
                    # Нормализуем сайт бренда и сравниваем с доменом email
                    brand_website_domain = normalize_website_url(brand.website)
                    if brand_website_domain and email_domain == brand_website_domain:
                        # Нашли совпадение! Привязываем к бренду (роль не меняем)
                        user.brand_id = brand.id
                        logger.info(
                            f"Auto-linked user {user.email} (id={user.id}) to brand {brand.name} "
                            f"after email verification (email domain: {email_domain}, brand website: {brand_website_domain})"
                        )
                        break
    
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    data: Annotated[AccountDeleteRequest, Body()],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """
    Удалить аккаунт текущего пользователя.
    
    Требует подтверждения пароля и предоставляет опции обработки данных.
    """
    from app.services.account_deletion import delete_user_account
    
    # Проверяем пароль
    if not verify_password(data.password_confirm, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный пароль",
        )
    
    # Выполняем удаление аккаунта
    await delete_user_account(
        user=current_user,
        delete_reviews=data.delete_reviews,
        delete_brand_if_sole_representative=data.delete_brand_if_sole_representative,
        db=db,
    )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("5/hour")  # Rate limiting: 5 запросов в час
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ForgotPasswordResponse:
    """
    Запрос на восстановление пароля.
    
    Отправляет токен восстановления на email пользователя (если email существует).
    Для безопасности всегда возвращает успешный ответ, даже если email не найден.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Ищем пользователя по email
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    
    if user and user.active:
        # Генерируем токен восстановления пароля
        reset_token = generate_password_reset_token(user.id, user.email)
        
        # TODO: Отправить email с токеном восстановления
        # Ссылка: {FRONTEND_URL}/reset-password?token={reset_token}
        logger.info(f"Password reset token generated for user {user.email}: {reset_token[:20]}...")
        logger.info(f"Reset link: {settings.BASE_URL}/reset-password?token={reset_token}")
    
    # Всегда возвращаем успешный ответ для безопасности (чтобы не раскрывать существование email)
    return ForgotPasswordResponse()


@router.post("/reset-password", response_model=ResetPasswordResponse)
@limiter.limit("5/hour")  # Rate limiting: 5 попыток в час
async def reset_password(
    request: Request,
    data: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ResetPasswordResponse:
    """
    Установка нового пароля по токену восстановления.
    
    Токен должен быть получен через /forgot-password и действителен (не истёк).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Декодируем токен восстановления
    payload = decode_password_reset_token(data.token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный или истёкший токен восстановления пароля",
        )
    
    user_id: int | None = payload.get("user_id")
    email: str | None = payload.get("email")
    
    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный токен восстановления пароля",
        )
    
    # Получаем пользователя
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Проверяем, что email совпадает
    if user.email != email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Несоответствие email в токене",
        )
    
    # Проверяем, что аккаунт активен
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт заблокирован",
        )
    
    # Хешируем новый пароль
    try:
        password_hash = get_password_hash(data.new_password)
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка обработки пароля",
        )
    
    # Обновляем пароль
    user.password_hash = password_hash
    await db.commit()
    
    logger.info(f"Password reset successful for user {user.email} (id={user.id})")
    
    return ResetPasswordResponse()

