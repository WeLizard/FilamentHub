"""Authentication endpoints."""

from datetime import datetime, timezone

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status

from app.core.config import settings
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import (
    get_current_active_user,
    get_current_user,
    is_token_revoked,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    decode_email_verification_token,
    decode_password_reset_token,
    generate_api_key,
    generate_email_verification_token,
    generate_password_reset_token,
    get_password_hash,
    token_fingerprint,
    verify_password,
)
from app.services.email_validator import is_personal_email, normalize_website_url, validate_email_domain
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.brand import Brand
from app.models.preset import Preset
from app.models.revoked_token import RevokedToken
from app.models.user_saved_preset import UserSavedPreset
from app.schemas.user import (
    APIKeyResponse,
    AccountDeleteRequest,
    AccountDeletionStats,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    Token,
    UserCreate,
    UserEmailUpdate,
    UserPasswordUpdate,
    UserResponse,
    UserSettingsUpdate,
    UserUpdate,
    UserUsernameUpdate,
)
from app.schemas.preset import PresetListResponse, PresetResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# Импортируем limiter из core
from app.core.limiter import limiter
from app.core.errors import (
    ERR_ACCOUNT_BLOCKED,
    ERR_ACCOUNT_INACTIVE,
    ERR_BRAND_NOT_FOUND,
    ERR_EMAIL_EXISTS,
    ERR_EMAIL_MISMATCH,
    ERR_INVALID_REFRESH_TOKEN,
    ERR_INVALID_RESET_TOKEN,
    ERR_INVALID_VERIFICATION_TOKEN,
    ERR_PASSWORD_HASH_ERROR,
    ERR_RECAPTCHA_FAILED,
    ERR_RESPONSE_ERROR,
    ERR_USER_CREATE_ERROR,
    ERR_USER_NOT_FOUND,
    ERR_USERNAME_EXISTS,
    ERR_WRONG_PASSWORD,
    raise_error,
)


def _extract_expiry(payload: dict | None) -> datetime | None:
    """Convert JWT exp claim to timezone-aware datetime."""
    if not payload:
        return None

    exp = payload.get("exp")
    if exp is None:
        return None

    try:
        exp_timestamp = int(exp)
    except (TypeError, ValueError):
        return None

    return datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)


async def _revoke_token_if_valid(
    token: str,
    payload: dict | None,
    db: AsyncSession,
) -> None:
    """Store token fingerprint in revoked_tokens when token payload is valid."""
    expires_at = _extract_expiry(payload)
    if not expires_at:
        return

    fingerprint = token_fingerprint(token)
    existing = await db.execute(
        select(RevokedToken.id).where(RevokedToken.jti == fingerprint)
    )
    if existing.scalar_one_or_none():
        return

    db.add(RevokedToken(jti=fingerprint, expires_at=expires_at))


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

    # reCAPTCHA v3 verification
    from app.core.utils import verify_recaptcha
    if not await verify_recaptcha(data.recaptcha_token or ""):
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_RECAPTCHA_FAILED)

    # Проверка домена email: опечатки + DNS MX/A
    domain_error = await validate_email_domain(data.email)
    if domain_error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=domain_error,  # already {"code": ..., "params": ...} from validator
        )

    # Проверка существования email
    result = await db.execute(select(User).where(User.email == data.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_EMAIL_EXISTS)

    # Проверка существования username
    result = await db.execute(select(User).where(User.username == data.username))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_USERNAME_EXISTS)
    
    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    is_valid, error_msg = await validate_text_field(data.username, db, "username")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    if data.full_name:
        is_valid, error_msg = await validate_text_field(data.full_name, db, "full_name")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    if data.bio:
        is_valid, error_msg = await validate_text_field(data.bio, db, "bio")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    # Роль всегда "user" при регистрации - роль "brand" присваивается только после верификации email
    # если email совпадает с доменом существующего верифицированного бренда
    user_role = UserRole.USER
    
    # Хеширование пароля
    try:
        password_hash = get_password_hash(data.password)
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}", exc_info=True)
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_PASSWORD_HASH_ERROR)

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
        
        # Примечание: Отправка email с токеном верификации будет реализована при добавлении email-сервиса
        # Ссылка для верификации: {FRONTEND_URL}/verify-email?token={verification_token}
        logger.info(f"Email verification token generated for user {user.email}: {verification_token[:20]}...")
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating user: {str(e)}", exc_info=True)
        # Если это ошибка уникальности (например, если пользователь создался между проверками)
        error_str = str(e).lower()
        if "unique" in error_str or "duplicate" in error_str:
            if "email" in error_str:
                raise_error(status.HTTP_400_BAD_REQUEST, ERR_EMAIL_EXISTS)
            elif "username" in error_str:
                raise_error(status.HTTP_400_BAD_REQUEST, ERR_USERNAME_EXISTS)
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_USER_CREATE_ERROR)
    
    # Возвращаем ответ
    try:
        return UserResponse.model_validate(user)
    except Exception as e:
        logger.error(f"Error serializing user response: {str(e)}", exc_info=True)
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_RESPONSE_ERROR)


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")  # Rate limiting: 5 попыток в минуту
async def login(
    request: Request,
    data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """Вход пользователя (получить JWT token).
    
    Можно использовать email или username (без учёта регистра).
    """
    login_value = data.email.strip().lower()
    
    # Ищем по email ИЛИ username (case-insensitive)
    result = await db.execute(
        select(User).where(
            (func.lower(User.email) == login_value) | 
            (func.lower(User.username) == login_value)
        )
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(data.password, user.password_hash):
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_WRONG_PASSWORD, headers={"WWW-Authenticate": "Bearer"})

    if not user.active:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCOUNT_INACTIVE)
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)
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
    if await is_token_revoked(data.refresh_token, db):
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_REFRESH_TOKEN, headers={"WWW-Authenticate": "Bearer"})

    # Декодируем refresh token
    payload = decode_refresh_token(data.refresh_token)
    
    if payload is None:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_REFRESH_TOKEN, headers={"WWW-Authenticate": "Bearer"})

    # Получаем email из payload
    email: str | None = payload.get("sub")
    if email is None:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_REFRESH_TOKEN, headers={"WWW-Authenticate": "Bearer"})

    # Проверяем существование пользователя
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_USER_NOT_FOUND, headers={"WWW-Authenticate": "Bearer"})

    if not user.active:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCOUNT_INACTIVE)
    
    # Создаём новый access token
    token_data = {"sub": user.email, "user_id": user.id, "role": user.role.value}
    access_token = create_access_token(data=token_data)
    
    return RefreshTokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: LogoutRequest | None = Body(default=None),
) -> None:
    """Инвалидировать текущие access/refresh токены (server-side blacklist)."""
    _ = current_user  # авторизация обязательна, даже если объект пользователя дальше не нужен

    authorization = request.headers.get("Authorization")
    access_token = None
    if authorization and authorization.startswith("Bearer "):
        access_token = authorization.split(" ", 1)[1]

    if access_token:
        access_payload = decode_access_token(access_token)
        await _revoke_token_if_valid(access_token, access_payload, db)

    refresh_token = data.refresh_token if data else None
    if refresh_token:
        if await is_token_revoked(refresh_token, db):
            return

        refresh_payload = decode_refresh_token(refresh_token)
        if refresh_payload is None:
            raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_REFRESH_TOKEN, headers={"WWW-Authenticate": "Bearer"})

        refresh_email: str | None = refresh_payload.get("sub")
        if refresh_email != current_user.email:
            raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_REFRESH_TOKEN, headers={"WWW-Authenticate": "Bearer"})

        await _revoke_token_if_valid(refresh_token, refresh_payload, db)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserResponse:
    """Получить информацию о текущем пользователе."""
    return UserResponse.model_validate(current_user)


@router.get("/me/presets-stats", response_model=dict)
async def get_my_presets_stats(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Получить статистику пресетов пользователя.
    
    Возвращает:
    - total_presets: всего пресетов (созданные + добавленные из каталога)
    - synced_presets: количество пресетов с включенной синхронизацией (sync_enabled=True)
    """
    from sqlalchemy import func
    
    # 1. Подсчитываем пресеты, созданные напрямую пользователем
    direct_presets_count = await db.scalar(
        select(func.count(Preset.id)).where(
            Preset.user_id == current_user.id,
            Preset.active == True,
        )
    ) or 0
    
    # 2. Подсчитываем пресеты из user_saved_presets (добавленные из каталога)
    # Нужно исключить те, которые уже созданы пользователем напрямую
    saved_presets_query = (
        select(func.count(UserSavedPreset.id))
        .join(Preset)
        .where(
            UserSavedPreset.user_id == current_user.id,
            Preset.active == True,
            ~Preset.user_id.in_([current_user.id]),  # Исключаем пресеты, созданные пользователем
        )
    )
    saved_presets_count = await db.scalar(saved_presets_query) or 0
    
    # Но на самом деле нужно считать иначе:
    # Всего = все пресеты, связанные с пользователем (созданные + сохранённые)
    # Для этого лучше использовать другой подход:
    # - Все созданные пресеты пользователя
    # - Все сохранённые пресеты (включая те, которые созданы пользователем, но были также сохранены)
    
    # Пересчитываем более точно:
    # Получаем все ID пресетов из user_saved_presets
    saved_preset_ids_query = select(UserSavedPreset.preset_id).where(
        UserSavedPreset.user_id == current_user.id
    ).join(Preset).where(Preset.active == True)
    saved_preset_ids_result = await db.execute(saved_preset_ids_query)
    saved_preset_ids = set(row[0] for row in saved_preset_ids_result.all())
    
    # Получаем все ID пресетов, созданных пользователем
    direct_preset_ids_query = select(Preset.id).where(
        Preset.user_id == current_user.id,
        Preset.active == True,
    )
    direct_preset_ids_result = await db.execute(direct_preset_ids_query)
    direct_preset_ids = set(row[0] for row in direct_preset_ids_result.all())
    
    # Объединяем множества - это и есть общее количество пресетов
    total_preset_ids = saved_preset_ids | direct_preset_ids
    total_presets = len(total_preset_ids)
    
    # 3. Подсчитываем пресеты с включенной синхронизацией (sync=True)
    synced_presets_count = await db.scalar(
        select(func.count(UserSavedPreset.id))
        .join(Preset)
        .where(
            UserSavedPreset.user_id == current_user.id,
            UserSavedPreset.sync == True,
            Preset.active == True,
        )
    ) or 0
    
    # Также нужно добавить созданные пресеты, которые могут быть не в user_saved_presets
    # Но по логике, если пресет создан пользователем, он должен быть доступен для синхронизации
    # Однако sync_enabled относится только к user_saved_presets
    # Поэтому для полной картины считаем так:
    # synced_presets = пресеты из user_saved_presets с sync_enabled=True + созданные пресеты (если они не в user_saved_presets)
    
    # Пересчитываем synced_presets более точно:
    synced_from_saved = await db.scalar(
        select(func.count(UserSavedPreset.id))
        .join(Preset)
        .where(
            UserSavedPreset.user_id == current_user.id,
            UserSavedPreset.sync == True,
            Preset.active == True,
        )
    ) or 0
    
    # Созданные пресеты, которых нет в user_saved_presets, тоже считаются доступными для синхронизации
    # (потому что они автоматически доступны в /my-presets)
    created_not_in_saved = len(direct_preset_ids - saved_preset_ids)
    
    synced_presets = synced_from_saved + created_not_in_saved
    
    return {
        "total_presets": total_presets,
        "synced_presets": synced_presets,
    }


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
    from app.models.user_saved_preset import UserSavedPreset
    
    preset_ids: set[int] = set()
    presets_dict: dict[int, Preset] = {}
    
    # Получаем пресеты из двух источников:
    # 1. Из user_saved_presets с sync_enabled=True (основной путь - для синхронизации)
    # 2. Прямо созданные пользователем пресеты (preset.user_id == current_user.id)
    #    Это нужно для случаев, когда пресет был создан до добавления логики user_saved_presets
    #    или если по какой-то причине запись в user_saved_presets отсутствует
    
    # 1. Пресеты из user_saved_presets с включенной синхронизацией
    saved_query = select(UserSavedPreset).where(
        UserSavedPreset.user_id == current_user.id,
        UserSavedPreset.sync == True,  # Только пресеты с включенной синхронизацией
    )
    
    if updated_since:
        # Проверяем либо saved_at, либо updated_at самого пресета
        saved_query = saved_query.join(Preset).where(
            Preset.active == True,  # Пресет должен быть активен
            or_(
                UserSavedPreset.saved_at >= updated_since,
                Preset.updated_at >= updated_since,
            ),
        )
    else:
        saved_query = saved_query.join(Preset).where(Preset.active == True)
    
    saved_result = await db.execute(
        saved_query.options(selectinload(UserSavedPreset.preset).selectinload(Preset.filament))
    )
    saved_presets_relations = saved_result.scalars().all()
    
    for saved_preset_relation in saved_presets_relations:
        preset = saved_preset_relation.preset
        if preset.active:  # Проверяем, что пресет активен
            preset_id = preset.id
            preset_ids.add(preset_id)
            presets_dict[preset_id] = preset
    
    # 2. УДАЛЕНО: Старая логика проверки presets.sync_enabled
    # Теперь ВСЕ пресеты (свои + чужие) управляются через user_saved_presets.sync_enabled
    # При создании своего пресета автоматически создаётся запись в user_saved_presets (см. presets.py:249)
    # Поэтому НЕ нужно дополнительно проверять Preset.user_id и Preset.sync_enabled
    
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
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_EMAIL_EXISTS)

    if "username" in update_data and update_data["username"]:
        result = await db.execute(select(User).where(User.username == update_data["username"]))
        existing_user = result.scalar_one_or_none()
        if existing_user and existing_user.id != current_user.id:
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_USERNAME_EXISTS)
    
    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    if "username" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["username"], db, "username")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    if "full_name" in update_data and update_data["full_name"]:
        is_valid, error_msg = await validate_text_field(update_data["full_name"], db, "full_name")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    if "bio" in update_data and update_data["bio"]:
        is_valid, error_msg = await validate_text_field(update_data["bio"], db, "bio")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    # Если обновляется brand_id, проверяем что бренд существует
    if "brand_id" in update_data and update_data["brand_id"]:
        result = await db.execute(select(Brand).where(Brand.id == update_data["brand_id"]))
        brand = result.scalar_one_or_none()
        if not brand:
            raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)
    
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
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_VERIFICATION_TOKEN)

    user_id: int | None = payload.get("user_id")
    email: str | None = payload.get("email")

    if not user_id or not email:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_VERIFICATION_TOKEN)

    # Получаем пользователя
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

    # Проверяем, что email совпадает
    if user.email != email:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_EMAIL_MISMATCH)
    
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
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_WRONG_PASSWORD)
    
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
        
        # Примечание: Отправка email с токеном восстановления будет реализована при добавлении email-сервиса
        # Ссылка для восстановления: {FRONTEND_URL}/reset-password?token={reset_token}
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
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_RESET_TOKEN)

    user_id: int | None = payload.get("user_id")
    email: str | None = payload.get("email")

    if not user_id or not email:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_RESET_TOKEN)

    # Получаем пользователя
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)

    # Проверяем, что email совпадает
    if user.email != email:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_EMAIL_MISMATCH)

    # Проверяем, что аккаунт активен
    if not user.active:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCOUNT_BLOCKED)

    # Хешируем новый пароль
    try:
        password_hash = get_password_hash(data.new_password)
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}", exc_info=True)
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_PASSWORD_HASH_ERROR)
    
    # Обновляем пароль
    user.password_hash = password_hash
    await db.commit()
    
    logger.info(f"Password reset successful for user {user.email} (id={user.id})")
    
    return ResetPasswordResponse()


@router.patch("/me/settings", response_model=UserResponse)
async def update_user_settings(
    data: UserSettingsUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Обновить настройки синхронизации текущего пользователя."""
    update_data = data.model_dump(exclude_unset=True)
    
    # Обновляем только поля настроек
    for key, value in update_data.items():
        if hasattr(current_user, key):
            setattr(current_user, key, value)
    
    await db.commit()
    await db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)


@router.patch("/me/password", response_model=UserResponse)
async def update_user_password(
    data: UserPasswordUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Изменить пароль текущего пользователя."""
    # Проверяем текущий пароль (для безопасности критичных операций)
    if not verify_password(data.current_password, current_user.password_hash):
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_WRONG_PASSWORD)

    # Хешируем новый пароль
    try:
        password_hash = get_password_hash(data.new_password)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error hashing password: {str(e)}", exc_info=True)
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_PASSWORD_HASH_ERROR)
    
    # Обновляем пароль
    current_user.password_hash = password_hash
    await db.commit()
    await db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)


@router.patch("/me/username", response_model=UserResponse)
async def update_user_username(
    data: UserUsernameUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Изменить username текущего пользователя."""
    # Проверяем уникальность нового username
    result = await db.execute(select(User).where(User.username == data.new_username))
    existing_user = result.scalar_one_or_none()
    if existing_user and existing_user.id != current_user.id:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_USERNAME_EXISTS)

    # Обновляем username
    current_user.username = data.new_username
    await db.commit()
    await db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)


@router.patch("/me/email", response_model=UserResponse)
async def update_user_email(
    data: UserEmailUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Изменить email текущего пользователя.
    
    На новый email будет отправлен код подтверждения.
    Email будет обновлен только после подтверждения кода.
    """
    # Проверяем уникальность нового email
    result = await db.execute(select(User).where(User.email == data.new_email))
    existing_user = result.scalar_one_or_none()
    if existing_user and existing_user.id != current_user.id:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_EMAIL_EXISTS)

    # Обновляем email и сбрасываем верификацию (требуется повторная верификация)
    # Примечание: В будущих версиях планируется добавить подтверждение через код,
    # но на текущий момент email обновляется сразу с требованием повторной верификации
    current_user.email = data.new_email
    current_user.email_verified = False
    
    # Генерируем новый токен верификации
    import logging
    logger = logging.getLogger(__name__)
    verification_token = generate_email_verification_token(current_user.id, current_user.email)
    logger.info(f"Email verification token generated for user {current_user.email}: {verification_token[:20]}...")
    # Примечание: Отправка email с токеном верификации будет реализована при добавлении email-сервиса
    
    await db.commit()
    await db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)







