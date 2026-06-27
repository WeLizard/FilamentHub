"""Pydantic schemas for Filament."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FilamentVisualSettings(BaseModel):
    """Schema for extended visual settings (только для сайта, не передается в OrcaSlicer)."""

    color_type: Literal["single", "two", "three", "gradient", "transition", "thermochromic"] = Field("single")
    # Тип цвета: одноцветный, двухцветный, трёхцветный, многоцветный градиент, переходной (любой цвет), термохромный (меняет цвет при нагреве)

    colors: list[str] = Field(default_factory=lambda: ["#FFFFFF"], max_length=5)
    # Массив HEX цветов (до 5 цветов для градиента/перехода)
    # Для "single": 1 цвет
    # Для "two": 2 цвета
    # Для "three": 3 цвета
    # Для "gradient": до 5 цветов (градиент)
    # Для "transition": до 5 цветов (переходной цвет, может быть любой)

    finish: Literal["matte", "glossy"] = Field("matte")
    # Финиш поверхности: матовый или глянцевый

    filler: Literal[
        "none", "wood", "carbon", "glitter", "metallic", "luminescent",
        "fibers", "stone", "glass", "pattern1", "pattern2", "pattern3",
        "pattern4", "pattern5", "pattern6", "pattern7", "pattern8",
        "pattern9", "pattern10", "pattern11", "pattern12"
    ] = Field("none")
    # Наполнитель: нет, дерево, CF, глиттер, металлик, люминофор, волокна,
    # камень, стекло, или паттерны 1-12

    transparency: bool = Field(False)
    # Прозрачность: да/нет (True = прозрачный, False = непрозрачный)

    @field_validator("filler", mode="before")
    @classmethod
    def _empty_filler_to_none(cls, v: object) -> object:
        # Если наполнитель не выбран (пустая строка / None), трактуем как "none",
        # а не отклоняем заявку 422 literal_error.
        if v is None or (isinstance(v, str) and not v.strip()):
            return "none"
        return v


class FilamentBase(BaseModel):
    """Base schema for Filament."""

    name: str = Field(..., min_length=1, max_length=200)
    material_type: str = Field(..., max_length=50)
    color_name: str | None = Field(None, max_length=100)
    color_hex: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    # color_hex: базовый цвет, используется в OrcaSlicer
    visual_settings: FilamentVisualSettings | None = Field(None)
    # visual_settings: расширенные визуальные эффекты (только для сайта)
    diameter: float = Field(1.75, ge=1.0, le=3.5)
    density: float | None = Field(None, gt=0)
    price_per_kg: float | None = Field(None, ge=0)
    spool_weight: float | None = Field(None, gt=0)
    empty_spool_weight_g: float | None = Field(None, ge=0)
    description: str | None = None
    availability: Literal["available", "out_of_stock", "discontinued", "coming_soon"] = Field("available")


class FilamentCreate(FilamentBase):
    """Schema for creating Filament."""

    brand_id: int = Field(..., gt=0)


class FilamentUpdate(BaseModel):
    """Schema for updating Filament."""

    name: str | None = Field(None, min_length=1, max_length=200)
    material_type: str | None = Field(None, max_length=50)
    color_name: str | None = Field(None, max_length=100)
    color_hex: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    visual_settings: FilamentVisualSettings | None = None
    diameter: float | None = Field(None, ge=1.0, le=3.5)
    density: float | None = Field(None, gt=0)
    price_per_kg: float | None = Field(None, ge=0)
    spool_weight: float | None = Field(None, gt=0)
    empty_spool_weight_g: float | None = Field(None, ge=0)
    description: str | None = None
    active: bool | None = None
    availability: Literal["available", "out_of_stock", "discontinued", "coming_soon"] | None = None


class FilamentPresetSummary(BaseModel):
    """Compact preset information for catalog cards."""

    id: int
    name: str
    is_official: bool = True
    is_weighted: bool = False
    extruder_temp: float | None = None
    bed_temp: float | None = None
    print_speed: float | None = None
    fan_speed: float | None = None
    flow_rate: float | None = None
    layer_height: float | None = None
    rating: float | None = None
    success_rate: float | None = None
    updated_at: datetime | None = None
    preset_type: Literal["official", "weighted", "community"]

    model_config = ConfigDict(from_attributes=True)


class FilamentResponse(FilamentBase):
    """Schema for Filament response."""

    id: int
    brand_id: int
    brand_name: str | None = Field(None)
    views_count: int | None = 0
    scans_count: int | None = 0
    qr_code: str | None = Field(None)  # Короткий код для QR-кода (например: "FHUB-ABC123")
    active: bool
    created_at: datetime
    updated_at: datetime
    presets_count: int | None = Field(None, ge=0)
    official_presets_count: int | None = Field(None, ge=0)
    community_presets_count: int | None = Field(None, ge=0)
    official_preset: FilamentPresetSummary | None = None
    preset_summaries: list[FilamentPresetSummary] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class FilamentListResponse(BaseModel):
    """Schema for Filament list response."""

    items: list[FilamentResponse]
    total: int
    page: int
    size: int
    pages: int


class CompatiblePrinter(BaseModel):
    """Schema for compatible printer."""

    id: int
    slug: str
    name: str
    manufacturer: str | None = None
    relation_source: str = Field(..., description="Источник связи: via_preset, via_print_profile, etc.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Уверенность в совместимости (0.0-1.0)")

    model_config = ConfigDict(from_attributes=True)


class CompatibleFilament(BaseModel):
    """Schema for compatible filament."""

    id: int
    slug: str
    name: str
    material_type: str
    brand_name: str | None = None
    relation_source: str = Field(..., description="Источник связи: via_preset, via_print_profile, etc.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Уверенность в совместимости (0.0-1.0)")

    model_config = ConfigDict(from_attributes=True)


