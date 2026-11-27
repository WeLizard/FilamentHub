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
    node_instance_id: str | None = Field(default=None, min_length=16, max_length=100)
    plugin_version: str = Field(min_length=1, max_length=50)
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    previous_physical_printer_id: int | None = Field(default=None, gt=0)
    previous_material_system_id: int | None = Field(default=None, gt=0)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    @model_validator(mode="after")
    def complete_previous_binding(self) -> "PrinterBridgePairRequest":
        if (self.transport == "edge_agent") != (self.node_instance_id is not None):
            raise ValueError("node identity is required only for the Edge transport")
        if (self.previous_physical_printer_id is None) != (
            self.previous_material_system_id is None
        ):
            raise ValueError("previous printer and material system must be supplied together")
        return self


class PrinterBridgePairResponse(BaseModel):
    bridge_token: str
    physical_printer_id: int
    material_system_id: int
    printer_discovery_key: str | None = None


class PrinterBridgeKlipperLinkRequest(BaseModel):
    """One OrcaSlicer installation asks to report a Klipper printer's filament usage."""

    physical_printer_id: int = Field(gt=0)
    material_system_id: int = Field(gt=0)
    source_instance_id: str = Field(min_length=16, max_length=100)
    plugin_version: str = Field(min_length=1, max_length=50)
    capabilities: list[str] = Field(default_factory=list, max_length=32)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}


class PrinterBridgeKlipperLinkResponse(BaseModel):
    bridge_token: str
    physical_printer_id: int
    material_system_id: int
    provider: str


# Steps of a local printer check, as the plugin names them when it reports why
# a setup ended without pairing. "dialog" is the window closed without a try.
PrinterBridgeSetupStage = Literal[
    "address", "connect", "tls", "auth", "subscribe", "report",
    "pair", "snapshot", "local", "repair", "dialog", "unknown",
]


class PrinterBridgeSetupAttemptRequest(BaseModel):
    """Why one setup with this pairing code ended without pairing.

    Content-free on purpose: no address, serial or access code, only the step
    and the plugin's message key.
    """

    pairing_code: str = Field(min_length=8, max_length=32)
    provider: str = Field(min_length=1, max_length=50)
    transport: PrinterBridgeTransport
    source_instance_id: str = Field(min_length=16, max_length=100)
    stage: PrinterBridgeSetupStage
    code: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    plugin_version: str = Field(min_length=1, max_length=50)
    platform: Literal["windows", "macos", "linux", "other"]

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}


class PrinterBridgeSetupReport(BaseModel):
    stage: str
    code: str
    reported_at: datetime


class PrinterBridgeStatusResponse(BaseModel):
    configured: bool
    paired: bool
    pairing_expires_at: datetime | None
    last_seen_at: datetime | None
    last_observation_at: datetime | None
    last_snapshot_sequence: int | None
    last_snapshot_source_instance_id: str | None
    source_instance_id: str | None
    node_instance_id: str | None = None
    provider: str
    transport: PrinterBridgeTransport
    capabilities: list[str]
    # The last reason a setup ended without pairing; only while not paired.
    last_setup_report: PrinterBridgeSetupReport | None = None


class PrinterBridgeHeartbeatRequest(BaseModel):
    material_system_id: int = Field(gt=0)
    provider: str = Field(min_length=1, max_length=50)
    transport: PrinterBridgeTransport
    source_instance_id: str = Field(min_length=16, max_length=100)
    observed_at: datetime
    capabilities: list[str] | None = Field(default=None, max_length=32)
    # Whether the device behind the helper answers, and how often the helper
    # promises to report. Omitted = the helper cannot say.
    provider_reachable: bool | None = None
    contact_interval_s: int | None = Field(default=None, ge=5, le=3600)

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
    usage_route_proof: str | None = None
    spool: PrinterBridgeDesiredSpoolSnapshot | None
    preset: PrinterBridgeDesiredPresetSnapshot | None


class HappyHareRefreshGate(BaseModel):
    index: int = Field(ge=0, le=255)
    spool_id: int
    name: str
    material: str
    color: str
    vendor: str
    temperature: int
    initial_weight: int
    rfids: str


class HappyHareRefreshTarget(BaseModel):
    revision: str
    physical_printer_id: int
    material_system_id: int
    inventory_key_digest: str
    printer_hostname: str
    gates: list[HappyHareRefreshGate]


class PrinterBridgeDesiredSnapshotResponse(BaseModel):
    revision: str
    physical_printer_id: int
    material_system_id: int
    system_name: str
    system_kind: str
    slots: list[PrinterBridgeDesiredSlotSnapshot]
    happy_hare_refresh: HappyHareRefreshTarget | None = None
