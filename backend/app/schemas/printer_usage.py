"""Provider-neutral printer usage evidence accepted by bridge transports."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PrinterUsageItem(BaseModel):
    slot_index: int = Field(ge=0, le=1023)
    tool_index: int | None = Field(default=None, ge=0, le=1023)
    spool_id: int = Field(ge=1)
    usage_route_proof: str | None = Field(default=None, min_length=1, max_length=128)
    evidence: Literal["route_proof", "current_assignment"] | None = None
    used_length_mm: float | None = Field(default=None, gt=0)
    used_weight_g: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def exactly_one_amount(self) -> "PrinterUsageItem":
        if (self.used_length_mm is None) == (self.used_weight_g is None):
            raise ValueError("exactly one usage amount is required")
        return self


class PrinterUsageEvent(BaseModel):
    contract_version: Literal[1, 2] = 1
    event_id: str = Field(min_length=1, max_length=128)
    job_id: str = Field(min_length=1, max_length=200)
    segment_sequence: int | None = Field(default=None, ge=1)
    event_type: Literal["checkpoint", "terminal"] = "terminal"
    reasons: list[
        Literal[
            "periodic",
            "tool_change",
            "slot_change",
            "spool_change",
            "filament_change",
            "paused",
            "disconnect",
            "shutdown",
            "terminal",
        ]
    ] = Field(default_factory=list, max_length=16)
    outcome: Literal["completed", "cancelled", "failed"] | None = None
    file_name: str | None = Field(default=None, max_length=500)
    started_at: datetime | None = None
    observed_at: datetime | None = None
    duration_s: float | None = Field(default=None, ge=0)
    items: list[PrinterUsageItem] = Field(default_factory=list, max_length=256)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    @model_validator(mode="after")
    def validate_event_shape(self) -> "PrinterUsageEvent":
        if self.contract_version == 2 and self.segment_sequence is None:
            raise ValueError("usage contract v2 requires segment_sequence")
        if self.event_type == "terminal" and self.outcome is None:
            raise ValueError("terminal usage event requires an outcome")
        if self.event_type == "checkpoint" and self.outcome is not None:
            raise ValueError("checkpoint usage event cannot have an outcome")
        if self.event_type == "checkpoint" and not self.items:
            raise ValueError("checkpoint usage event requires an amount")
        slot_indices = [item.slot_index for item in self.items]
        spool_ids = [item.spool_id for item in self.items]
        if len(slot_indices) != len(set(slot_indices)):
            raise ValueError("each slot may appear only once in a usage event")
        if len(spool_ids) != len(set(spool_ids)):
            raise ValueError("each spool may appear only once in a usage event")
        for item in self.items:
            expected_evidence = (
                "route_proof" if item.usage_route_proof is not None else "current_assignment"
            )
            if item.evidence is not None and item.evidence != expected_evidence:
                raise ValueError("usage evidence must match the submitted route proof")
        return self


class PrinterUsageEventResult(BaseModel):
    event_id: str
    deduplicated: bool
    consumed_weight_g: float
