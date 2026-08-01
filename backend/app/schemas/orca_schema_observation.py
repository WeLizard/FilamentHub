"""Admin API schemas for OrcaSlicer schema observations."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

OrcaPresetScope = Literal["filament", "process", "machine"]
OrcaSchemaObservationStatus = Literal["new", "acknowledged", "ignored"]


class OrcaSchemaObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: OrcaPresetScope
    field_name: str
    value_shape: str
    status: OrcaSchemaObservationStatus
    occurrences: int
    registry_version: str
    first_source: str
    last_source: str
    first_seen_at: datetime
    last_seen_at: datetime
    reviewed_at: datetime | None
    reviewed_by_user_id: int | None


class OrcaSchemaObservationListResponse(BaseModel):
    items: list[OrcaSchemaObservationResponse]
    total: int
    new_count: int
    page: int
    size: int
    pages: int
    registry_version: str


class OrcaSchemaObservationUpdate(BaseModel):
    status: OrcaSchemaObservationStatus
