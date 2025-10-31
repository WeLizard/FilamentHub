"""Pydantic schemas for Brand."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BrandBase(BaseModel):
    """Base schema for Brand."""

    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    website: str | None = None
    logo_url: str | None = None
    verified: bool = False


class BrandCreate(BrandBase):
    """Schema for creating Brand."""

    pass


class BrandUpdate(BaseModel):
    """Schema for updating Brand."""

    name: str | None = Field(None, min_length=1, max_length=100)
    slug: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    website: str | None = None
    logo_url: str | None = None
    verified: bool | None = None
    active: bool | None = None


class BrandResponse(BrandBase):
    """Schema for Brand response."""

    id: int
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BrandListResponse(BaseModel):
    """Schema for Brand list response."""

    items: list[BrandResponse]
    total: int
    page: int
    size: int
    pages: int

