"""Pydantic schemas for Filament."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Известные наполнители. Кастомное значение вне этого набора разрешено только
# верифицированному бренду (проверяет эндпоинт филаментов).
KNOWN_FILLERS = frozenset({
    "none", "wood", "carbon", "glitter", "metallic", "luminescent",
    "fibers", "stone", "glass", "pattern1", "pattern2", "pattern3",
    "pattern4", "pattern5", "pattern6", "pattern7", "pattern8",
    "pattern9", "pattern10", "pattern11", "pattern12",
})


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

    filler: str = Field("none", max_length=40)
    # Наполнитель: одно из KNOWN_FILLERS или кастомное значение (только для
    # верифицированного бренда — это проверяет эндпоинт; неверифиц. → только известные)

    transparency: bool = Field(False)
    # Прозрачность: да/нет (True = прозрачный, False = непрозрачный)

    @field_validator("filler", mode="before")
    @classmethod
    def _normalize_filler(cls, v: object) -> object:
        # Пустой наполнитель трактуем как "none" (а не 422).
        if v is None or (isinstance(v, str) and not v.strip()):
            return "none"
        if isinstance(v, str):
            return v.strip()
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
    price_display_unit: Literal["per_kg", "per_spool"] = Field("per_kg")
    line_id: int | None = Field(None, gt=0)  # линейка (группировка вариантов-цвета)


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
    price_display_unit: Literal["per_kg", "per_spool"] | None = None
    line_id: int | None = Field(None, gt=0)  # null — снять с линейки


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
    line_name: str | None = Field(None)  # имя линейки (денормализовано)
    currency: str = Field("RUB")  # валюта бренда (денормализовано)
    price_hidden: bool = Field(False)  # бренд скрыл цену (денормализовано)
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


class FilamentLineCreate(BaseModel):
    """Schema for creating a filament line."""

    name: str = Field(..., min_length=1, max_length=200)


class FilamentLineUpdate(BaseModel):
    """Schema for updating a filament line."""

    name: str = Field(..., min_length=1, max_length=200)


class FilamentLineResponse(BaseModel):
    """Schema for a filament line."""

    id: int
    brand_id: int
    name: str
    filaments_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FilamentImportRowResult(BaseModel):
    """Результат обработки одной строки CSV-импорта."""

    row: int  # номер строки в файле (1-based, без заголовка)
    status: Literal["created", "skipped", "error"]
    name: str | None = None
    filament_id: int | None = None
    message: str | None = None  # код ошибки / причина пропуска


class FilamentImportResult(BaseModel):
    """Сводка импорта материалов из CSV."""

    created: int = 0
    skipped: int = 0
    errors: int = 0
    rows: list[FilamentImportRowResult] = Field(default_factory=list)


class FilamentPaletteVariant(BaseModel):
    """Один цвет-вариант в палитре."""

    color_name: str = Field(..., min_length=1, max_length=100)
    color_hex: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    name: str | None = Field(None, min_length=1, max_length=200)  # переопределение авто-имени


class FilamentPaletteCreate(BaseModel):
    """Создание набора цветов в линейке: общие параметры + список цветов."""

    material_type: str = Field(..., max_length=50)
    visual_settings: FilamentVisualSettings | None = Field(None)
    diameter: float = Field(1.75, ge=1.0, le=3.5)
    density: float | None = Field(None, gt=0)
    price_per_kg: float | None = Field(None, ge=0)
    spool_weight: float | None = Field(None, gt=0)
    empty_spool_weight_g: float | None = Field(None, ge=0)
    description: str | None = None
    availability: Literal["available", "out_of_stock", "discontinued", "coming_soon"] = Field("available")
    price_display_unit: Literal["per_kg", "per_spool"] = Field("per_kg")
    variants: list[FilamentPaletteVariant] = Field(..., min_length=1, max_length=100)


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


