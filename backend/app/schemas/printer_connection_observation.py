"""Schemas for the OrcaSlicer plugin printer-connection observation stream."""

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
