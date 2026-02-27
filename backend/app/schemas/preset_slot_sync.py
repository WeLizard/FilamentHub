"""Schemas for preset slot sync (HH integration) endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ── Device schemas ─────────────────────────────────────────────────────────


class DeviceRegisterRequest(BaseModel):
    """Register or update a user's printer device."""

    device_fingerprint: str = Field(..., max_length=200)
    name: str = Field(..., max_length=200)
    printer_id: int | None = Field(default=None, ge=1)
    supports_hh: bool = Field(default=False)
    gate_count: int | None = Field(default=None, ge=1, le=256)


class DeviceResponse(BaseModel):
    """Printer device info."""

    id: int
    user_id: int
    printer_id: int | None
    name: str
    device_fingerprint: str
    supports_hh: bool
    gate_count: int | None
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeviceStateResponse(BaseModel):
    """Device info with its current gate states."""

    device: DeviceResponse
    gates: list["GateStateResponse"]


# ── Gate state schemas ─────────────────────────────────────────────────────


class GateStateResponse(BaseModel):
    """Current state of a single gate/slot."""

    id: int
    gate_index: int
    preset_id: int | None
    spool_id: int | None
    hh_material: str | None
    hh_color_hex: str | None
    hh_status: int | None
    source: str
    source_ts: datetime
    is_active: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class PresetSlotAssignRequest(BaseModel):
    """Assign a preset to a gate (web manual)."""

    preset_id: int | None = Field(default=None, ge=1)
    spool_id: int | None = Field(default=None, ge=1)


# ── Orca sync schemas ──────────────────────────────────────────────────────


class HeartbeatRequest(BaseModel):
    """Device heartbeat from OrcaSlicer."""

    device_fingerprint: str = Field(..., max_length=200)
    device_name: str | None = Field(default=None, max_length=200)
    supports_hh: bool = Field(default=False)
    gate_count: int | None = Field(default=None, ge=1, le=256)
    orcaslicer_version: str | None = Field(default=None, max_length=50)


class HeartbeatResponse(BaseModel):
    """Heartbeat acknowledgement."""

    device_id: int
    ok: bool = True


class HHGateItem(BaseModel):
    """A single gate entry from a Happy Hare snapshot."""

    gate: int = Field(..., ge=0)
    status: int = Field(..., ge=-1, le=2)
    material: str = Field(default="", max_length=50)
    color_hex: str = Field(default="", max_length=7)
    temperature: int = Field(default=0, ge=0)

    @field_validator("color_hex")
    @classmethod
    def normalise_color(cls, v: str) -> str:
        return v.lstrip("#").upper() if v else ""


class HHSnapshotRequest(BaseModel):
    """HH snapshot payload from OrcaSlicer."""

    device_fingerprint: str = Field(..., max_length=200)
    gate_count: int = Field(..., ge=1, le=256)
    snapshot_ts: datetime
    gates: list[HHGateItem]

    @field_validator("gates")
    @classmethod
    def no_dup_gates(cls, gates: list[HHGateItem]) -> list[HHGateItem]:
        seen = set()
        for g in gates:
            if g.gate in seen:
                raise ValueError(f"Duplicate gate index: {g.gate}")
            seen.add(g.gate)
        return gates


class HHSnapshotResponse(BaseModel):
    """HH snapshot acknowledgement."""

    device_id: int
    updated_gates: int
    mismatches: list[int] = Field(default_factory=list)


class ManualAssignmentRequest(BaseModel):
    """Manual gate assignment from OrcaSlicer."""

    device_fingerprint: str = Field(..., max_length=200)
    gate: int = Field(..., ge=0)
    preset_id: int | None = Field(default=None, ge=1)
    spool_id: int | None = Field(default=None, ge=1)


class ManualAssignmentResponse(BaseModel):
    """Manual assignment acknowledgement."""

    gate_state_id: int
    ok: bool = True


class UsageEstimateRequest(BaseModel):
    """Filament usage estimate after a print job."""

    device_fingerprint: str = Field(..., max_length=200)
    preset_id: int | None = Field(default=None, ge=1)
    spool_id: int | None = Field(default=None, ge=1)
    delta_weight_g: float = Field(..., gt=0)
    job_ref: str | None = Field(default=None, max_length=200)
    meta: dict[str, Any] | None = None


class UsageEstimateResponse(BaseModel):
    """Usage estimate acknowledgement."""

    event_id: int
    ok: bool = True


class SlotStateResponse(BaseModel):
    """Current slot map for a device (Orca sync GET)."""

    device_id: int
    device_fingerprint: str
    gate_count: int | None
    gates: list[GateStateResponse]
