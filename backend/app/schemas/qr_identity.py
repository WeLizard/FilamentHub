"""Schemas for personal QR identities and manufacturer batch issuance."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class QrRevisionRequest(BaseModel):
    """Optimistic revision required by a lifecycle transition."""

    revision: int = Field(..., ge=1)


class QrRotateRequest(QrRevisionRequest):
    """A replay-safe token rotation request."""

    idempotency_key: str = Field(..., min_length=8, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_idempotency_key(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 8:
            raise ValueError("idempotency key is too short")
        return normalized


class QrReplaceMaterialRequest(QrRotateRequest):
    """Explicitly replace a spool material and its user-issued QR identity."""

    filament_id: int = Field(..., ge=1)
    confirm_reprint: Literal[True]


class UserSpoolQrResponse(BaseModel):
    """Private owner view of one QR identity linked to a spool."""

    spool_id: int
    filament_id: int
    issuer: Literal["user", "manufacturer"]
    state: Literal["active", "pending_retirement", "linked"]
    revision: int
    short_code: str
    target_url: str
    retirement_started_at: datetime | None = None
    purge_after: datetime | None = None


class UserSpoolQrListResponse(BaseModel):
    items: list[UserSpoolQrResponse]
    total: int
    offset: int
    limit: int


class ManufacturerQrBatchItemRequest(BaseModel):
    filament_id: int = Field(..., ge=1)
    quantity: int = Field(..., ge=1, le=1_000_000)


class ManufacturerQrBatchCreateRequest(BaseModel):
    brand_id: int = Field(..., ge=1)
    mode: Literal["sku", "serialized"]
    items: list[ManufacturerQrBatchItemRequest] = Field(..., min_length=1, max_length=100)

    @field_validator("items")
    @classmethod
    def unique_filaments(
        cls, value: list[ManufacturerQrBatchItemRequest]
    ) -> list[ManufacturerQrBatchItemRequest]:
        ids = [item.filament_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("filament ids must be unique inside a batch")
        return value


class ManufacturerQrBatchItemResponse(BaseModel):
    filament_id: int
    quantity: int
    ordinal_start: int
    product_qr_code: str


class ManufacturerQrBatchResponse(BaseModel):
    public_id: str
    organization_id: int
    brand_id: int
    mode: Literal["sku", "serialized"]
    status: Literal["active", "cancelled"]
    total_quantity: int
    manifest_revision: int
    created_at: datetime
    updated_at: datetime
    items: list[ManufacturerQrBatchItemResponse]


class ManufacturerQrBatchListResponse(BaseModel):
    items: list[ManufacturerQrBatchResponse]
    total: int
    offset: int
    limit: int


class ManufacturerQrPayloadResponse(BaseModel):
    ordinal: int
    filament_id: int
    short_code: str
    target_url: str


class ManufacturerQrPayloadPage(BaseModel):
    batch_id: str
    manifest_revision: int
    offset: int
    limit: int
    total: int
    items: list[ManufacturerQrPayloadResponse]
    next_offset: int | None


class ManufacturerQrExceptionRequest(BaseModel):
    ordinal: int = Field(..., ge=0)
    action: Literal["revoke", "scrap", "restore"]
    idempotency_key: str = Field(..., min_length=8, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_exception_key(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 8:
            raise ValueError("idempotency key is too short")
        return normalized


class ManufacturerQrExceptionResponse(BaseModel):
    ordinal: int
    status: Literal["revoked", "scrapped"] | None
    manifest_revision: int


class ManufacturerQrClaimRequest(BaseModel):
    spool_id: int = Field(..., ge=1)


class ManufacturerQrClaimResponse(BaseModel):
    filament_id: int
    spool_id: int
    issuer: Literal["manufacturer"] = "manufacturer"
    state: Literal["linked"] = "linked"
