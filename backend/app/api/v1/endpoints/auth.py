"""Authentication endpoints."""

from datetime import datetime

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    generate_api_key,
    get_password_hash,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.user import (
    APIKeyResponse,
    LoginRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    Token,
    UserCreate,
    UserResponse,
)

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
    
    # Валидация и конвертация роли
    try:
        user_role = UserRole(data.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {data.role}. Must be 'user' or 'brand'",
        )
    
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

