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
    compatible_printers: list[str] | None = None
    compatible_filaments: list[str] | None = None
    orcaslicer_settings: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(None, max_length=10_000)


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
    compatible_printers: list[str] | None = None
    compatible_filaments: list[str] | None = None
    orcaslicer_settings: dict[str, Any] | None = None
    notes: str | None = Field(None, max_length=10_000)


class PrintProfileResponse(PrintProfileBase):
    """Schema for returning print profile."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }


class PrintProfileListResponse(BaseModel):
    """Paginated response for print profiles."""

    items: list[PrintProfileResponse]
    total: int
    page: int
    size: int
    pages: int
