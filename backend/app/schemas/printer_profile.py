"""Pydantic schemas for PrinterProfile."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PrinterProfileBase(BaseModel):
    """Base schema for printer profiles."""

    name: str = Field(..., max_length=200)
    slug: str = Field(..., max_length=200)
    description: str | None = Field(None, max_length=10_000)
    printer_id: int | None = Field(None, ge=1)
    owner_user_id: int | None = Field(None, ge=1)
    is_official: bool = False
    active: bool = True
    orcaslicer_settings: dict[str, Any] = Field(default_factory=dict)
    start_gcode: str | None = None
    end_gcode: str | None = None
    notes: str | None = Field(None, max_length=10_000)


class PrinterProfileCreate(PrinterProfileBase):
    """Schema for creating printer profile."""

    pass


class PrinterProfileUpdate(BaseModel):
    """Schema for patching printer profile."""

    name: str | None = Field(None, max_length=200)
    slug: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=10_000)
    printer_id: int | None = Field(None, ge=1)
    owner_user_id: int | None = Field(None, ge=1)
    is_official: bool | None = None
    active: bool | None = None
    orcaslicer_settings: dict[str, Any] | None = None
    start_gcode: str | None = None
    end_gcode: str | None = None
    notes: str | None = Field(None, max_length=10_000)


class PrinterProfileResponse(PrinterProfileBase):
    """Schema for returning printer profile."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }


class PrinterProfileListResponse(BaseModel):
    """Paginated printer profiles response."""

    items: list[PrinterProfileResponse]
    total: int
    page: int
    size: int
    pages: int
