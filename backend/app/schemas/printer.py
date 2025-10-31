"""Pydantic schemas for Printer."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PrinterBase(BaseModel):
    """Base schema for Printer (FDM/FFF only)."""

    name: str = Field(..., min_length=1, max_length=200)
    manufacturer: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=200)
    
    # Build volume (optional)
    build_volume_x: float | None = Field(None, ge=0)
    build_volume_y: float | None = Field(None, ge=0)
    build_volume_z: float | None = Field(None, ge=0)
    
    # Nozzle diameter (для FDM)
    nozzle_diameter: float | None = Field(None, ge=0.1, le=2.0)
    
    # Temperature limits
    max_extruder_temp: int | None = Field(None, ge=0, le=500)
    max_bed_temp: int | None = Field(None, ge=0, le=200)
    
    # Description
    description: str | None = None
    image_url: str | None = Field(None, max_length=500)


class PrinterCreate(PrinterBase):
    """Schema for creating Printer."""

    pass


class PrinterUpdate(BaseModel):
    """Schema for updating Printer."""

    name: str | None = Field(None, min_length=1, max_length=200)
    manufacturer: str | None = Field(None, min_length=1, max_length=100)
    model: str | None = Field(None, min_length=1, max_length=100)
    slug: str | None = Field(None, min_length=1, max_length=200)
    
    build_volume_x: float | None = Field(None, ge=0)
    build_volume_y: float | None = Field(None, ge=0)
    build_volume_z: float | None = Field(None, ge=0)
    
    nozzle_diameter: float | None = Field(None, ge=0.1, le=2.0)
    max_extruder_temp: int | None = Field(None, ge=0, le=500)
    max_bed_temp: int | None = Field(None, ge=0, le=200)
    
    description: str | None = None
    image_url: str | None = Field(None, max_length=500)
    active: bool | None = None


class PrinterResponse(PrinterBase):
    """Schema for Printer response."""

    id: int
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrinterListResponse(BaseModel):
    """Schema for Printer list response."""

    items: list[PrinterResponse]
    total: int
    page: int
    size: int
    pages: int

