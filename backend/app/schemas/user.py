"""Pydantic schemas for User."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserBase(BaseModel):
    """Base schema for User."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: str | None = Field(None, max_length=255)
    bio: str | None = None


class UserCreate(UserBase):
    """Schema for creating User."""

    password: str = Field(..., min_length=8, max_length=100)
    # Роль всегда "user" при создании - роль "brand" присваивается только через процесс верификации
    role: Literal["user"] = Field(default="user")


class UserUpdate(BaseModel):
    """Schema for updating User."""

    email: EmailStr | None = None
    username: str | None = Field(None, min_length=3, max_length=100)
    full_name: str | None = Field(None, max_length=255)
    bio: str | None = None
    password: str | None = Field(None, min_length=8, max_length=100)
    brand_id: int | None = Field(None, gt=0, description="ID бренда, который представляет пользователь")


class UserResponse(UserBase):
    """Schema for User response."""

    id: int
    role: UserRole
    api_key: str | None = None
    active: bool
    email_verified: bool
    brand_id: int | None = None
    brand_name: str | None = None  # Название бренда (для админки)
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserPublic(UserBase):
    """Schema for public User info (без sensitive данных)."""

    id: int
    username: str
    full_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """Schema for JWT token."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""

    refresh_token: str


class RefreshTokenResponse(BaseModel):
    """Schema for refresh token response."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Schema for token payload."""

    sub: str | None = None  # user email
    user_id: int | None = None
    role: UserRole | None = None


class LoginRequest(BaseModel):
    """Schema for login request."""

    email: EmailStr
    password: str


class RegisterRequest(UserCreate):
    """Schema for register request."""

    pass


class APIKeyResponse(BaseModel):
    """Schema for API key response."""

    api_key: str
    message: str = "API key generated. Use it for OrcaSlicer integration."


class AccountDeleteRequest(BaseModel):
    """Schema for account deletion request with options."""
    
    delete_reviews: bool = Field(
        default=False,
        description="Полностью удалить отзывы (True) или анонимизировать (False)"
    )
    delete_brand_if_sole_representative: bool = Field(
        default=False,
        description="Удалить бренд, если пользователь единственный представитель (True) или передать админу (False)"
    )
    password_confirm: str = Field(
        ...,
        description="Подтверждение пароля для удаления аккаунта"
    )


class AccountDeletionStats(BaseModel):
    """Schema for account deletion statistics."""
    
    presets_count: int = Field(description="Количество созданных пресетов")
    official_presets_count: int = Field(description="Количество официальных пресетов")
    approved_presets_count: int = Field(description="Количество одобренных пресетов")
    presets_used_by_others_count: int = Field(description="Количество пресетов, сохраненных другими пользователями")
    reviews_count: int = Field(description="Количество отзывов")
    saved_presets_count: int = Field(description="Количество сохраненных пресетов")
    brand_requests_count: int = Field(description="Количество заявок на верификацию бренда")
    is_brand_representative: bool = Field(description="Является ли пользователь представителем бренда")
    brand_other_representatives_count: int = Field(description="Количество других представителей бренда (если есть)")


class ForgotPasswordRequest(BaseModel):
    """Schema for forgot password request."""
    
    email: EmailStr = Field(..., description="Email пользователя для восстановления пароля")


class ForgotPasswordResponse(BaseModel):
    """Schema for forgot password response."""
    
    message: str = Field(
        default="Если указанный email существует в системе, на него будет отправлена инструкция по восстановлению пароля.",
        description="Сообщение о результате запроса"
    )


class ResetPasswordRequest(BaseModel):
    """Schema for reset password request."""
    
    token: str = Field(..., description="Токен восстановления пароля")
    new_password: str = Field(..., min_length=8, max_length=100, description="Новый пароль")


class ResetPasswordResponse(BaseModel):
    """Schema for reset password response."""
    
    message: str = Field(default="Пароль успешно изменён", description="Сообщение о результате")

