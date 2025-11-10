"""Pydantic schemas for PrintProfile."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PrintProfileBase(BaseModel):
    """Base schema for print (process) profiles."""

    name: str = Field(..., max_length=200)
    slug: str = Field(..., max_length=200)
    description: str | None = Field(None, max_length=10_000)
    category: str | None = Field(None, max_length=100)
    owner_user_id: int | None = Field(None, ge=1)
    is_official: bool = False
    active: bool = True
    source: str = "user"
    vendor: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=200)
    setting_id: str | None = Field(None, max_length=100)
    quality_tier: str | None = Field(None, max_length=50)
    default_nozzle: str | None = Field(None, max_length=20)
    layer_height_mm: float | None = None
    compatible_printers: list[str] | None = None
    compatible_filaments: list[str] | None = None
    orcaslicer_settings: dict[str, Any] = Field(default_factory=dict)
    extra_metadata: dict[str, Any] | None = None
    notes: str | None = Field(None, max_length=10_000)


class PrintProfilePrinterLink(BaseModel):
    """Link schema for printers compatible with print profile."""

    printer_id: int | None = None
    printer_slug: str
    relation_type: str
    condition: str | None = None

    model_config = {
        "from_attributes": True,
    }


class PrintProfileFilamentLink(BaseModel):
    """Link schema for filaments compatible with print profile."""

    filament_id: int | None = None
    filament_slug: str
    relation_type: str

    model_config = {
        "from_attributes": True,
    }


class PrintProfileCreate(PrintProfileBase):
    """Schema for creating print profile."""

    pass


class PrintProfileUpdate(BaseModel):
    """Schema for updating print profile."""

    name: str | None = Field(None, max_length=200)
    slug: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=10_000)
    category: str | None = Field(None, max_length=100)
    owner_user_id: int | None = Field(None, ge=1)
    is_official: bool | None = None
    active: bool | None = None
    source: str | None = Field(None, max_length=50)
    vendor: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=200)
    setting_id: str | None = Field(None, max_length=100)
    quality_tier: str | None = Field(None, max_length=50)
    default_nozzle: str | None = Field(None, max_length=20)
    layer_height_mm: float | None = None
    compatible_printers: list[str] | None = None
    compatible_filaments: list[str] | None = None
    orcaslicer_settings: dict[str, Any] | None = None
    extra_metadata: dict[str, Any] | None = None
    notes: str | None = Field(None, max_length=10_000)


class PrintProfileResponse(PrintProfileBase):
    """Schema for returning print profile."""

    id: int
    created_at: datetime
    updated_at: datetime
    printer_links: list[PrintProfilePrinterLink] = Field(default_factory=list)
    filament_links: list[PrintProfileFilamentLink] = Field(default_factory=list)

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class PrintProfileListResponse(BaseModel):
    """Paginated response for print profiles."""

    items: list[PrintProfileResponse]
    total: int
    page: int
    size: int
    pages: int
