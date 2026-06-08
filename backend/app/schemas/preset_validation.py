"""Pydantic schemas для валидации пресетов OrcaSlicer."""

from pydantic import BaseModel, Field

# ── Parent Preset Validation ──────────────────────────────────


class ParentPresetValidationRequest(BaseModel):
    """Запрос на валидацию родительского пресета."""
    inherits: str
    orcaslicer_version: str | None = None


class ParentPresetValidationResponse(BaseModel):
    """Ответ валидации родительского пресета."""
    exists: bool
    needs_fallback: bool = False
    fallback_preset: str | None = None
    confidence: float = 1.0
    material_type: str | None = None


# ── Batch Validation ──────────────────────────────────────────


class PresetBatchValidationItem(BaseModel):
    """Один пресет для валидации в батче."""
    preset_id: int | None = None
    name: str
    inherits: str | None = None
    material_type: str | None = None
    extruder_temp: float | None = None
    bed_temp: float | None = None


class PresetBatchValidationRequest(BaseModel):
    """Запрос на батч-валидацию пресетов."""
    presets: list[PresetBatchValidationItem]


class PresetValidationResultItem(BaseModel):
    """Результат валидации одного пресета."""
    preset_id: int | None = None
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parent_preset_missing: bool = False
    material_mapping_confidence: float = 1.0


class PresetBatchValidationResponse(BaseModel):
    """Ответ батч-валидации."""
    results: list[PresetValidationResultItem]
    total: int
    valid_count: int
    error_count: int
