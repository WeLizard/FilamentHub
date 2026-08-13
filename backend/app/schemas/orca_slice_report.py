"""Schemas for slices the OrcaSlicer plugin reports."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrcaSliceReportIn(BaseModel):
    """What identifies a slice the plugin produced.

    No figures: they come from reading the file when a person asks for a
    calculation, so a listed slice cannot disagree with its own numbers.
    """

    file_name: str = Field(..., min_length=1, max_length=300)
    printer_settings_id: str | None = Field(None, max_length=200)
    print_settings_id: str | None = Field(None, max_length=200)
    printer_model: str | None = Field(None, max_length=200)
    fhub_printer_profile_id: int | None = Field(None, ge=1, le=2**63 - 1)
    fhub_print_profile_id: int | None = Field(None, ge=1, le=2**63 - 1)
    source_instance_id: str | None = Field(None, min_length=16, max_length=100)
    target_host: str | None = Field(None, max_length=50)
    slicer_version: str | None = Field(None, max_length=50)
    # The plugin's handle for the file; it keeps the path on its own side.
    source_key: str | None = Field(None, max_length=64)
    sliced_at: datetime | None = None


class OrcaSliceReportBatch(BaseModel):
    slices: list[OrcaSliceReportIn] = Field(..., min_length=1, max_length=25)


class OrcaSliceReportResponse(BaseModel):
    """A remembered slice, with the printer it belongs to when known."""

    id: int
    file_name: str
    printer_settings_id: str | None
    print_settings_id: str | None
    printer_model: str | None
    physical_printer_id: int | None
    physical_printer_name: str | None
    printer_profile_id: int | None
    print_profile_id: int | None
    target_host: str | None
    source_key: str | None
    sliced_at: datetime | None
    received_at: datetime


class OrcaSliceReportAccepted(BaseModel):
    accepted: int
    duplicates: int
