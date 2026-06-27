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
    logo_bg: str | None = Field(None, max_length=32)
    verified: bool = False
    currency: str = Field("RUB", max_length=8)
    social_media_urls: list[str] | None = None
    shop_links: list[dict[str, str]] | None = None
    price_hidden: bool = False


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
    created_at: datetime
    updated_at: datetime
    employees_count: int | None = Field(None, description="Количество сотрудников (только при запросе)")

    model_config = ConfigDict(from_attributes=True)


class BrandListResponse(BaseModel):
    """Schema for Brand list response."""

    items: list[BrandResponse]
    total: int
    page: int
    size: int
    pages: int


class PopularPrinterItem(BaseModel):
    """Принтер и число привязанных к нему пресетов бренда."""

    printer_id: int
    name: str
    manufacturer: str | None = None
    count: int


class BrandUsageResponse(BaseModel):
    """Статистика использования материалов бренда."""

    popular_printers: list[PopularPrinterItem]
    spools_tracked: int
    total_preset_usage: int
    presets_count: int

