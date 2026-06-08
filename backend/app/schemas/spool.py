"""Schemas for user spool (filament inventory) endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SpoolState = Literal["active", "shelf", "archived", "empty"]
SpoolSource = Literal["manual", "qr", "catalog", "orca_import"]


class SpoolFilamentInfo(BaseModel):
    """Embedded filament info returned with a spool."""

    id: int
    name: str
    material_type: str
    color_name: str | None
    color_hex: str | None
    brand_name: str | None
    price_per_kg: float | None

    model_config = {"from_attributes": True}


class SpoolResponse(BaseModel):
    """Full spool representation."""

    id: int
    user_id: int
    filament_id: int | None
    filament: SpoolFilamentInfo | None
    initial_weight_g: float
    used_weight_g: float
    remaining_weight_g: float
    remaining_pct: float
    price: float | None
    state: str
    source: str
    lot_nr: str | None
    comment: str | None
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None
    extra: dict | None

    model_config = {"from_attributes": True}


class SpoolCreateRequest(BaseModel):
    """Create a new spool."""

    filament_id: int | None = Field(default=None, ge=1)
    initial_weight_g: float = Field(..., gt=0, le=10_000)
    used_weight_g: float = Field(default=0.0, ge=0)
    price: float | None = Field(default=None, ge=0)
    state: SpoolState = "active"
    source: SpoolSource = "manual"
    lot_nr: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=500)


class SpoolUpdateRequest(BaseModel):
    """Partial update of a spool."""

    filament_id: int | None = Field(default=None, ge=1)
    initial_weight_g: float | None = Field(default=None, gt=0, le=10_000)
    used_weight_g: float | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, ge=0)
    state: SpoolState | None = None
    lot_nr: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=500)


class SpoolUseRequest(BaseModel):
    """Record filament usage (add to used_weight_g)."""

    delta_weight_g: float = Field(..., gt=0, le=5_000)
