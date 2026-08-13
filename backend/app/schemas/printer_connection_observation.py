"""Schemas for the OrcaSlicer plugin printer-connection observation stream."""

from datetime import datetime

from pydantic import BaseModel, Field


class PrinterConnectionObservationIn(BaseModel):
    connection_ref: str | None = Field(None, max_length=120)
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


class PrinterConnectionObserveResponse(BaseModel):
    accepted: int
    matched: int
    unmatched: int
    created: int = 0


class PrinterConnectionBindingResponse(BaseModel):
    """Safe display view of a connection binding — never identity, never secrets.

    The physical printer is identified by physical_printer_id; the endpoint is a
    volatile label. No access codes / tokens / raw credentials are exposed."""

    physical_printer_id: int
    connection_ref: str | None = None
    provider: str | None
    display_endpoint: str | None
    endpoint_shared: bool = False
    last_seen_at: datetime
