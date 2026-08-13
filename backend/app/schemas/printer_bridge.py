"""HTTP contract for local printer-bridge pairing and authorization."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PrinterBridgePairingCodeResponse(BaseModel):
    pairing_code: str
    expires_at: datetime


class PrinterBridgePairRequest(BaseModel):
    pairing_code: str = Field(min_length=8, max_length=32)
    provider: Literal["bambu"]
    transport: Literal["orca_plugin_lan"]
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
