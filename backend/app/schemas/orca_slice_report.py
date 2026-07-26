"""Schemas for slices the OrcaSlicer plugin reports."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrcaSliceReportIn(BaseModel):
    """Figures the plugin read out of a produced G-code file."""

    file_name: str = Field(..., min_length=1, max_length=300)
    printer_settings_id: str | None = Field(None, max_length=200)
    printer_model: str | None = Field(None, max_length=200)
    target_host: str | None = Field(None, max_length=50)
    slicer_version: str | None = Field(None, max_length=50)
    total_weight_g: float | None = Field(None, ge=0)
    filament_weights_g: list[float] | None = None
    estimated_seconds: int | None = Field(None, ge=0)
    filament_changes: int | None = Field(None, ge=0)
    layer_count: int | None = Field(None, ge=0)
    sliced_at: datetime | None = None


class OrcaSliceReportBatch(BaseModel):
    slices: list[OrcaSliceReportIn] = Field(..., min_length=1, max_length=25)


class OrcaSliceReportResponse(BaseModel):
    """A remembered slice, with the printer it belongs to when known."""

    id: int
    file_name: str
    printer_settings_id: str | None
    printer_model: str | None
    physical_printer_id: int | None
    physical_printer_name: str | None
    target_host: str | None
    total_weight_g: float | None
    filament_weights_g: list[float] | None
    estimated_seconds: int | None
    filament_changes: int | None
    layer_count: int | None
    sliced_at: datetime | None
    received_at: datetime


class OrcaSliceReportAccepted(BaseModel):
    accepted: int
    duplicates: int
