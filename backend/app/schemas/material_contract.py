"""Schemas for the physical-printer and material-system contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.tag_identity import normalize_tag_format, normalize_tag_uid
from app.schemas.printer_connection_observation import PrinterIdentityEvidence

CapabilityName = Literal[
    "read",
    "write",
    "presence",
    "spool_identity",
    "consumption",
    "local_command",
    "tag_read",
    "tag_write",
]


class PhysicalPrinterMergeRequest(BaseModel):
    target_id: int = Field(gt=0)
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class PhysicalPrinterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    printer_id: int | None = Field(default=None, ge=1)
    printer_profile_ids: list[int] = Field(default_factory=list, max_length=64)
    request_id: UUID | None = None
    material_system: MaterialSystemCreate | None = None
    connection: PrinterSetupConnection | None = None

    model_config = {"str_strip_whitespace": True}

    @field_validator("printer_profile_ids")
    @classmethod
    def unique_profile_ids(cls, value: list[int]) -> list[int]:
        if any(profile_id < 1 for profile_id in value):
            raise ValueError("printer_profile_ids must contain positive integers")
        if len(value) != len(set(value)):
            raise ValueError("printer_profile_ids must be unique")
        return value


class PhysicalPrinterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    printer_id: int | None = Field(default=None, ge=1)

    model_config = {"str_strip_whitespace": True}


class PhysicalPrinterConfigurationsUpdate(BaseModel):
    printer_profile_ids: list[int] = Field(default_factory=list, max_length=64)

    @field_validator("printer_profile_ids")
    @classmethod
    def unique_profile_ids(cls, value: list[int]) -> list[int]:
        if any(profile_id < 1 for profile_id in value):
            raise ValueError("printer_profile_ids must contain positive integers")
        if len(value) != len(set(value)):
            raise ValueError("printer_profile_ids must be unique")
        return value


class MaterialSlotCreate(BaseModel):
    provider_index: int = Field(ge=0, le=1023)
    label: str | None = Field(default=None, max_length=100)
    kind: str = Field(default="slot", min_length=1, max_length=50)

    model_config = {"str_strip_whitespace": True}


class MaterialSystemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="direct_feed", min_length=1, max_length=50)
    provider: str = Field(default="manual", min_length=1, max_length=50)
    capabilities: list[CapabilityName] = Field(default_factory=list)
    slot_count: int | None = Field(default=None, ge=1, le=256)
    slots: list[MaterialSlotCreate] = Field(default_factory=list, max_length=257)

    model_config = {"str_strip_whitespace": True}

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, value: list[CapabilityName]) -> list[CapabilityName]:
        if len(value) != len(set(value)):
            raise ValueError("capabilities must be unique")
        return value

    @model_validator(mode="after")
    def unique_slot_indices(self) -> "MaterialSystemCreate":
        indices = [slot.provider_index for slot in self.slots]
        if len(indices) != len(set(indices)):
            raise ValueError("slot provider_index values must be unique within a system")
        if self.slots and self.slot_count is not None and set(indices) != set(range(self.slot_count)):
            raise ValueError("slot_count must describe exactly the explicit slot indices")
        return self


class MaterialSystemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slot_count: int | None = Field(default=None, ge=1, le=256)
    kind: str | None = Field(default=None, min_length=1, max_length=50)
    provider: str | None = Field(default=None, min_length=1, max_length=50)
    slots: list[MaterialSlotCreate] | None = Field(default=None, min_length=1, max_length=257)
    expected_slots: list[MaterialSlotAssignmentExpectation] | None = Field(default=None, max_length=257)

    model_config = {"str_strip_whitespace": True}

    @model_validator(mode="after")
    def explicit_topology(self) -> "MaterialSystemUpdate":
        if self.slots is not None:
            indices = [slot.provider_index for slot in self.slots]
            if len(indices) != len(set(indices)) or self.expected_slots is None:
                raise ValueError("explicit topology requires unique indices and slot expectations")
            if self.slot_count is not None:
                raise ValueError("use explicit slots or slot_count, not both")
        elif self.kind is not None or self.provider is not None:
            raise ValueError("changing topology kind or provider requires explicit slots")
        return self


class PrinterSetupConnection(BaseModel):
    """Opaque evidence from a local client; never a LAN address or credential."""

    source_instance_id: str = Field(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    connection_ref: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    origin: Literal["orca_profile", "local_manual"]
    provider: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    endpoint_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    device_identity: PrinterIdentityEvidence | None = None

    model_config = {"extra": "forbid"}


class PhysicalPrinterConnectionSetup(BaseModel):
    connection: PrinterSetupConnection | None = None
    material_system: MaterialSystemCreate | None = None
    material_system_update: MaterialSystemUpdate | None = None
    material_system_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def target_existing_topology(self) -> "PhysicalPrinterConnectionSetup":
        if self.material_system_update is not None and (
            self.material_system_id is None or self.material_system is not None
        ):
            raise ValueError("topology update requires one existing material system")
        return self


class MaterialSlotAssignmentExpectation(BaseModel):
    material_slot_id: int = Field(ge=1)
    expected_revision: int = Field(ge=0)
    expected_spool_id: int | None = Field(ge=1)


class MaterialSlotAssignmentUpdate(BaseModel):
    expected_revision: int = Field(ge=0)
    expected_spool_id: int | None = Field(ge=1)
    preset_id: int | None = Field(default=None, ge=1)
    spool_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_assignment_field(self) -> "MaterialSlotAssignmentUpdate":
        if not {"preset_id", "spool_id"}.intersection(self.model_fields_set):
            raise ValueError("preset_id or spool_id must be provided")
        return self


class MaterialSystemAssignmentsClearRequest(BaseModel):
    slots: list[MaterialSlotAssignmentExpectation] = Field(max_length=257)

    @model_validator(mode="after")
    def require_unique_slot_ids(self) -> "MaterialSystemAssignmentsClearRequest":
        slot_ids = [item.material_slot_id for item in self.slots]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("material_slot_id values must be unique")
        return self


class PhysicalPrinterConnectorCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    transport: str = Field(min_length=1, max_length=50)
    material_system_id: int | None = Field(default=None, ge=1)
    capabilities: list[CapabilityName] = Field(default_factory=list)

    model_config = {"str_strip_whitespace": True}

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, value: list[CapabilityName]) -> list[CapabilityName]:
        if len(value) != len(set(value)):
            raise ValueError("capabilities must be unique")
        return value


class LegacySlotProjectionResponse(BaseModel):
    gate_state_id: int
    preset_id: int | None
    spool_id: int | None
    source: str
    source_ts: datetime
    is_active: bool
    hh_material: str | None
    hh_color_hex: str | None
    hh_status: int | None
    updated_at: datetime


class MaterialSlotObservationResponse(BaseModel):
    source: str
    observed_at: datetime
    received_at: datetime
    present: bool | None
    active_feed: bool | None
    spool_id: int | None = None
    spool_identity_known: bool = False
    tag_uid: str | None = None
    tag_technology: Literal["unknown", "nfc", "uhf_rfid"] | None = None
    tag_format: str | None = None
    tag_match_status: Literal["matched", "unlinked", "conflict"] | None = None
    material: str | None
    color_hex: str | None
    remaining_percent: int | None
    remaining_grams: int | None

    model_config = {"from_attributes": True}


class MaterialSlotAssignmentResponse(BaseModel):
    id: int
    preset_id: int | None
    spool_id: int | None
    source: str
    source_ts: datetime
    active: bool


class MaterialSlotResponse(BaseModel):
    id: int
    provider_index: int
    label: str | None
    kind: str
    active: bool
    assignment_revision: int
    assignment: MaterialSlotAssignmentResponse | None = None
    observation: MaterialSlotObservationResponse | None = None
    legacy_projection: LegacySlotProjectionResponse | None = None

    model_config = {"from_attributes": True}


class MaterialSystemResponse(BaseModel):
    id: int
    name: str
    kind: str
    provider: str
    capabilities: list[str]
    active: bool
    declared_slot_count: int | None
    slots: list[MaterialSlotResponse]

    model_config = {"from_attributes": True}


class PhysicalPrinterConnectorResponse(BaseModel):
    id: int
    material_system_id: int | None
    provider: str
    transport: str
    source_instance_id: str | None
    capabilities: list[str]
    active: bool
    last_seen_at: datetime | None
    last_observation_at: datetime | None
    last_snapshot_sequence: int | None
    last_snapshot_source_instance_id: str | None
    status_observation: "PhysicalPrinterStatusObservationResponse | None" = None

    model_config = {"from_attributes": True}


class PhysicalPrinterStatusObservationResponse(BaseModel):
    source: str
    observed_at: datetime
    received_at: datetime
    state: str
    progress_percent: int | None
    remaining_seconds: int | None
    current_layer: int | None
    total_layers: int | None
    job_name: str | None
    nozzle_temperature: float | None
    nozzle_target_temperature: float | None
    bed_temperature: float | None
    bed_target_temperature: float | None
    chamber_temperature: float | None
    wifi_signal: str | None
    error_code: str | None

    model_config = {"from_attributes": True}


class PhysicalPrinterResponse(BaseModel):
    id: int
    logical_id: str
    printer_id: int | None
    name: str
    printer_profile_ids: list[int]
    material_systems: list[MaterialSystemResponse]
    connectors: list[PhysicalPrinterConnectorResponse]
    has_api_key: bool
    printer_hostname: str | None
    reports_feed: bool
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, printer: Any) -> "PhysicalPrinterResponse":
        systems = sorted(printer.material_systems, key=lambda system: system.id)
        return cls(
            id=printer.id,
            logical_id=printer.logical_id,
            printer_id=printer.printer_id,
            name=printer.name,
            has_api_key=printer.api_key is not None,
            printer_hostname=printer.printer_hostname,
            reports_feed=printer.reports_feed,
            last_seen_at=printer.last_seen_at,
            printer_profile_ids=sorted(link.printer_profile_id for link in printer.profile_links),
            material_systems=[cls._material_system_response(system) for system in systems],
            connectors=[
                PhysicalPrinterConnectorResponse.model_validate(connector)
                for connector in sorted(printer.connectors, key=lambda item: item.id)
            ],
            created_at=printer.created_at,
            updated_at=printer.updated_at,
        )

    @staticmethod
    def _material_system_response(system: Any) -> MaterialSystemResponse:
        slots = []
        for slot in sorted(system.slots, key=lambda item: (item.provider_index, item.id)):
            state = slot.legacy_gate_state
            projection = None
            if state is not None:
                projection = LegacySlotProjectionResponse(
                    gate_state_id=state.id,
                    preset_id=state.preset_id,
                    spool_id=state.spool_id,
                    source=state.source.value
                    if hasattr(state.source, "value")
                    else str(state.source),
                    source_ts=state.source_ts,
                    is_active=state.is_active,
                    hh_material=state.hh_material,
                    hh_color_hex=state.hh_color_hex,
                    hh_status=state.hh_status,
                    updated_at=state.updated_at,
                )
            assignment = None
            if slot.assignment is not None:
                assignment = MaterialSlotAssignmentResponse.model_validate(
                    slot.assignment, from_attributes=True
                )
            slots.append(
                MaterialSlotResponse(
                    id=slot.id,
                    provider_index=slot.provider_index,
                    label=slot.label,
                    kind=slot.kind,
                    active=slot.active,
                    assignment_revision=slot.assignment_revision,
                    assignment=assignment,
                    observation=(
                        MaterialSlotObservationResponse.model_validate(slot.observation)
                        if slot.observation is not None
                        else None
                    ),
                    legacy_projection=projection,
                )
            )
        return MaterialSystemResponse(
            id=system.id,
            name=system.name,
            kind=system.kind,
            provider=system.provider,
            capabilities=list(system.capabilities),
            active=system.active,
            declared_slot_count=system.declared_slot_count,
            slots=slots,
        )


PrinterBridgeState = Literal[
    "unknown",
    "idle",
    "preparing",
    "printing",
    "paused",
    "finished",
    "failed",
]


class PrinterBridgeStatusSnapshot(BaseModel):
    state: PrinterBridgeState = "unknown"
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    remaining_seconds: int | None = Field(default=None, ge=0, le=2_592_000)
    current_layer: int | None = Field(default=None, ge=0, le=10_000_000)
    total_layers: int | None = Field(default=None, ge=0, le=10_000_000)
    job_name: str | None = Field(default=None, max_length=300)
    nozzle_temperature: float | None = Field(default=None, ge=-100, le=600)
    nozzle_target_temperature: float | None = Field(default=None, ge=-100, le=600)
    bed_temperature: float | None = Field(default=None, ge=-100, le=250)
    bed_target_temperature: float | None = Field(default=None, ge=-100, le=250)
    chamber_temperature: float | None = Field(default=None, ge=-100, le=150)
    wifi_signal: str | None = Field(default=None, max_length=32)
    error_code: str | None = Field(default=None, max_length=80)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}


class PrinterBridgeSlotSnapshot(BaseModel):
    provider_index: int = Field(ge=0, le=1023)
    label: str | None = Field(default=None, max_length=100)
    kind: str = Field(default="slot", min_length=1, max_length=50)
    present: bool | None = None
    active_feed: bool | None = None
    spool_id: int | None = Field(default=None, ge=1)
    spool_identity_known: bool = False
    tag_uid: str | None = Field(default=None, min_length=1, max_length=128)
    tag_technology: Literal["unknown", "nfc", "uhf_rfid"] | None = None
    tag_format: str | None = Field(default=None, max_length=32)
    material: str | None = Field(default=None, max_length=80)
    color_hex: str | None = Field(default=None, pattern=r"^[0-9A-Fa-f]{6}$")
    remaining_percent: int | None = Field(default=None, ge=0, le=100)
    remaining_grams: int | None = Field(default=None, ge=0, le=100_000)

    @field_validator("tag_uid")
    @classmethod
    def normalize_uid(cls, value: str | None) -> str | None:
        return normalize_tag_uid(value) if value is not None else None

    @field_validator("tag_format")
    @classmethod
    def normalize_format(cls, value: str | None) -> str | None:
        return normalize_tag_format(value)

    @model_validator(mode="after")
    def tag_metadata_requires_uid(self) -> "PrinterBridgeSlotSnapshot":
        if self.tag_uid is None and (self.tag_technology is not None or self.tag_format is not None):
            raise ValueError("tag metadata requires tag_uid")
        if self.tag_uid is not None and self.tag_technology is None:
            self.tag_technology = "unknown"
        return self

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}


class PrinterBridgeSnapshotRequest(BaseModel):
    device_identity: PrinterIdentityEvidence | None = None
    material_system_id: int = Field(ge=1)
    provider: str = Field(min_length=1, max_length=50)
    transport: Literal["orca_plugin_lan", "edge_agent"]
    source_instance_id: str = Field(min_length=16, max_length=100)
    capabilities: list[CapabilityName] | None = Field(default=None, max_length=16)
    sequence: int | None = Field(default=None, ge=1, le=9_223_372_036_854_775_807)
    observed_at: datetime
    printer: PrinterBridgeStatusSnapshot | None = None
    slots: list[PrinterBridgeSlotSnapshot] = Field(default_factory=list, max_length=257)
    slot_topology_complete: bool = False
    inventory_key_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def unique_slot_indices(self) -> "PrinterBridgeSnapshotRequest":
        indices = [slot.provider_index for slot in self.slots]
        if len(indices) != len(set(indices)):
            raise ValueError("slot provider_index values must be unique within a snapshot")
        if self.printer is None and not self.slots:
            raise ValueError("a bridge snapshot must contain printer or slot facts")
        return self

    @field_validator("capabilities")
    @classmethod
    def unique_snapshot_capabilities(
        cls, value: list[CapabilityName] | None
    ) -> list[CapabilityName] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("capabilities must be unique")
        return value

    model_config = {"extra": "forbid"}


class PrinterBridgeSnapshotResponse(BaseModel):
    accepted: bool
    stale: bool
    connector_id: int
    material_system_id: int
    slots_seen: int
