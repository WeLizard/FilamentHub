"""Provider-neutral API schemas for physical spool tags."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.tag_identity import normalize_tag_format, normalize_tag_uid

TagTechnology = Literal["unknown", "nfc", "uhf_rfid"]


class SpoolTagCreateRequest(BaseModel):
    uid: str = Field(min_length=1, max_length=128)
    technology: TagTechnology = "unknown"
    format: str | None = Field(default=None, max_length=64)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    @field_validator("uid")
    @classmethod
    def normalize_uid(cls, value: str) -> str:
        return normalize_tag_uid(value)

    @field_validator("format")
    @classmethod
    def normalize_format(cls, value: str | None) -> str | None:
        return normalize_tag_format(value)


class SpoolTagResponse(BaseModel):
    id: int
    spool_id: int
    uid: str
    technology: TagTechnology
    format: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SpoolTagResolutionResponse(BaseModel):
    uid: str
    status: Literal["matched", "unlinked"]
    spool_id: int | None

