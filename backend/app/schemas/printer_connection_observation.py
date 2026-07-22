"""Schemas for the OrcaSlicer plugin printer-connection observation stream."""

from datetime import datetime

from pydantic import BaseModel, Field


class PrinterConnectionObservationIn(BaseModel):
    preset_name: str | None = Field(None, max_length=200)
    printer_settings_id: str | None = Field(None, max_length=200)
    inherits: str | None = Field(None, max_length=200)
    printer_model: str | None = Field(None, max_length=200)
    print_host: str | None = Field(None, max_length=500)
    host_type: str | None = Field(None, max_length=50)

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


class PrinterConnectionBindingResponse(BaseModel):
    """Safe display view of a connection binding — never identity, never secrets.

    The physical printer is identified by physical_printer_id; the endpoint is a
    volatile label. No access codes / tokens / raw credentials are exposed."""

    physical_printer_id: int
    provider: str | None
    display_endpoint: str | None
    last_seen_at: datetime
