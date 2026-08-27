"""HTTP contract for local printer-bridge pairing and authorization."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PrinterBridgeTransport = Literal["orca_plugin_lan", "edge_agent"]


class PrinterBridgePairingCodeResponse(BaseModel):
    pairing_code: str
    expires_at: datetime


class PrinterBridgePairRequest(BaseModel):
    pairing_code: str = Field(min_length=8, max_length=32)
    provider: str = Field(min_length=1, max_length=50)
    transport: PrinterBridgeTransport
    source_instance_id: str = Field(min_length=16, max_length=100)
    plugin_version: str = Field(min_length=1, max_length=50)
    capabilities: list[str] = Field(default_factory=list, max_length=32)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}


class PrinterBridgePairResponse(BaseModel):
    bridge_token: str
    physical_printer_id: int
    material_system_id: int


class PrinterBridgeStatusResponse(BaseModel):
    configured: bool
    paired: bool
    pairing_expires_at: datetime | None
    last_seen_at: datetime | None
    source_instance_id: str | None
    provider: str
    transport: PrinterBridgeTransport
    capabilities: list[str]


class PrinterBridgeHeartbeatRequest(BaseModel):
    material_system_id: int = Field(gt=0)
    provider: str = Field(min_length=1, max_length=50)
    transport: PrinterBridgeTransport
    source_instance_id: str = Field(min_length=16, max_length=100)
    observed_at: datetime
    capabilities: list[str] | None = Field(default=None, max_length=32)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}


class PrinterBridgeHeartbeatResponse(BaseModel):
    accepted: bool
    last_seen_at: datetime


class PrinterBridgeDesiredSpoolSnapshot(BaseModel):
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


class PrinterBridgeDesiredPresetSnapshot(BaseModel):
    id: int
    name: str


class PrinterBridgeDesiredSlotSnapshot(BaseModel):
    material_slot_id: int = Field(ge=1)
    index: int = Field(ge=0, le=1023)
    label: str | None
    kind: str
    assignment_revision: int = Field(ge=0)
    spool: PrinterBridgeDesiredSpoolSnapshot | None
    preset: PrinterBridgeDesiredPresetSnapshot | None


class PrinterBridgeDesiredSnapshotResponse(BaseModel):
    revision: str
    physical_printer_id: int
    material_system_id: int
    system_name: str
    system_kind: str
    slots: list[PrinterBridgeDesiredSlotSnapshot]
