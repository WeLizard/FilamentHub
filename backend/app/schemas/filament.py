"""Pydantic schemas for Filament."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Legacy visual filler values. New clients use ``effects`` but ``filler`` remains
# in the contract so old Orca/plugin and web clients continue to round-trip data.
KNOWN_FILLERS = frozenset({
    "none", "wood", "carbon", "glitter", "metallic", "luminescent",
    "fibers", "stone", "glass", "pattern1", "pattern2", "pattern3",
    "pattern4", "pattern5", "pattern6", "pattern7", "pattern8",
    "pattern9", "pattern10", "pattern11", "pattern12",
})

KNOWN_ADDITIVES = frozenset({
    "aramid_fiber", "bamboo", "basalt_fiber", "carbon_black", "carbon_fiber",
    "carbon_nanotubes", "ceramic", "cork", "glass_beads", "glass_fiber",
    "graphene", "hollow_spheres", "metal_powder", "mineral", "natural_fiber",
    "ptfe", "wood",
})

KNOWN_PROPERTY_CLAIMS = frozenset({
    "antimicrobial", "chemical_resistant", "electrically_conductive",
    "emi_shielding", "esd", "flame_retardant", "food_contact", "foaming",
    "heat_resistant", "lightweight", "low_friction", "magnetically_detectable",
    "uv_resistant", "wear_resistant",
})


def _normalize_code(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower().replace(" ", "_")
    return value


_RAL_CODE_RE = re.compile(r"^(?:RAL[\s_-]*)?(\d{4})$", re.IGNORECASE)


def normalize_ral_code(value: object) -> object:
    """Normalize optional RAL Classic input without claiming palette membership."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return None
    match = _RAL_CODE_RE.fullmatch(stripped)
    return match.group(1) if match else stripped.upper()


class FilamentAdditive(BaseModel):
    """A physical additive or reinforcement declared for a filament."""

    code: str = Field(..., min_length=1, max_length=40)
    content_percent: float | None = Field(None, ge=0, le=100)
    content_basis: Literal["weight", "volume"] | None = None

    _normalize_additive_code = field_validator("code", mode="before")(_normalize_code)


class FilamentPropertyClaim(BaseModel):
    """A functional property claim, optionally accompanied by its evidence label."""

    code: str = Field(..., min_length=1, max_length=40)
    value: str | None = Field(None, max_length=100)
    standard: str | None = Field(None, max_length=100)
    rating: str | None = Field(None, max_length=80)

    _normalize_claim_code = field_validator("code", mode="before")(_normalize_code)


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
    # Legacy primary visual effect. Kept for backward compatibility.

    effects: list[str] = Field(default_factory=list, max_length=12)
    # Independent visual effects. More than one may be rendered at the same time.

    transparency: bool = Field(False)
    # Прозрачность: да/нет (True = прозрачный, False = непрозрачный)

    @field_validator("filler", mode="before")
    @classmethod
    def _normalize_filler(cls, v: object) -> object:
        # Пустой наполнитель трактуем как "none" (а не 422).
        if v is None or (isinstance(v, str) and not v.strip()):
            return "none"
        if isinstance(v, str):
            return _normalize_code(v)
        return v

    @field_validator("effects", mode="before")
    @classmethod
    def _normalize_effects(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        normalized: list[str] = []
        for item in value:
            code = _normalize_code(item)
            if isinstance(code, str) and code and code != "none" and code not in normalized:
                normalized.append(code)
        return normalized

    @model_validator(mode="after")
    def _sync_legacy_filler(self) -> "FilamentVisualSettings":
        if self.effects:
            self.filler = self.effects[0]
        elif self.filler != "none":
            self.effects = [self.filler]
        return self


class FilamentBase(BaseModel):
    """Base schema for Filament."""

    name: str = Field(..., min_length=1, max_length=200)
    material_type: str = Field(..., max_length=50)
    color_name: str | None = Field(None, max_length=100)
    color_hex: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    # color_hex: базовый цвет, используется в OrcaSlicer
    ral_code: str | None = Field(None, pattern=r"^\d{4}$")
    # RAL Classic reference supplied by the contributor; no embedded palette lookup.
    visual_settings: FilamentVisualSettings | None = Field(None)
    # visual_settings: расширенные визуальные эффекты (только для сайта)
    additives: list[FilamentAdditive] = Field(default_factory=list, max_length=24)
    property_claims: list[FilamentPropertyClaim] = Field(default_factory=list, max_length=24)
    diameter: float = Field(1.75, ge=1.0, le=3.5)
    density: float | None = Field(None, gt=0)
    price_per_kg: float | None = Field(None, ge=0)
    spool_weight: float | None = Field(None, gt=0)
    empty_spool_weight_g: float | None = Field(None, ge=0)
    # Рекомендованные вендором диапазоны печати (спека материала), не значения профиля
    recommended_nozzle_temp_min: int | None = Field(None, ge=0, le=600)
    recommended_nozzle_temp_max: int | None = Field(None, ge=0, le=600)
    recommended_bed_temp_min: int | None = Field(None, ge=0, le=300)
    recommended_bed_temp_max: int | None = Field(None, ge=0, le=300)
    required_nozzle_hrc: int | None = Field(None, ge=0, le=500)
    description: str | None = None
    availability: Literal["available", "out_of_stock", "discontinued", "coming_soon"] = Field("available")
    price_display_unit: Literal["per_kg", "per_spool"] = Field("per_kg")
    line_id: int | None = Field(None, gt=0)  # линейка (группировка вариантов-цвета)

    _normalize_ral_code = field_validator("ral_code", mode="before")(normalize_ral_code)


class FilamentCreate(FilamentBase):
    """Schema for creating Filament."""

    brand_id: int = Field(..., gt=0)


class FilamentUpdate(BaseModel):
    """Schema for updating Filament."""

    name: str | None = Field(None, min_length=1, max_length=200)
    material_type: str | None = Field(None, max_length=50)
    color_name: str | None = Field(None, max_length=100)
    color_hex: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    ral_code: str | None = Field(None, pattern=r"^\d{4}$")
    visual_settings: FilamentVisualSettings | None = None
    additives: list[FilamentAdditive] | None = Field(None, max_length=24)
    property_claims: list[FilamentPropertyClaim] | None = Field(None, max_length=24)
    diameter: float | None = Field(None, ge=1.0, le=3.5)
    density: float | None = Field(None, gt=0)
    price_per_kg: float | None = Field(None, ge=0)
    spool_weight: float | None = Field(None, gt=0)
    empty_spool_weight_g: float | None = Field(None, ge=0)
    recommended_nozzle_temp_min: int | None = Field(None, ge=0, le=600)
    recommended_nozzle_temp_max: int | None = Field(None, ge=0, le=600)
    recommended_bed_temp_min: int | None = Field(None, ge=0, le=300)
    recommended_bed_temp_max: int | None = Field(None, ge=0, le=300)
    required_nozzle_hrc: int | None = Field(None, ge=0, le=500)
    description: str | None = None
    active: bool | None = None
    availability: Literal["available", "out_of_stock", "discontinued", "coming_soon"] | None = None
    price_display_unit: Literal["per_kg", "per_spool"] | None = None
    line_id: int | None = Field(None, gt=0)  # null — снять с линейки

    _normalize_ral_code = field_validator("ral_code", mode="before")(normalize_ral_code)


class FilamentPresetSummary(BaseModel):
    """Compact preset information for catalog cards."""

    id: int
    name: str
    is_official: bool = True
    is_weighted: bool = False
    extruder_temp: float | None = None
    bed_temp: float | None = None
    fan_speed: float | None = None
    flow_rate: float | None = None
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
    brand_slug: str | None = Field(None)
    brand_verified: bool = Field(False)
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
    # Which of these materials have a preset for the printer asked about.
    printer_matched_ids: list[int] = []


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
    ral_code: str | None = Field(None, pattern=r"^\d{4}$")
    name: str | None = Field(None, min_length=1, max_length=200)  # переопределение авто-имени

    _normalize_ral_code = field_validator("ral_code", mode="before")(normalize_ral_code)


class FilamentPaletteCreate(BaseModel):
    """Создание набора цветов в линейке: общие параметры + список цветов."""

    material_type: str = Field(..., max_length=50)
    visual_settings: FilamentVisualSettings | None = Field(None)
    additives: list[FilamentAdditive] = Field(default_factory=list, max_length=24)
    property_claims: list[FilamentPropertyClaim] = Field(default_factory=list, max_length=24)
    diameter: float = Field(1.75, ge=1.0, le=3.5)
    density: float | None = Field(None, gt=0)
    price_per_kg: float | None = Field(None, ge=0)
    spool_weight: float | None = Field(None, gt=0)
    empty_spool_weight_g: float | None = Field(None, ge=0)
    recommended_nozzle_temp_min: int | None = Field(None, ge=0, le=600)
    recommended_nozzle_temp_max: int | None = Field(None, ge=0, le=600)
    recommended_bed_temp_min: int | None = Field(None, ge=0, le=300)
    recommended_bed_temp_max: int | None = Field(None, ge=0, le=300)
    required_nozzle_hrc: int | None = Field(None, ge=0, le=500)
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


