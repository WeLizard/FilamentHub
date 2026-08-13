"""Public contract for provider-neutral production print history."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.print_job import PrintJobStatus


class PrintJobMaterialCreate(BaseModel):
    spool_id: int = Field(..., ge=1)
    material_line_key: str | None = Field(None, max_length=160)
    tool_index: int | None = Field(None, ge=0, le=1023)
    planned_weight_g: float | None = Field(None, gt=0, le=1_000_000)


class PrintJobCreate(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    title: str = Field(..., min_length=1, max_length=255)
    physical_printer_id: int = Field(..., ge=1)
    calculator_history_id: int | None = Field(None, ge=1)
    calculator_job_key: str | None = Field(None, max_length=160)
    orca_slice_report_id: int | None = Field(None, ge=1)
    estimated_duration_s: float | None = Field(None, ge=0, le=31_536_000)
    materials: list[PrintJobMaterialCreate] = Field(default_factory=list, max_length=64)

    model_config = {"str_strip_whitespace": True}

    @model_validator(mode="after")
    def validate_references(self) -> "PrintJobCreate":
        if self.calculator_job_key is not None and self.calculator_history_id is None:
            raise ValueError("calculator_job_key requires calculator_history_id")
        identities = [
            (item.spool_id, item.material_line_key, item.tool_index) for item in self.materials
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("materials must contain unique spool/line/tool combinations")
        return self


class PrintJobTransitionCreate(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    status: PrintJobStatus
    note: str | None = Field(None, max_length=500)

    model_config = {"str_strip_whitespace": True}


class PrintJobMaterialResponse(BaseModel):
    id: int
    spool_id: int | None
    material_line_key: str | None
    tool_index: int | None
    planned_weight_g: float | None
    spool_name: str
    filament_name: str | None
    material_type: str | None
    color_hex: str | None


class PrintJobEventResponse(BaseModel):
    id: int
    status: PrintJobStatus
    source: str
    note: str | None
    occurred_at: datetime
    received_at: datetime


class PrintJobResponse(BaseModel):
    id: int
    logical_id: str
    physical_printer_id: int | None
    printer_name: str | None
    calculator_history_id: int | None
    calculation_title: str | None
    calculator_job_key: str | None
    orca_slice_report_id: int | None
    file_name: str | None
    title: str
    status: PrintJobStatus
    source: str
    estimated_duration_s: float | None
    actual_duration_s: float | None
    confirmed_consumption_g: float
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    materials: list[PrintJobMaterialResponse]
    events: list[PrintJobEventResponse]


class PrintJobListResponse(BaseModel):
    items: list[PrintJobResponse]
    total: int
