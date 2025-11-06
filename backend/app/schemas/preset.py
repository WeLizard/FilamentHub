"""Pydantic schemas for Preset."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.printer import PrinterResponse

if TYPE_CHECKING:
    from app.schemas.filament import FilamentResponse


class PresetBase(BaseModel):
    """Base schema for Preset."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    is_official: bool = Field(False)
    is_weighted: bool = Field(False, description="Динамический взвешенный пресет, автоматически пересчитывается системой")

    # Print settings (required)
    extruder_temp: float = Field(..., ge=0, le=400)
    bed_temp: float = Field(..., ge=0, le=150)
    print_speed: float = Field(..., ge=1, le=500)
    travel_speed: float | None = Field(None, ge=1, le=500)

    # Advanced settings (optional)
    layer_height: float | None = Field(None, ge=0.05, le=1.0)
    first_layer_height: float | None = Field(None, ge=0.05, le=1.0)
    flow_rate: float | None = Field(None, ge=50, le=150)
    # flow_rate: % от стандартного

    # Cooling
    fan_speed: int | None = Field(None, ge=0, le=100)
    # fan_speed: 0-100%

    # Retraction
    retraction_length: float | None = Field(None, ge=0, le=10)
    retraction_speed: float | None = Field(None, ge=1, le=100)

    # Extended OrcaSlicer parameters (JSON)
    orcaslicer_settings: dict[str, Any] | None = Field(None, description="Расширенные параметры OrcaSlicer в формате JSON")

    # Rating
    rating: float | None = Field(None, ge=1, le=5)
    success_rate: float | None = Field(None, ge=0.0, le=100.0, description="Процент успешных печатей (0-100)")
    usage_count: int = Field(0, ge=0)


class PresetCreate(PresetBase):
    """Schema for creating Preset."""

    filament_id: int = Field(..., gt=0)
    user_id: int | None = Field(None, gt=0)  # Автоматически заполняется из токена
    printer_ids: list[int] = Field(default_factory=list, description="Список ID принтеров, для которых подходит этот пресет")


class PresetUpdate(BaseModel):
    """Schema for updating Preset."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    is_official: bool | None = None

    # Print settings
    extruder_temp: float | None = Field(None, ge=0, le=400)
    bed_temp: float | None = Field(None, ge=0, le=150)
    print_speed: float | None = Field(None, ge=1, le=500)
    travel_speed: float | None = Field(None, ge=1, le=500)

    # Advanced settings
    layer_height: float | None = Field(None, ge=0.05, le=1.0)
    first_layer_height: float | None = Field(None, ge=0.05, le=1.0)
    flow_rate: float | None = Field(None, ge=50, le=150)
    fan_speed: int | None = Field(None, ge=0, le=100)
    retraction_length: float | None = Field(None, ge=0, le=10)
    retraction_speed: float | None = Field(None, ge=1, le=100)

    # Extended OrcaSlicer parameters (JSON)
    orcaslicer_settings: dict[str, Any] | None = Field(None, description="Расширенные параметры OrcaSlicer в формате JSON")

    # Rating
    rating: float | None = Field(None, ge=1, le=5)
    active: bool | None = None
    
    # Printers
    printer_ids: list[int] | None = Field(None, description="Список ID принтеров, для которых подходит этот пресет")


class PresetResponse(PresetBase):
    """Schema for Preset response."""

    id: int
    filament_id: int
    user_id: int | None = None
    active: bool
    moderation_status: str  # pending, approved, rejected
    moderation_reason: str | None = None
    moderated_by: int | None = None
    moderated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    printers: list[PrinterResponse] = Field(default_factory=list, description="Список принтеров, для которых подходит этот пресет")

    model_config = ConfigDict(from_attributes=True)


# PresetWithFilament - временно закомментирован из-за проблем с forward references
# TODO: Восстановить после исправления проблемы с OpenAPI
# class PresetWithFilament(PresetResponse):
#     """Schema for Preset with Filament info."""
#     filament: "FilamentResponse"
#     model_config = ConfigDict(from_attributes=True)


class PresetListResponse(BaseModel):
    """Schema for Preset list response."""

    items: list[PresetResponse]
    total: int
    page: int
    size: int
    pages: int


class RecommendedPresetResponse(BaseModel):
    """Schema for recommended preset (weighted average)."""

    filament_id: int
    
    # Calculated optimal values
    extruder_temp: float = Field(..., ge=0, le=400)
    bed_temp: float = Field(..., ge=0, le=150)
    print_speed: float = Field(..., ge=1, le=500)
    travel_speed: float | None = Field(None, ge=1, le=500)
    
    # Advanced settings
    layer_height: float | None = Field(None, ge=0.05, le=1.0)
    first_layer_height: float | None = Field(None, ge=0.05, le=1.0)
    flow_rate: float | None = Field(None, ge=50, le=150)
    fan_speed: int | None = Field(None, ge=0, le=100)
    retraction_length: float | None = Field(None, ge=0, le=10)
    retraction_speed: float | None = Field(None, ge=1, le=100)
    
    # Statistics
    presets_count: int = Field(..., ge=0, description="Number of presets used for calculation")
    avg_rating: float | None = Field(None, ge=0, le=5, description="Average rating of used presets")
    
    model_config = ConfigDict(from_attributes=True)


# PresetWithFilament временно отключен из-за проблем с forward references в OpenAPI
# TODO: Восстановить после исправления проблемы



