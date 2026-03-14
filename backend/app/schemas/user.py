"""Pydantic schemas for User."""

from datetime import datetime
from typing import Literal

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


def validate_password_strength(password: str) -> str:
    """Validate password has at least one letter and one digit."""
    if not re.search(r'[a-zA-Zа-яА-ЯёЁ]', password):
        raise ValueError('Пароль должен содержать хотя бы одну букву')
    if not re.search(r'\d', password):
        raise ValueError('Пароль должен содержать хотя бы одну цифру')
    return password


class UserBase(BaseModel):
    """Base schema for User."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: str | None = Field(None, max_length=255)
    bio: str | None = None


class UserCreate(UserBase):
    """Schema for creating User."""

    password: str = Field(..., min_length=8, max_length=100)

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)
    # Роль всегда "user" при создании - роль "brand" присваивается только через процесс верификации
    role: Literal["user"] = Field(default="user")


class UserUpdate(BaseModel):
    """Schema for updating User."""

    email: EmailStr | None = None
    username: str | None = Field(None, min_length=3, max_length=100)
    full_name: str | None = Field(None, max_length=255)
    bio: str | None = None
    password: str | None = Field(None, min_length=8, max_length=100)

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_password_strength(v)
        return v
    brand_id: int | None = Field(None, gt=0, description="ID бренда, который представляет пользователь")
    # Sync settings
    allow_filament_presets_import: bool | None = None
    allow_printer_profiles_import: bool | None = None
    allow_printer_profiles_export: bool | None = None
    allow_print_profiles_import: bool | None = None
    allow_print_profiles_export: bool | None = None


class UserSettingsUpdate(BaseModel):
    """Schema for updating user sync settings."""

    allow_filament_presets_import: bool | None = None
    allow_printer_profiles_import: bool | None = None
    allow_printer_profiles_export: bool | None = None
    allow_print_profiles_import: bool | None = None
    allow_print_profiles_export: bool | None = None


class UserPasswordUpdate(BaseModel):
    """Schema for updating user password."""

    current_password: str = Field(..., min_length=1, description="Текущий пароль")
    new_password: str = Field(..., min_length=8, max_length=100, description="Новый пароль")

    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class UserEmailUpdate(BaseModel):
    """Schema for updating user email."""

    new_email: EmailStr = Field(..., description="Новый email")


class UserUsernameUpdate(BaseModel):
    """Schema for updating user username."""

    new_username: str = Field(..., min_length=3, max_length=100, description="Новый username")


class UserResponse(UserBase):
    """Schema for User response."""

    id: int
    role: UserRole
    api_key: str | None = None
    active: bool
    email_verified: bool
    brand_id: int | None = None
    brand_name: str | None = None  # Название бренда (для админки)
    badges: list[str] | None = None  # Бейджи пользователя
    # Sync settings
    allow_filament_presets_import: bool = True
    allow_printer_profiles_import: bool = True
    allow_printer_profiles_export: bool = True
    allow_print_profiles_import: bool = True
    allow_print_profiles_export: bool = True
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserPublic(UserBase):
    """Schema for public User info (без sensitive данных)."""

    id: int
    username: str
    full_name: str | None = None
    badges: list[str] | None = None  # Бейджи пользователя (публично видны)

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """Schema for JWT token."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Schema for logout request."""

    refresh_token: str | None = None


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

    email: str  # email или username (без учёта регистра)
    password: str


class RegisterRequest(UserCreate):
    """Schema for register request."""

    recaptcha_token: str | None = Field(None, description="reCAPTCHA v3 token")


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

    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class ResetPasswordResponse(BaseModel):
    """Schema for reset password response."""
    
    message: str = Field(default="Пароль успешно изменён", description="Сообщение о результате")
