"""Pydantic schemas for Filament."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from app.schemas.country_cell import FilamentCountryCellCreate
from app.services.catalog_color_groups import ColorGroupSource, FilamentColorGroup
from app.services.filament_features import canonical_code, known_codes
from app.services.technical_properties import (
    CONDITION_VALUES,
    NUMERIC_CONDITIONS,
    TECHNICAL_PROPERTIES,
    canonical_value,
    technical_property_key,
)

# ``filler`` is the legacy primary visual effect: new clients use ``effects``,
# but old Orca/plugin and web clients still round-trip it.
KNOWN_FILLERS = known_codes("effect")
KNOWN_ADDITIVES = known_codes("additive")
KNOWN_PROPERTY_CLAIMS = known_codes("claim")


def _additive_code(value: object) -> object:
    return canonical_code("additive", value)


def _claim_code(value: object) -> object:
    return canonical_code("claim", value)


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


def normalize_optional_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    return normalized or None


class FilamentAdditive(BaseModel):
    """A physical additive or reinforcement declared for a filament."""

    code: str = Field(..., min_length=1, max_length=40)
    content_percent: float | None = Field(None, ge=0, le=100)
    content_basis: Literal["weight", "volume"] | None = None

    _normalize_additive_code = field_validator("code", mode="before")(_additive_code)


class FilamentPropertyClaim(BaseModel):
    """A functional property claim, optionally accompanied by its evidence label."""

    code: str = Field(..., min_length=1, max_length=40)
    value: str | None = Field(None, max_length=100)
    standard: str | None = Field(None, max_length=100)
    rating: str | None = Field(None, max_length=80)

    _normalize_claim_code = field_validator("code", mode="before")(_claim_code)


class FilamentChemicalGuidance(BaseModel):
    """Product-specific chemical post-processing guidance with visible safety context."""

    name: str = Field(..., min_length=1, max_length=100)
    purpose: str | None = Field(None, min_length=1, max_length=200)
    safety_note: str | None = Field(None, min_length=1, max_length=500)
    hazardous: bool = False

    @field_validator("name", "purpose", "safety_note", mode="before")
    @classmethod
    def _strip_guidance_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _require_hazard_note(self) -> "FilamentChemicalGuidance":
        if self.hazardous and not self.safety_note:
            raise ValueError("safety_note is required for hazardous chemicals")
        return self

_GTIN_RE = re.compile(r"^(?:\d{8}|\d{12,14})$")


def _gtin_check_digit_ok(code: str) -> bool:
    digits = [int(char) for char in code]
    total = sum(
        digit * (1 if index % 2 else 3) for index, digit in enumerate(reversed(digits[:-1]))
    )
    return (10 - total % 10) % 10 == digits[-1]


class FilamentPackaging(BaseModel):
    """One way the manufacturer sells this filament: weight, carrier and codes."""

    model_config = ConfigDict(extra="forbid")

    net_weight_g: float = Field(..., gt=0, le=100000)
    package_type: Literal["spool", "refill", "coil", "multipack"] = "spool"
    # Spools in one multipack; the other values describe one spool of it.
    units_per_package: int | None = Field(None, ge=2, le=100)
    spool_material: Literal["plastic", "cardboard", "metal", "none"] | None = None
    empty_spool_weight_g: float | None = Field(None, ge=0, le=20000)
    spool_outer_diameter_mm: float | None = Field(None, gt=0, le=2000)
    spool_width_mm: float | None = Field(None, gt=0, le=2000)
    spool_core_diameter_mm: float | None = Field(None, gt=0, le=2000)
    gross_weight_g: float | None = Field(None, gt=0, le=200000)
    sku: str | None = Field(None, max_length=100)
    ean: str | None = Field(None, max_length=14)

    _normalize_text = field_validator("sku", "ean", mode="before")(normalize_optional_text)

    @field_validator("ean")
    @classmethod
    def _valid_gtin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _GTIN_RE.fullmatch(value) or not _gtin_check_digit_ok(value):
            raise ValueError("EAN/GTIN must be 8, 12, 13 or 14 digits with a valid check digit")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "FilamentPackaging":
        if (self.package_type == "multipack") != (self.units_per_package is not None):
            raise ValueError("units_per_package is set exactly for a multipack")
        spool_values = (
            self.empty_spool_weight_g,
            self.spool_outer_diameter_mm,
            self.spool_width_mm,
            self.spool_core_diameter_mm,
        )
        if self.package_type in ("refill", "coil") and (
            any(value for value in spool_values) or self.spool_material not in (None, "none")
        ):
            raise ValueError("a refill or coil has no spool")
        if (
            self.spool_outer_diameter_mm is not None
            and self.spool_core_diameter_mm is not None
            and self.spool_core_diameter_mm > self.spool_outer_diameter_mm
        ):
            raise ValueError("spool core diameter exceeds outer diameter")
        if self.gross_weight_g is not None:
            contents = (self.net_weight_g + (self.empty_spool_weight_g or 0)) * (
                self.units_per_package or 1
            )
            if self.gross_weight_g < contents:
                raise ValueError("gross weight is below the package contents")
        return self

    @property
    def key(self) -> str:
        return packaging_key(self.model_dump())


def packaging_key(item: dict) -> str:
    """Identity of a packaging within one filament, also used to address its evidence.

    The same weight on a plastic and on a cardboard spool are two packagings.
    """
    weight = float(item.get("net_weight_g") or 0)
    units = item.get("units_per_package")
    material = item.get("spool_material")
    return (
        f"{item.get('package_type') or 'spool'}:{weight:g}"
        + (f"x{units}" if units else "")
        + (f":{material}" if material else "")
    )


def _unique_packagings(value: list[FilamentPackaging] | None) -> list[FilamentPackaging] | None:
    if value is not None:
        keys = [item.key for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("each packaging must differ in type, weight, unit count or spool")
    return value


def main_packaging_values(packagings: list[FilamentPackaging]) -> dict[str, float]:
    """Single-spool card fields taken from the first listed packaging.

    Spoolman-compatible clients, the calculator and Orca read one spool weight;
    a manufacturer listing several sizes names its main one first.
    """
    first = next((item for item in packagings if item.package_type != "multipack"), None)
    if first is None:
        return {}
    values = {
        "spool_weight": first.net_weight_g,
        "empty_spool_weight_g": first.empty_spool_weight_g,
        "spool_outer_diameter_mm": first.spool_outer_diameter_mm,
        "spool_width_mm": first.spool_width_mm,
        "spool_core_diameter_mm": first.spool_core_diameter_mm,
        "packaged_gross_weight_g": first.gross_weight_g,
    }
    return {field: value for field, value in values.items() if value is not None}



class FilamentTechnicalProperty(BaseModel):
    """One measured value from the manufacturer's data sheet, as written there."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=40)
    value: float | None = None
    min: float | None = None
    max: float | None = None
    # "52 ± 3": the published spread around ``value``.
    tolerance: float | None = Field(None, ge=0)
    unit: str = Field(..., min_length=1, max_length=20)
    standard: str | None = Field(None, max_length=60)
    conditions: dict[str, str | float] = Field(default_factory=dict)
    # Derived: the value in the property's canonical unit when it converts exactly.
    canonical_value: float | None = None
    canonical_min: float | None = None
    canonical_max: float | None = None

    _normalize_standard = field_validator("standard", mode="before")(normalize_optional_text)

    @model_validator(mode="after")
    def _known_and_consistent(self) -> "FilamentTechnicalProperty":
        reference = TECHNICAL_PROPERTIES.get(self.code)
        if reference is None:
            raise ValueError(f"unknown technical property: {self.code}")
        if self.unit not in reference.units:
            raise ValueError(f"{self.code} is not measured in {self.unit}")
        single = self.value is not None
        ranged = self.min is not None or self.max is not None
        if single == ranged:
            raise ValueError("give either a value or a min-max range")
        if ranged and (self.min is None or self.max is None or self.min > self.max):
            raise ValueError("a range needs min not above max")
        if self.tolerance is not None and not single:
            raise ValueError("a tolerance belongs to a single value")
        for name, condition in self.conditions.items():
            if name not in reference.conditions:
                raise ValueError(f"{self.code} has no condition {name}")
            if name in NUMERIC_CONDITIONS:
                if isinstance(condition, str) or condition <= 0:
                    raise ValueError(f"{name} must be a positive number")
            elif condition not in CONDITION_VALUES[name]:
                raise ValueError(f"{name} cannot be {condition}")
        self.canonical_value = canonical_value(self.code, self.unit, self.value)
        self.canonical_min = canonical_value(self.code, self.unit, self.min)
        self.canonical_max = canonical_value(self.code, self.unit, self.max)
        return self

    @property
    def key(self) -> str:
        return technical_property_key(self.model_dump())


def _unique_technical_properties(
    value: list[FilamentTechnicalProperty] | None,
) -> list[FilamentTechnicalProperty] | None:
    if value is not None:
        keys = [item.key for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("a property is listed twice with the same conditions and standard")
    return value


class FilamentTechnicalDataContract(BaseModel):
    drying_required: bool | None = None
    drying_temperature_c: float | None = Field(None, ge=0, le=200)
    drying_duration_hours: float | None = Field(None, ge=0.25, le=336)
    enclosure_requirement: Literal["none", "passive", "active"] | None = None
    chamber_temperature_c: float | None = Field(None, ge=0, le=150)
    storage_temperature_min_c: float | None = Field(None, ge=-100, le=200)
    storage_temperature_max_c: float | None = Field(None, ge=-100, le=200)
    storage_relative_humidity_max_percent: float | None = Field(None, ge=0, le=100)
    storage_relative_humidity_target_percent: float | None = Field(None, ge=0, le=100)
    spool_weight: float | None = Field(None, gt=0)
    empty_spool_weight_g: float | None = Field(None, ge=0)
    spool_outer_diameter_mm: float | None = Field(None, gt=0, le=2000)
    spool_width_mm: float | None = Field(None, gt=0, le=2000)
    spool_core_diameter_mm: float | None = Field(None, gt=0, le=2000)
    packaged_gross_weight_g: float | None = Field(None, gt=0, le=100000)
    recommended_nozzle_temp_min: int | None = Field(None, ge=0, le=600)
    recommended_nozzle_temp_max: int | None = Field(None, ge=0, le=600)
    recommended_bed_temp_min: int | None = Field(None, ge=0, le=300)
    recommended_bed_temp_max: int | None = Field(None, ge=0, le=300)
    packagings: list[FilamentPackaging] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_consistency(self) -> "FilamentTechnicalDataContract":
        single_weights = {
            item.net_weight_g for item in self.packagings if item.package_type != "multipack"
        }
        if (
            self.spool_weight is not None
            and single_weights
            and self.spool_weight not in single_weights
        ):
            raise ValueError("the main spool weight must be one of the listed packagings")
        drying_pair = (self.drying_temperature_c, self.drying_duration_hours)
        if (drying_pair[0] is None) != (drying_pair[1] is None):
            raise ValueError("drying temperature and duration must be provided together")
        if self.drying_required is True and drying_pair[0] is None:
            raise ValueError("drying temperature and duration are required")
        if self.drying_required is False and drying_pair[0] is not None:
            raise ValueError("drying parameters contradict an explicit not-required declaration")
        if self.enclosure_requirement == "active" and self.chamber_temperature_c is None:
            raise ValueError("chamber temperature is required for an actively heated chamber")

        storage_pair = (self.storage_temperature_min_c, self.storage_temperature_max_c)
        if (storage_pair[0] is None) != (storage_pair[1] is None):
            raise ValueError("storage temperature range requires both bounds")
        if storage_pair[0] is not None and storage_pair[0] > storage_pair[1]:
            raise ValueError("storage temperature minimum exceeds maximum")
        if (
            self.storage_relative_humidity_max_percent is not None
            and self.storage_relative_humidity_target_percent is not None
            and self.storage_relative_humidity_target_percent
            > self.storage_relative_humidity_max_percent
        ):
            raise ValueError("storage humidity target exceeds maximum")
        if (
            self.spool_outer_diameter_mm is not None
            and self.spool_core_diameter_mm is not None
            and self.spool_core_diameter_mm > self.spool_outer_diameter_mm
        ):
            raise ValueError("spool core diameter exceeds outer diameter")
        if (
            self.recommended_nozzle_temp_min is not None
            and self.recommended_nozzle_temp_max is not None
            and self.recommended_nozzle_temp_min > self.recommended_nozzle_temp_max
        ):
            raise ValueError("recommended nozzle temperature minimum exceeds maximum")
        if (
            self.recommended_bed_temp_min is not None
            and self.recommended_bed_temp_max is not None
            and self.recommended_bed_temp_min > self.recommended_bed_temp_max
        ):
            raise ValueError("recommended bed temperature minimum exceeds maximum")
        known_contents_weight = sum(
            value for value in (self.spool_weight, self.empty_spool_weight_g) if value is not None
        )
        if (
            self.packaged_gross_weight_g is not None
            and known_contents_weight
            and self.packaged_gross_weight_g < known_contents_weight
        ):
            raise ValueError("packaged gross weight is below known spool contents")
        return self


def normalize_bed_adhesives(value: object) -> object:
    if value is None:
        return []
    if not isinstance(value, list):
        return value
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            return value
        label = item.strip()
        key = label.casefold()
        if not label or key in seen:
            continue
        if len(label) > 100:
            raise ValueError("bed adhesive labels must not exceed 100 characters")
        seen.add(key)
        normalized.append(label)
    return normalized


class FilamentVisualSettings(BaseModel):
    """Schema for extended visual settings (только для сайта, не передается в OrcaSlicer)."""

    color_type: Literal[
        "single", "two", "three", "four", "gradient", "transition", "thermochromic"
    ] = Field("single")
    # Тип цвета: одноцветный, двух-, трёх-, четырёхцветный (цвета в сечении нити), многоцветный градиент, переходной (любой цвет), термохромный (меняет цвет при нагреве)

    colors: list[str] = Field(default_factory=lambda: ["#FFFFFF"], max_length=5)
    # Массив HEX цветов (до 5 цветов для градиента/перехода)
    # Для "single": 1 цвет
    # Для "two": 2 цвета
    # Для "three": 3 цвета
    # Для "four": 4 цвета
    # Для "gradient": до 5 цветов (градиент)
    # Для "transition": до 5 цветов (переходной цвет, может быть любой)

    finish: Literal["matte", "satin", "glossy", "silk"] = Field("matte")
    # Финиш поверхности: матовый, сатиновый (полуматовый), глянцевый или шёлковый

    filler: str = Field("none", max_length=40)
    # Legacy primary visual effect. Kept for backward compatibility.

    effects: list[str] = Field(default_factory=list, max_length=12)
    # Independent visual effects. More than one may be rendered at the same time.

    transparency: bool = Field(False)
    # Прозрачность: да/нет (True = прозрачный, False = непрозрачный)

    @field_validator("color_type", mode="before")
    @classmethod
    def _normalize_color_type(cls, value: object) -> object:
        return canonical_code("color_type", value)

    @field_validator("finish", mode="before")
    @classmethod
    def _normalize_finish(cls, value: object) -> object:
        return canonical_code("finish", value)

    @field_validator("filler", mode="before")
    @classmethod
    def _normalize_filler(cls, v: object) -> object:
        # Пустой наполнитель трактуем как "none" (а не 422).
        if v is None or (isinstance(v, str) and not v.strip()):
            return "none"
        return canonical_code("effect", v)

    @field_validator("effects", mode="before")
    @classmethod
    def _normalize_effects(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        normalized: list[str] = []
        for item in value:
            code = canonical_code("effect", item)
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
    color_group: FilamentColorGroup | None = None
    color_group_source: ColorGroupSource = "auto"
    ral_code: str | None = Field(None, pattern=r"^\d{4}$")
    # RAL Classic reference supplied by the contributor; no embedded palette lookup.
    visual_settings: FilamentVisualSettings | None = Field(None)
    # visual_settings: расширенные визуальные эффекты (только для сайта)
    additives: list[FilamentAdditive] = Field(default_factory=list, max_length=24)
    property_claims: list[FilamentPropertyClaim] = Field(default_factory=list, max_length=24)
    packagings: list[FilamentPackaging] = Field(default_factory=list, max_length=12)
    technical_properties: list[FilamentTechnicalProperty] = Field(
        default_factory=list, max_length=80
    )
    diameter: float = Field(1.75, ge=1.0, le=3.5)
    density: float | None = Field(None, gt=0)
    drying_required: bool | None = None
    drying_temperature_c: float | None = Field(None, ge=0, le=200)
    drying_duration_hours: float | None = Field(None, ge=0.25, le=336)
    storage_temperature_min_c: float | None = Field(None, ge=-100, le=200)
    storage_temperature_max_c: float | None = Field(None, ge=-100, le=200)
    storage_relative_humidity_max_percent: float | None = Field(None, ge=0, le=100)
    storage_relative_humidity_target_percent: float | None = Field(None, ge=0, le=100)
    storage_airtight_required: bool | None = None
    storage_desiccant_recommended: bool | None = None
    storage_light_protection_required: bool | None = None
    storage_after_opening_guidance: str | None = Field(None, max_length=1000)
    unopened_shelf_life_months: int | None = Field(None, ge=1, le=1200)
    enclosure_requirement: Literal["none", "passive", "active"] | None = None
    chamber_temperature_c: float | None = Field(None, ge=0, le=150)
    bed_adhesives: list[str] = Field(default_factory=list, max_length=12)
    post_processing_chemicals: list[FilamentChemicalGuidance] = Field(
        default_factory=list, max_length=12
    )
    price_per_kg: float | None = Field(None, ge=0)
    spool_weight: float | None = Field(None, gt=0)
    empty_spool_weight_g: float | None = Field(None, ge=0)
    spool_outer_diameter_mm: float | None = Field(None, gt=0, le=2000)
    spool_width_mm: float | None = Field(None, gt=0, le=2000)
    spool_core_diameter_mm: float | None = Field(None, gt=0, le=2000)
    packaged_gross_weight_g: float | None = Field(None, gt=0, le=100000)
    technical_data_source_ref: str | None = Field(None, max_length=500)
    technical_data_version: str | None = Field(None, max_length=100)
    technical_data_effective_date: date | None = None
    # Рекомендованные вендором диапазоны печати (спека материала), не значения профиля
    recommended_nozzle_temp_min: int | None = Field(None, ge=0, le=600)
    recommended_nozzle_temp_max: int | None = Field(None, ge=0, le=600)
    recommended_bed_temp_min: int | None = Field(None, ge=0, le=300)
    recommended_bed_temp_max: int | None = Field(None, ge=0, le=300)
    required_nozzle_hrc: int | None = Field(None, ge=0, le=500)
    description: str | None = None
    availability: Literal["available", "out_of_stock", "discontinued", "coming_soon"] = Field(
        "available"
    )
    price_display_unit: Literal["per_kg", "per_spool"] = Field("per_kg")
    line_id: int | None = Field(None, gt=0)  # линейка (группировка вариантов-цвета)

    _normalize_ral_code = field_validator("ral_code", mode="before")(normalize_ral_code)
    _normalize_bed_adhesives = field_validator("bed_adhesives", mode="before")(
        normalize_bed_adhesives
    )
    _unique_packagings = field_validator("packagings")(_unique_packagings)
    _unique_technical_properties = field_validator("technical_properties")(
        _unique_technical_properties
    )
    _normalize_technical_text = field_validator(
        "storage_after_opening_guidance",
        "technical_data_source_ref",
        "technical_data_version",
        mode="before",
    )(normalize_optional_text)


class FilamentCreate(FilamentBase):
    """Schema for creating Filament."""

    brand_id: int = Field(..., gt=0)
    # A territorial organization creates the shared catalog record and its
    # market data together.  The nested cell is optional so community and
    # global contributors keep the same open-catalog endpoint.
    country_cell: FilamentCountryCellCreate | None = None

    @model_validator(mode="after")
    def validate_handling_parameters(self) -> FilamentCreate:
        for field, value in main_packaging_values(self.packagings).items():
            if getattr(self, field) is None:
                setattr(self, field, value)
        FilamentTechnicalDataContract.model_validate(self.model_dump())
        return self


class FilamentUpdate(BaseModel):
    """Schema for updating Filament."""

    name: str | None = Field(None, min_length=1, max_length=200)
    material_type: str | None = Field(None, max_length=50)
    color_name: str | None = Field(None, max_length=100)
    color_hex: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    color_group: FilamentColorGroup | None = None
    color_group_source: ColorGroupSource | None = None
    ral_code: str | None = Field(None, pattern=r"^\d{4}$")
    visual_settings: FilamentVisualSettings | None = None
    additives: list[FilamentAdditive] | None = Field(None, max_length=24)
    property_claims: list[FilamentPropertyClaim] | None = Field(None, max_length=24)
    packagings: list[FilamentPackaging] | None = Field(None, max_length=12)
    technical_properties: list[FilamentTechnicalProperty] | None = Field(None, max_length=80)
    diameter: float | None = Field(None, ge=1.0, le=3.5)
    density: float | None = Field(None, gt=0)
    drying_required: bool | None = None
    drying_temperature_c: float | None = Field(None, ge=0, le=200)
    drying_duration_hours: float | None = Field(None, ge=0.25, le=336)
    storage_temperature_min_c: float | None = Field(None, ge=-100, le=200)
    storage_temperature_max_c: float | None = Field(None, ge=-100, le=200)
    storage_relative_humidity_max_percent: float | None = Field(None, ge=0, le=100)
    storage_relative_humidity_target_percent: float | None = Field(None, ge=0, le=100)
    storage_airtight_required: bool | None = None
    storage_desiccant_recommended: bool | None = None
    storage_light_protection_required: bool | None = None
    storage_after_opening_guidance: str | None = Field(None, max_length=1000)
    unopened_shelf_life_months: int | None = Field(None, ge=1, le=1200)
    enclosure_requirement: Literal["none", "passive", "active"] | None = None
    chamber_temperature_c: float | None = Field(None, ge=0, le=150)
    bed_adhesives: list[str] | None = Field(None, max_length=12)
    post_processing_chemicals: list[FilamentChemicalGuidance] | None = Field(None, max_length=12)
    price_per_kg: float | None = Field(None, ge=0)
    spool_weight: float | None = Field(None, gt=0)
    empty_spool_weight_g: float | None = Field(None, ge=0)
    spool_outer_diameter_mm: float | None = Field(None, gt=0, le=2000)
    spool_width_mm: float | None = Field(None, gt=0, le=2000)
    spool_core_diameter_mm: float | None = Field(None, gt=0, le=2000)
    packaged_gross_weight_g: float | None = Field(None, gt=0, le=100000)
    technical_data_source_ref: str | None = Field(None, max_length=500)
    technical_data_version: str | None = Field(None, max_length=100)
    technical_data_effective_date: date | None = None
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
    _normalize_bed_adhesives = field_validator("bed_adhesives", mode="before")(
        normalize_bed_adhesives
    )
    _unique_packagings = field_validator("packagings")(_unique_packagings)
    _unique_technical_properties = field_validator("technical_properties")(
        _unique_technical_properties
    )
    _normalize_technical_text = field_validator(
        "storage_after_opening_guidance",
        "technical_data_source_ref",
        "technical_data_version",
        mode="before",
    )(normalize_optional_text)

    @model_validator(mode="after")
    def validate_handling_parameters(self) -> FilamentUpdate:
        if self.enclosure_requirement == "active" and self.chamber_temperature_c is None:
            raise ValueError("chamber temperature is required for an actively heated chamber")
        return self


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


class FilamentAdditionalProperty(BaseModel):
    """A reviewed manufacturer fact that has no dedicated catalog field."""

    model_config = ConfigDict(extra="forbid")

    property_name: str = Field(min_length=1, max_length=120)
    value_summary: str = Field(min_length=1, max_length=500)
    source_urls: list[str] = Field(min_length=1, max_length=10)
    kind: Literal["direct", "inferred"]

    @field_validator("property_name", "value_summary")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("source_urls")
    @classmethod
    def validate_source_urls(cls, value: list[str]) -> list[str]:
        parsed = TypeAdapter(list[AnyHttpUrl]).validate_python(value)
        if any(url.username is not None or url.password is not None for url in parsed):
            raise ValueError("Source URLs must not contain credentials")
        return [str(url) for url in parsed]


class FilamentResponse(FilamentBase):
    """Schema for Filament response."""

    id: int
    slug: str
    brand_id: int
    # Derived from material_type: polymer family and reference subtype; null
    # when the manufacturer's type names no known polymer or no known subtype.
    base_material_type: str | None = None
    material_subtype: str | None = None
    # Wiki article about the material or its base; may be unpublished.
    material_wiki_slug: str | None = None
    additional_properties: list[FilamentAdditionalProperty] = Field(default_factory=list)
    contributed_by_organization_id: int | None = None
    brand_name: str | None = Field(None)
    brand_slug: str | None = Field(None)
    brand_verified: bool = Field(False)
    line_name: str | None = Field(None)  # имя линейки (денормализовано)
    currency: str | None = Field(None)  # валюта рынка или бренда (денормализовано)
    price_hidden: bool = Field(False)  # бренд скрыл цену (денормализовано)
    views_count: int | None = 0
    scans_count: int | None = 0
    qr_code: str | None = Field(None)  # Короткий код для QR-кода (например: "FHUB-ABC123")
    technical_data_last_verified_by: (
        Literal["manufacturer_representative", "administrator", "legacy_catalog"] | None
    ) = None
    technical_data_last_verified_at: datetime | None = None
    active: bool
    created_at: datetime
    updated_at: datetime
    presets_count: int | None = Field(None, ge=0)
    official_presets_count: int | None = Field(None, ge=0)
    community_presets_count: int | None = Field(None, ge=0)
    official_preset: FilamentPresetSummary | None = None
    preset_summaries: list[FilamentPresetSummary] = Field(default_factory=list)

    # Заполнено, когда сведения подставлены из ячейки страны: витрина обязана
    # подписать такую цену как рекомендованную для этого рынка, а не как нашу.
    market_country: str | None = None
    # Актуальность карточки в этой стране. Не путать с `availability`: то
    # глобальное состояние товара у производителя.
    market_availability: str | None = None
    market_note: str | None = None
    product_url: str | None = None
    purchase_links: list[dict[str, str]] | None = None

    model_config = ConfigDict(from_attributes=True)


class MaterialTypeGroup(BaseModel):
    """Material types of one base polymer; ``base`` is null for unrecognised types."""

    base: str | None
    types: list[str]
    filament_count: int = 0


class FilamentListResponse(BaseModel):
    """Schema for Filament list response."""

    items: list[FilamentResponse]
    total: int
    page: int
    size: int
    pages: int
    # Which of these materials have a preset for the printer asked about.
    printer_matched_ids: list[int] = []


class FilamentCommonEditRequest(BaseModel):
    """A verified user asks the responsible brand organization for a correction."""

    message: str = Field(..., min_length=5, max_length=1000)


class FilamentCommonEditRequestResponse(BaseModel):
    recipients: int = Field(..., ge=0)


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
    status: Literal["created", "updated", "skipped", "error"]
    name: str | None = None
    material_type: str | None = None
    color_name: str | None = None
    filament_id: int | None = None
    message: str | None = None  # код ошибки / причина пропуска


class FilamentImportResult(BaseModel):
    """Сводка импорта материалов из CSV."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    rows: list[FilamentImportRowResult] = Field(default_factory=list)


class FilamentImportPreviewResult(FilamentImportResult):
    """Non-persistent CSV plan that may be corrected before confirmation."""

    file_name: str
    source_rows: list[dict[str, str]] = Field(default_factory=list)
    confirmation_token: str
    confirmation_expires_at: datetime


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
    drying_required: bool | None = None
    drying_temperature_c: float | None = Field(None, ge=0, le=200)
    drying_duration_hours: float | None = Field(None, ge=0.25, le=336)
    enclosure_requirement: Literal["none", "passive", "active"] | None = None
    chamber_temperature_c: float | None = Field(None, ge=0, le=150)
    bed_adhesives: list[str] = Field(default_factory=list, max_length=12)
    post_processing_chemicals: list[FilamentChemicalGuidance] = Field(
        default_factory=list, max_length=12
    )
    price_per_kg: float | None = Field(None, ge=0)
    spool_weight: float | None = Field(None, gt=0)
    empty_spool_weight_g: float | None = Field(None, ge=0)
    recommended_nozzle_temp_min: int | None = Field(None, ge=0, le=600)
    recommended_nozzle_temp_max: int | None = Field(None, ge=0, le=600)
    recommended_bed_temp_min: int | None = Field(None, ge=0, le=300)
    recommended_bed_temp_max: int | None = Field(None, ge=0, le=300)
    required_nozzle_hrc: int | None = Field(None, ge=0, le=500)
    description: str | None = None
    availability: Literal["available", "out_of_stock", "discontinued", "coming_soon"] = Field(
        "available"
    )
    price_display_unit: Literal["per_kg", "per_spool"] = Field("per_kg")
    country_cell: FilamentCountryCellCreate | None = None

    variants: list[FilamentPaletteVariant] = Field(..., min_length=1, max_length=100)

    _normalize_bed_adhesives = field_validator("bed_adhesives", mode="before")(
        normalize_bed_adhesives
    )

    @model_validator(mode="after")
    def validate_handling_parameters(self) -> FilamentPaletteCreate:
        if self.drying_required is True and (
            self.drying_temperature_c is None or self.drying_duration_hours is None
        ):
            raise ValueError("drying temperature and duration are required")
        if self.enclosure_requirement == "active" and self.chamber_temperature_c is None:
            raise ValueError("chamber temperature is required for an actively heated chamber")
        return self


class CompatiblePrinter(BaseModel):
    """Schema for compatible printer."""

    id: int
    slug: str
    name: str
    manufacturer: str | None = None
    relation_source: str = Field(
        ..., description="Источник связи: via_preset, via_print_profile, etc."
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Уверенность в совместимости (0.0-1.0)"
    )

    model_config = ConfigDict(from_attributes=True)


class CompatibleFilament(BaseModel):
    """Schema for compatible filament."""

    id: int
    slug: str
    name: str
    material_type: str
    brand_name: str | None = None
    relation_source: str = Field(
        ..., description="Источник связи: via_preset, via_print_profile, etc."
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Уверенность в совместимости (0.0-1.0)"
    )

    model_config = ConfigDict(from_attributes=True)
