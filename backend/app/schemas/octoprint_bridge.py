"""HTTP contract owned by the native OctoPrint Bridge adapter."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class OctoPrintPairingCodeResponse(BaseModel):
    pairing_code: str
    expires_at: datetime


class OctoPrintBridgeStatusResponse(BaseModel):
    configured: bool
    paired: bool
    pairing_expires_at: datetime | None
    last_seen_at: datetime | None
    active_slot_index: int | None
    instance_id: str | None
    plugin_version: str | None
    octoprint_version: str | None


class OctoPrintBridgePairRequest(BaseModel):
    pairing_code: str = Field(min_length=8, max_length=32)
    instance_id: str = Field(min_length=1, max_length=200)
    plugin_version: str = Field(min_length=1, max_length=50)
    octoprint_version: str = Field(min_length=1, max_length=50)
    capabilities: list[str] = Field(default_factory=list, max_length=32)

    model_config = {"str_strip_whitespace": True}


class OctoPrintBridgePairResponse(BaseModel):
    bridge_token: str
    physical_printer_id: int
    material_system_id: int


class OctoPrintBridgeHeartbeatRequest(BaseModel):
    instance_id: str = Field(min_length=1, max_length=200)
    plugin_version: str = Field(min_length=1, max_length=50)
    octoprint_version: str = Field(min_length=1, max_length=50)
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    active_slot_index: int | None = Field(default=None, ge=0, le=1023)

    model_config = {"str_strip_whitespace": True}


class OctoPrintBridgeSpoolSnapshot(BaseModel):
    id: int
    filament_id: int | None
    name: str
    brand: str | None
    material_type: str | None
    color_hex: str | None
    remaining_weight_g: float
    initial_weight_g: float
    density_g_cm3: float
    diameter_mm: float


class OctoPrintBridgePresetSnapshot(BaseModel):
    id: int
    name: str


class OctoPrintBridgeSlotSnapshot(BaseModel):
    index: int
    label: str | None
    kind: str
    spool: OctoPrintBridgeSpoolSnapshot | None
    preset: OctoPrintBridgePresetSnapshot | None


class OctoPrintBridgeSnapshotResponse(BaseModel):
    revision: str
    physical_printer_id: int
    material_system_id: int
    system_name: str
    system_kind: str
    slots: list[OctoPrintBridgeSlotSnapshot]


class OctoPrintBridgeUsageItem(BaseModel):
    slot_index: int = Field(ge=0, le=1023)
    spool_id: int = Field(ge=1)
    used_length_mm: float | None = Field(default=None, gt=0)
    used_weight_g: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def exactly_one_amount(self) -> "OctoPrintBridgeUsageItem":
        if (self.used_length_mm is None) == (self.used_weight_g is None):
            raise ValueError("exactly one usage amount is required")
        return self


class OctoPrintBridgeUsageRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    job_id: str = Field(min_length=1, max_length=200)
    outcome: Literal["completed", "cancelled", "failed"]
    file_name: str | None = Field(default=None, max_length=500)
    duration_s: float | None = Field(default=None, ge=0)
    items: list[OctoPrintBridgeUsageItem] = Field(min_length=1, max_length=256)

    model_config = {"str_strip_whitespace": True}


class OctoPrintBridgeUsageResponse(BaseModel):
    accepted: bool
    deduplicated: bool
    consumed_weight_g: float
