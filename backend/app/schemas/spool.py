"""Schemas for user spool (filament inventory) endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SpoolState = Literal["active", "shelf", "archived", "empty"]
SpoolSource = Literal[
    "manual",
    "qr",
    "catalog",
    "orca_import",
    "octoprint_spoolmanager",
    "csv_import",
]

SpoolImportSemanticField = Literal[
    "spool_name",
    "vendor",
    "material",
    "color_name",
    "color_hex",
    "serial_number",
    "initial_weight",
    "used_weight",
    "remaining_weight",
    "empty_spool_weight",
    "price",
    "currency",
    "note",
    "density",
    "diameter",
    "diameter_tolerance",
    "flow_rate_compensation",
    "nozzle_temperature",
    "bed_temperature",
    "enclosure_temperature",
    "nozzle_temperature_offset",
    "bed_temperature_offset",
    "enclosure_temperature_offset",
    "total_length",
    "used_length",
    "first_use",
    "last_use",
    "purchased_from",
    "purchased_on",
]
SpoolImportUnit = Literal["g", "kg", "mm", "m"]


class SpoolFilamentInfo(BaseModel):
    """Embedded filament info returned with a spool."""

    id: int
    name: str
    material_type: str
    color_name: str | None
    color_hex: str | None
    brand_name: str | None
    price_per_kg: float | None
    currency: str | None = None  # валюта бренда (для price_per_kg)
    required_nozzle_hrc: int | None = None
    qr_code: str | None = None

    model_config = {"from_attributes": True}


class SpoolResponse(BaseModel):
    """Full spool representation."""

    id: int
    user_id: int
    filament_id: int | None
    filament: SpoolFilamentInfo | None
    initial_weight_g: float
    used_weight_g: float
    remaining_weight_g: float
    remaining_pct: float
    price: float | None
    currency: str | None
    state: str
    source: str
    lot_nr: str | None
    comment: str | None
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None
    extra: dict | None

    model_config = {"from_attributes": True}


class SpoolCreateRequest(BaseModel):
    """Create a new spool."""

    filament_id: int | None = Field(default=None, ge=1)
    initial_weight_g: float = Field(..., gt=0, le=10_000)
    used_weight_g: float = Field(default=0.0, ge=0)
    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    state: SpoolState = "shelf"
    source: SpoolSource = "manual"
    lot_nr: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=500)


class SpoolUpdateRequest(BaseModel):
    """Partial update of a spool."""

    filament_id: int | None = Field(default=None, ge=1)
    initial_weight_g: float | None = Field(default=None, gt=0, le=10_000)
    used_weight_g: float | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    state: SpoolState | None = None
    lot_nr: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=500)


class SpoolUseRequest(BaseModel):
    """Record filament usage (add to used_weight_g)."""

    delta_weight_g: float = Field(..., gt=0, le=5_000)


class SpoolUsageEventResponse(BaseModel):
    """One recorded fact about a spool's consumption."""

    id: int
    event_type: str
    delta_weight_g: float | None
    remaining_weight_g: float | None
    device_name: str | None
    job_ref: str | None
    created_at: datetime
    # Что именно не сошлось: заявленный принтером вес, признак повтора,
    # результат замера, пометка об отмене.
    meta: dict | None = None


class SpoolManagerFilamentMatch(BaseModel):
    """One conservative, unambiguous catalog match for an imported row."""

    id: int
    name: str
    brand_name: str
    material_type: str
    color_name: str | None = None
    color_hex: str | None = None
    reason: Literal["name", "color_hex", "color_name"]


class SpoolManagerPreviewRow(BaseModel):
    """Normalized preview of one OctoPrint SpoolManager CSV row."""

    row_number: int
    fingerprint: str
    status: Literal["ready", "already_imported", "invalid"]
    spool_name: str
    vendor: str | None = None
    material: str | None = None
    color_name: str | None = None
    color_hex: str | None = None
    serial_number: str | None = None
    initial_weight_g: float | None = None
    used_weight_g: float | None = None
    remaining_weight_g: float | None = None
    empty_spool_weight_g: float | None = None
    price: float | None = None
    currency: str | None = None
    suggested_filament: SpoolManagerFilamentMatch | None = None
    warnings: list[str] = Field(default_factory=list)


class SpoolManagerPreviewResponse(BaseModel):
    """Preview and validation summary for a SpoolManager CSV."""

    file_name: str
    file_sha256: str
    total_rows: int
    importable_rows: int
    matched_rows: int
    unmatched_rows: int
    duplicate_rows: int
    invalid_rows: int
    rows: list[SpoolManagerPreviewRow]


class SpoolManagerImportResponse(BaseModel):
    """Result of an explicitly confirmed SpoolManager CSV import."""

    created: int
    skipped_existing: int
    skipped_unselected: int
    invalid: int
    created_spool_ids: list[int]
    created_draft_ids: list[int] = Field(default_factory=list)


class SpoolImportColumnMapping(BaseModel):
    """User-confirmed mapping from safe semantic fields to CSV columns."""

    fields: dict[SpoolImportSemanticField, str] = Field(default_factory=dict)
    units: dict[SpoolImportSemanticField, SpoolImportUnit] = Field(default_factory=dict)


class SpoolImportPreviewResponse(SpoolManagerPreviewResponse):
    """Provider-neutral preview for a detected or manually mapped file."""

    detected_format: Literal["octoprint_spoolmanager_csv", "custom_csv"] | None
    detected_label: str | None = None
    mapping_required: bool = False
    available_columns: list[str] = Field(default_factory=list)
    sample_rows: list[dict[str, str]] = Field(default_factory=list)
    suggested_mapping: SpoolImportColumnMapping | None = None
    required_fields: list[SpoolImportSemanticField] = Field(default_factory=list)


class SpoolImportResponse(SpoolManagerImportResponse):
    """Result of a provider-neutral spool file import."""

    detected_format: Literal["octoprint_spoolmanager_csv", "custom_csv"]
