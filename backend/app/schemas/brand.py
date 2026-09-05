"""Pydantic schemas for Brand."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BrandBase(BaseModel):
    """Base schema for Brand."""

    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    website: str | None = None
    logo_url: str | None = None
    logo_bg: str | None = Field(None, max_length=32)
    verified: bool = False
    currency: str = Field("RUB", max_length=8)
    social_media_urls: list[str] | None = None
    shop_links: list[dict[str, str]] | None = None
    price_hidden: bool = False


class BrandCreate(BrandBase):
    """Schema for creating Brand."""

    slug: str | None = Field(None, max_length=100)


class BrandUpdate(BaseModel):
    """Schema for updating Brand."""

    name: str | None = Field(None, min_length=1, max_length=100)
    slug: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    website: str | None = None
    logo_url: str | None = None
    logo_bg: str | None = Field(None, max_length=32)
    verified: bool | None = None
    active: bool | None = None
    currency: str | None = Field(None, max_length=8)
    social_media_urls: list[str] | None = None
    shop_links: list[dict[str, str]] | None = None
    price_hidden: bool | None = None


class BrandResponse(BrandBase):
    """Schema for Brand response."""

    id: int
    active: bool
    name_correction_available: bool = False
    name_corrected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    employees_count: int | None = Field(None, description="Количество сотрудников (только при запросе)")
    market_country: str | None = Field(
        None, description="Страна, чья витрина подставлена в ответ"
    )

    model_config = ConfigDict(from_attributes=True)


class BrandListResponse(BaseModel):
    """Schema for Brand list response."""

    items: list[BrandResponse]
    total: int
    page: int
    size: int
    pages: int


class BrandMonthlySpools(BaseModel):
    """Fixed count of retained spool registrations, gated by distinct owners."""

    month: str
    status: Literal["available", "insufficient_cohort", "unavailable_scope"]
    value: int | None = Field(None, ge=10)
    captured_at: datetime | None = None


class BrandUsageResponse(BaseModel):
    """Public catalog count and the same monthly release as brand analytics."""

    presets_count: int
    monthly_registered_spools: BrandMonthlySpools


class BrandAnalyticsResponse(BaseModel):
    """Analytics constrained by the active Brand + Organization workspace."""

    scope: Literal["global", "territorial"]
    monthly_registered_spools: BrandMonthlySpools


class BrandSlugSuggestionResponse(BaseModel):
    """Server-owned suggestion for a new public brand URL."""

    slug: str


class BrandSlugRename(BaseModel):
    """Explicit administrative rename of a published brand URL."""

    slug: str = Field(..., min_length=1, max_length=100)
    expected_current_slug: str = Field(..., min_length=1, max_length=100)
