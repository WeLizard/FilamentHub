"""HTTP contract for local printer-bridge pairing and authorization."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.printer_usage import PrinterUsageEvent, PrinterUsageEventResult

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
    last_observation_at: datetime | None
    last_snapshot_sequence: int | None
    last_snapshot_source_instance_id: str | None
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


class PrinterBridgeUsageBatchRequest(BaseModel):
    material_system_id: int = Field(gt=0)
    provider: str = Field(min_length=1, max_length=50)
    transport: PrinterBridgeTransport
    source_instance_id: str = Field(min_length=16, max_length=100)
    sequence: int = Field(ge=1, le=9_223_372_036_854_775_807)
    events: list[PrinterUsageEvent] = Field(min_length=1, max_length=128)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    @model_validator(mode="after")
    def unique_event_ids(self) -> "PrinterBridgeUsageBatchRequest":
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event ids must be unique within a batch")
        return self


class PrinterBridgeUsageBatchResponse(BaseModel):
    accepted: bool
    deduplicated: bool
    ack_sequence: int
    events: list[PrinterUsageEventResult]


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
