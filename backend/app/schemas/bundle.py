"""Pydantic schemas for catalog Bundle / BundleImport."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BundleSummary(BaseModel):
    """Public-safe summary of a Bundle row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: UUID
    source: str
    uploaded_by_user_id: int | None
    filename: str
    sha256: str
    size_bytes: int
    status: str
    validation_summary: dict[str, Any] | None = None
    rejection_reason: str | None = None
    uploaded_at: datetime
    updated_at: datetime


class BundleImportSummary(BaseModel):
    """Public-safe summary of a BundleImport row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    bundle_id: int
    started_by_user_id: int | None
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    summary: dict[str, Any] | None = None
    error_text: str | None = None
    rolled_back_at: datetime | None = None
    rolled_back_by_user_id: int | None = None


class BundleDetail(BundleSummary):
    """Bundle with embedded import history."""

    imports: list[BundleImportSummary] = Field(default_factory=list)


class BundleListResponse(BaseModel):
    """Paginated list of bundles."""

    items: list[BundleSummary]
    total: int
    page: int
    size: int


class BundleCreateResponse(BaseModel):
    """Response after upload — id + inline validation result."""

    bundle_id: int
    status: str
    validation_summary: dict[str, Any] | None = None
