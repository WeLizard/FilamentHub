"""Schemas for the OrcaSlicer plugin printer-connection observation stream."""

from datetime import datetime

from pydantic import BaseModel, Field


class PrinterIdentityEvidence(BaseModel):
    """Account-scoped HMAC of a provider identifier read from the local device.

    Shared by desktop, Edge and future mobile adapters. It is matching evidence,
    never authentication or permission to operate a printer.
    """

    kind: str = Field(pattern=r"^[a-z][a-z0-9_]{1,49}$")
    token: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = {"extra": "forbid"}


class PrinterConnectionObservationIn(BaseModel):
    connection_ref: str | None = Field(None, max_length=120)
    endpoint_token: str | None = Field(None, pattern=r"^[0-9a-f]{64}$")
    device_identity: PrinterIdentityEvidence | None = None
    has_connection: bool | None = None
    preset_name: str | None = Field(None, max_length=200)
    printer_settings_id: str | None = Field(None, max_length=200)
    inherits: str | None = Field(None, max_length=200)
    printer_model: str | None = Field(None, max_length=200)
    nozzle_diameter: str | None = Field(None, max_length=20)
    vendor_id: str | None = Field(None, max_length=100)
    profile_fingerprint: str | None = Field(None, min_length=64, max_length=64)
    print_host: str | None = Field(None, max_length=500)
    host_type: str | None = Field(None, max_length=50)
    is_system: bool = False
    is_visible: bool = Field(
        default=False,
        description="System preset is enabled and visible in this Orca installation.",
    )
    has_technical_changes: bool | None = Field(
        default=None,
        description=(
            "Whether the user preset differs technically from its loaded parent; "
            "null for older plugin payloads."
        ),
    )
    is_current: bool = Field(
        default=False,
        description="Пресет выбран в слайсере в момент наблюдения.",
    )

    model_config = {"str_strip_whitespace": True}


class PrinterConnectionObserveRequest(BaseModel):
    observations: list[PrinterConnectionObservationIn] = Field(
        default_factory=list, max_length=256
    )
    source_instance_id: str | None = Field(None, max_length=100)
    snapshot_complete: bool = True


class PrinterConnectionObserveResponse(BaseModel):
    accepted: int
    matched: int
    unmatched: int
    created: int = 0
    pending: int = 0


class PrinterConnectionBindingResponse(BaseModel):
    """Safe display view of a connection binding — never identity, never secrets.

    The physical printer is identified by physical_printer_id; the endpoint is a
    volatile label. No access codes / tokens / raw credentials are exposed."""

    id: int
    physical_printer_id: int
    physical_printer_name: str
    connection_ref: str | None = None
    preset_name: str | None = None
    provider: str | None
    display_endpoint: str | None
    endpoint_shared: bool = False
    last_seen_at: datetime
    status: str = "bound"


class PrinterConnectionBindingAssignRequest(BaseModel):
    physical_printer_id: int = Field(..., gt=0)


class PrinterConnectionResolveRequest(BaseModel):
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    physical_printer_id: int | None = Field(None, gt=0)
    create_new: bool = False
