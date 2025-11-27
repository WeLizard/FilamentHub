"""Pydantic schemas for PrinterProfile."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field


class PrinterProfileBase(BaseModel):
    """Base schema for printer profiles."""

    name: str = Field(..., max_length=200)
    slug: str = Field(..., max_length=200)
    description: str | None = Field(None, max_length=10_000)
    printer_id: int | None = Field(None, ge=1)
    owner_user_id: int | None = Field(None, ge=1)
    is_official: bool = False
    active: bool = True
    source: str = "user"
    vendor: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=200)
    setting_id: str | None = Field(None, max_length=100)
    nozzle_diameters: list[float] | None = None
    printable_area: dict | list | None = None
    printable_height_mm: float | None = None
    default_print_profile_slug: str | None = Field(None, max_length=200)
    orcaslicer_settings: dict[str, Any] = Field(default_factory=dict)
    extra_metadata: dict[str, Any] | None = None
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
    source: str | None = Field(None, max_length=50)
    vendor: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=200)
    setting_id: str | None = Field(None, max_length=100)
    nozzle_diameters: list[float] | None = None
    printable_area: dict | list | None = None
    printable_height_mm: float | None = None
    default_print_profile_slug: str | None = Field(None, max_length=200)
    orcaslicer_settings: dict[str, Any] | None = None
    extra_metadata: dict[str, Any] | None = None
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
        "populate_by_name": True,
    }

    @computed_field(return_type=str | None, alias="printer_slug")
    def printer_slug(self) -> str | None:  # pragma: no cover - simple accessor
        printer = getattr(self, "printer", None)
        if printer is not None:
            return getattr(printer, "slug", None)
        return None

    @computed_field(return_type=str | None, alias="printer_name")
    def printer_name(self) -> str | None:  # pragma: no cover - simple accessor
        printer = getattr(self, "printer", None)
        if printer is not None:
            return getattr(printer, "name", None)
        return None

    @computed_field(return_type=str | None, alias="printer_manufacturer")
    def printer_manufacturer(self) -> str | None:  # pragma: no cover - simple accessor
        printer = getattr(self, "printer", None)
        if printer is not None:
            return getattr(printer, "manufacturer", None)
        return None

    @computed_field(return_type=str | None, alias="printer_model")
    def printer_model(self) -> str | None:  # pragma: no cover - simple accessor
        printer = getattr(self, "printer", None)
        if printer is not None:
            return getattr(printer, "model", None)
        return None


class PrinterProfileListResponse(BaseModel):
    """Paginated printer profiles response."""

    items: list[PrinterProfileResponse]
    total: int
    page: int
    size: int
    pages: int
