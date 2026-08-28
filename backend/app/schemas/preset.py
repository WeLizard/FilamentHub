"""Pydantic schemas for Preset."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.printer import PrinterResponse

if TYPE_CHECKING:
    pass


class PresetBase(BaseModel):
    """Base schema for Preset."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    is_official: bool = Field(False)
    is_weighted: bool = Field(False, description="Динамический взвешенный пресет, автоматически пересчитывается системой")

    # Filament settings (material scope). print/travel speed и layer heights —
    # process-scope (Orca print profile), не свойства филамента: на пресете их нет.
    extruder_temp: float = Field(..., ge=0, le=1500)
    bed_temp: float = Field(..., ge=0, le=300)
    flow_rate: float | None = Field(None, gt=0, le=200)
    # flow_rate: % от стандартного

    # Cooling
    fan_speed: int | None = Field(None, ge=0, le=100)
    # fan_speed: 0-100%

    # Retraction
    retraction_length: float | None = Field(None, ge=0, le=20)
    retraction_speed: float | None = Field(None, ge=0, le=200)

    # Extended OrcaSlicer parameters (JSON)
    orcaslicer_settings: dict[str, Any] | None = Field(None, description="Расширенные параметры OrcaSlicer в формате JSON")

    # Rating
    rating: float | None = Field(None, ge=1, le=5)
    success_rate: float | None = Field(None, ge=0.0, le=100.0, description="Процент успешных печатей (0-100)")
    usage_count: int = Field(0, ge=0)

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Preset name cannot be empty")
        return normalized

class PresetCreate(PresetBase):
    """Schema for creating Preset."""

    filament_id: int = Field(..., gt=0)
    user_id: int | None = Field(None, gt=0)  # Автоматически заполняется из токена
    printer_ids: list[int] = Field(default_factory=list, description="Список ID принтеров, для которых подходит этот пресет")


class OfficialPresetCreate(PresetCreate):
    """Create a distinct Organization-owned official preset."""

    is_official: Literal[True] = True
    source_preset_id: int | None = Field(
        None,
        gt=0,
        description="Optional personal/community preset used only as source provenance",
    )


class PresetUpdate(BaseModel):
    """Schema for updating Preset."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    is_official: bool | None = None

    # Filament (для активации черновиков/заготовок)
    filament_id: int | None = Field(None, gt=0, description="ID филамента (для привязки черновика)")

    # Filament settings (material scope)
    extruder_temp: float | None = Field(None, ge=0, le=1500)
    bed_temp: float | None = Field(None, ge=0, le=300)
    flow_rate: float | None = Field(None, gt=0, le=200)
    fan_speed: int | None = Field(None, ge=0, le=100)
    retraction_length: float | None = Field(None, ge=0, le=20)
    retraction_speed: float | None = Field(None, ge=0, le=200)

    # Extended OrcaSlicer parameters (JSON)
    orcaslicer_settings: dict[str, Any] | None = Field(None, description="Расширенные параметры OrcaSlicer в формате JSON")

    # Rating
    rating: float | None = Field(None, ge=1, le=5)
    active: bool | None = None
    # УДАЛЕНО: sync_enabled - теперь управляется через user_saved_presets.sync

    # Printers
    printer_ids: list[int] | None = Field(None, description="Список ID принтеров, для которых подходит этот пресет")

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Preset name cannot be cleared")
        normalized = value.strip()
        if not normalized:
            raise ValueError("Preset name cannot be empty")
        return normalized

    @field_validator("extruder_temp", "bed_temp")
    @classmethod
    def required_temperatures_cannot_be_cleared(cls, value: float | None) -> float | None:
        if value is None:
            raise ValueError("Preset temperatures cannot be cleared")
        return value


class PresetActivateRequest(BaseModel):
    """Schema for activating a draft preset."""

    filament_id: int = Field(..., gt=0, description="ID филамента для привязки")


class PresetResponse(PresetBase):
    """Schema for Preset response."""

    id: int
    # КРИТИЧНО: для черновиков из OrcaSlicer filament_id может быть NULL
    filament_id: int | None
    user_id: int | None = None
    organization_id: int | None = None
    created_by_user_id: int | None = None
    derived_from_preset_id: int | None = None
    derived_from_version_id: int | None = None
    active: bool
    moderation_status: str  # pending, approved, rejected
    # УДАЛЕНО: sync_enabled - теперь управляется через user_saved_presets.sync
    external_id: str | None = Field(None, description="ID пресета в OrcaSlicer (для маппинга)")
    source: str | None = Field(None, description="Источник пресета (orcaslicer, user, system, etc.)")
    moderation_reason: str | None = None
    moderated_by: int | None = None
    moderated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # Present on the authenticated Orca desired-state manifest. Other preset
    # responses leave these fields null.
    selected_version_id: int | None = None
    selected_version_number: int | None = None
    latest_version_id: int | None = None
    latest_version_number: int | None = None
    update_available: bool = False
    printers: list[PrinterResponse] = Field(default_factory=list, description="Список принтеров, для которых подходит этот пресет")

    @classmethod
    def model_validate_public(cls, obj: Any) -> PresetResponse:
        """Validate a catalog response and remove owner-only Orca evidence."""
        response = cls.model_validate(obj)
        if isinstance(response.orcaslicer_settings, dict):
            from app.services.preset_publication import public_orca_settings

            response.orcaslicer_settings = public_orca_settings(
                response.orcaslicer_settings
            )
        return response

    model_config = ConfigDict(from_attributes=True)


class PresetDraftSuggestion(BaseModel):
    """One review value with honest provenance."""

    value: str | float
    source: str
    confidence: str
    direct: bool = False


class PresetDraftCatalogMatch(BaseModel):
    id: int
    name: str
    brand_id: int | None = None
    material_type: str | None = None
    color_name: str | None = None
    confidence: str = "possible"
    reasons: list[str] = Field(default_factory=list)


class PresetDraftAnalysisResponse(BaseModel):
    """Small review projection for an imported Orca draft."""

    preset_id: int
    evidence_kind: str
    suggestions: dict[str, PresetDraftSuggestion] = Field(default_factory=dict)
    brand_match: PresetDraftCatalogMatch | None = None
    filament_matches: list[PresetDraftCatalogMatch] = Field(default_factory=list)
    confirmed_fields: list[str] = Field(default_factory=list)
    suggested_fields: list[str] = Field(default_factory=list)
    preset_readiness_percent: int = Field(ge=0, le=100)
    catalog_readiness_percent: int = Field(ge=0, le=100)
    technical_settings_count: int = Field(ge=0)
    preset_decisions: list[str] = Field(default_factory=list)
    catalog_decisions: list[str] = Field(default_factory=list)
    review_state: str
    generic_source: bool = False
    similar_import_users: int = Field(
        default=0,
        ge=0,
        description="Independent private imports with the same anonymous candidate signature",
    )


class PresetDraftMetricRequest(BaseModel):
    """One categorical UI funnel event; identifiers and arbitrary metadata are forbidden."""

    event_type: Literal[
        "review_opened",
        "important_field_confirmed",
        "filament_matched_or_created",
        "duplicate_prevented",
    ]


class PresetDraftQueueResponse(BaseModel):
    """Review state for the current user's visible draft queue."""

    items: list[PresetDraftAnalysisResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    ready: int = Field(ge=0)
    almost_ready: int = Field(ge=0)
    needs_decision: int = Field(ge=0)
    ambiguous: int = Field(ge=0)



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

    # Calculated optimal values (material scope only)
    extruder_temp: float = Field(..., ge=0, le=1500)
    bed_temp: float = Field(..., ge=0, le=300)
    flow_rate: float | None = Field(None, gt=0, le=200)
    fan_speed: int | None = Field(None, ge=0, le=100)
    retraction_length: float | None = Field(None, ge=0, le=20)
    retraction_speed: float | None = Field(None, ge=0, le=200)

    # Statistics
    presets_count: int = Field(..., ge=0, description="Number of presets used for calculation")
    avg_rating: float | None = Field(None, ge=0, le=5, description="Average rating of used presets")

    model_config = ConfigDict(from_attributes=True)


class RecommendedPresetCompatibilityCheck(BaseModel):
    """One explainable hard requirement for a recommended material preset."""

    kind: Literal["hotend_temperature", "nozzle_hrc"]
    status: Literal["compatible", "incompatible", "unknown"]
    required_value: float = Field(..., gt=0)
    available_value: float | None = Field(None, gt=0)
    unit: Literal["°C", "HRC"]


class RecommendedPresetItem(BaseModel):
    """A preset ranked by fit, factual compatibility, and public evidence."""

    preset: PresetResponse
    match_score: float = Field(..., ge=0.0, le=1.2, description="Base tier score plus ranking bonuses")
    match_reason: str = Field(
        ...,
        description="exact_match | same_model | same_family | same_manufacturer | compatible_specs",
    )
    compatibility_status: Literal["compatible", "incompatible", "unknown"] = "unknown"
    compatibility_coverage: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Share of relevant hard requirements backed by configuration facts",
    )
    compatibility_checks: list[RecommendedPresetCompatibilityCheck] = Field(
        default_factory=list
    )
    hard_conflicts: list[Literal["hotend_temperature", "nozzle_hrc"]] = Field(
        default_factory=list
    )
    saved: bool = False
    sync_enabled: bool | None = None


class RecommendedForPrinterResponse(BaseModel):
    """Top presets recommended for a specific printer."""

    printer_id: int
    printer_name: str
    items: list[RecommendedPresetItem]
