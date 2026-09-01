"""Contracts for the stateless administrative catalog master-import."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CatalogImportDraft(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    brands: list[dict[str, Any]] = Field(default_factory=list)
    filaments: list[dict[str, Any]] = Field(default_factory=list)
    brand_markets: list[dict[str, Any]] = Field(default_factory=list)
    filament_markets: list[dict[str, Any]] = Field(default_factory=list)
    presets: list[dict[str, Any]] = Field(default_factory=list)


class CatalogImportPlanRow(BaseModel):
    sheet: str
    row: int
    key: str | None = None
    status: Literal["create", "update", "noop", "skipped", "error"]
    message: str | None = None
    changes: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CatalogImportPreview(BaseModel):
    draft: CatalogImportDraft
    rows: list[CatalogImportPlanRow]
    summary: dict[str, int]
    confirmation_token: str | None = None
    confirmation_expires_at: datetime | None = None


class CatalogImportApplyRequest(BaseModel):
    draft: CatalogImportDraft
    confirmation_token: str


class CatalogImportApplyResponse(BaseModel):
    batch_id: int
    summary: dict[str, int]


class CatalogImportBatchResponse(BaseModel):
    id: int
    filename: str
    source_sha256: str
    applied_by_user_id: int | None
    summary: dict[str, Any]
    applied_at: datetime


class CatalogImportHistoryResponse(BaseModel):
    items: list[CatalogImportBatchResponse]
    total: int
