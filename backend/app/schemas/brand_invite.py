"""Pydantic schemas for brand invitations."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

BrandInviteTargetType = Literal["new", "existing"]
BrandInviteMemberRole = Literal["owner", "editor"]
BrandInviteSenderProfile = Literal["partnerships", "pr", "transactional"]


class BrandInviteCreate(BaseModel):
    """Admin creates an invitation."""

    email: EmailStr
    target_type: BrandInviteTargetType = "new"
    brand_id: int | None = Field(None, gt=0)
    brand_name: str | None = Field(None, min_length=1, max_length=100)
    organization_id: int | None = Field(None, gt=0)
    organization_name: str | None = Field(None, min_length=1, max_length=150)
    member_role: BrandInviteMemberRole = "owner"
    sender_profile: BrandInviteSenderProfile = "partnerships"
    expires_days: int = Field(14, ge=1, le=90)

    @model_validator(mode="after")
    def validate_target(self) -> "BrandInviteCreate":
        if self.target_type == "existing" and self.brand_id is None:
            raise ValueError("brand_id is required for an existing brand invitation")
        if self.target_type == "new" and not (self.brand_name and self.brand_name.strip()):
            raise ValueError("brand_name is required for a new brand invitation")
        return self


class BrandInviteBatchCreate(BaseModel):
    """Admin sends independently trackable invitations to several recipients."""

    emails: list[EmailStr] = Field(..., min_length=1, max_length=100)
    target_type: BrandInviteTargetType = "new"
    brand_id: int | None = Field(None, gt=0)
    brand_name: str | None = Field(None, min_length=1, max_length=100)
    organization_id: int | None = Field(None, gt=0)
    organization_name: str | None = Field(None, min_length=1, max_length=150)
    member_role: BrandInviteMemberRole = "owner"
    sender_profile: BrandInviteSenderProfile = "partnerships"
    expires_days: int = Field(14, ge=1, le=90)

    @model_validator(mode="after")
    def validate_target(self) -> "BrandInviteBatchCreate":
        if self.target_type == "existing" and self.brand_id is None:
            raise ValueError("brand_id is required for an existing brand invitation")
        if self.target_type == "new" and not (self.brand_name and self.brand_name.strip()):
            raise ValueError("brand_name is required for a new brand invitation")
        return self


class BrandInviteAdminResponse(BaseModel):
    """Full invite view for the admin panel."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    token: str
    email: str
    brand_name: str | None = None
    target_type: str
    brand_id: int | None = None
    organization_id: int | None = None
    member_role: str
    purpose: str
    all_brands: bool
    sender_profile: str
    batch_id: str | None = None
    send_status: str
    send_error: str | None = None
    pre_verified: bool
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    invite_url: str | None = None


class BrandInvitePublicResponse(BaseModel):
    """What the public accept page sees for a given token."""

    valid: bool
    brand_name: str | None = None
    email: str | None = None
    target_type: str | None = None
    brand_id: int | None = None
    purpose: str | None = None
    member_role: str | None = None
    reason: str | None = None  # ERR-код, если невалиден


class BrandInviteAccept(BaseModel):
    """Compatibility payload; the server-owned invitation target is authoritative."""

    brand_name: str | None = Field(None, min_length=1, max_length=100)


class BrandInviteAcceptResponse(BaseModel):
    """Result of accepting an invite."""

    brand_id: int
    brand_name: str
    organization_id: int
    member_role: str
