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
    role: Literal["user", "brand"] = Field(default="user")


class UserUpdate(BaseModel):
    """Schema for updating User."""

    email: EmailStr | None = None
    username: str | None = Field(None, min_length=3, max_length=100)
    full_name: str | None = Field(None, max_length=255)
    bio: str | None = None
    password: str | None = Field(None, min_length=8, max_length=100)


class UserResponse(UserBase):
    """Schema for User response."""

    id: int
    role: UserRole
    api_key: str | None = None
    active: bool
    email_verified: bool
    brand_id: int | None = None
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

