"""Schemas for the physical-printer and material-system contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CapabilityName = Literal[
    "read",
    "write",
    "presence",
    "spool_identity",
    "consumption",
    "local_command",
]


class PhysicalPrinterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    printer_id: int | None = Field(default=None, ge=1)
    printer_profile_ids: list[int] = Field(default_factory=list, max_length=64)

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
    slots: list[MaterialSlotCreate] = Field(default_factory=list, max_length=256)

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


class MaterialSlotResponse(BaseModel):
    id: int
    provider_index: int
    label: str | None
    kind: str
    active: bool

    model_config = {"from_attributes": True}


class MaterialSystemResponse(BaseModel):
    id: int
    name: str
    kind: str
    provider: str
    capabilities: list[str]
    active: bool
    slots: list[MaterialSlotResponse]

    model_config = {"from_attributes": True}


class PhysicalPrinterConnectorResponse(BaseModel):
    id: int
    material_system_id: int | None
    provider: str
    transport: str
    capabilities: list[str]
    active: bool
    last_seen_at: datetime | None

    model_config = {"from_attributes": True}


class PhysicalPrinterResponse(BaseModel):
    id: int
    logical_id: str
    printer_id: int | None
    name: str
    printer_profile_ids: list[int]
    material_systems: list[MaterialSystemResponse]
    connectors: list[PhysicalPrinterConnectorResponse]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, printer: Any) -> "PhysicalPrinterResponse":
        systems = sorted(printer.material_systems, key=lambda system: system.id)
        for system in systems:
            system.slots.sort(key=lambda slot: (slot.provider_index, slot.id))
        return cls(
            id=printer.id,
            logical_id=printer.logical_id,
            printer_id=printer.printer_id,
            name=printer.name,
            printer_profile_ids=sorted(
                link.printer_profile_id for link in printer.profile_links
            ),
            material_systems=[
                MaterialSystemResponse.model_validate(system) for system in systems
            ],
            connectors=[
                PhysicalPrinterConnectorResponse.model_validate(connector)
                for connector in sorted(printer.connectors, key=lambda item: item.id)
            ],
            created_at=printer.created_at,
            updated_at=printer.updated_at,
        )
