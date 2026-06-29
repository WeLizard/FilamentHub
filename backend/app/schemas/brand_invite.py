"""Pydantic schemas for brand invitations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BrandInviteCreate(BaseModel):
    """Admin creates an invitation."""

    email: EmailStr
    brand_name: str | None = Field(None, max_length=100)
    expires_days: int = Field(14, ge=1, le=90)


class BrandInviteAdminResponse(BaseModel):
    """Full invite view for the admin panel."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    token: str
    email: str
    brand_name: str | None = None
    pre_verified: bool
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime
    invite_url: str | None = None


class BrandInvitePublicResponse(BaseModel):
    """What the public accept page sees for a given token."""

    valid: bool
    brand_name: str | None = None
    email: str | None = None
    reason: str | None = None  # ERR-код, если невалиден


class BrandInviteAccept(BaseModel):
    """Accept payload — the brand name to create (prefilled from the invite)."""

    brand_name: str = Field(..., min_length=1, max_length=100)


class BrandInviteAcceptResponse(BaseModel):
    """Result of accepting an invite."""

    brand_id: int
    brand_name: str
