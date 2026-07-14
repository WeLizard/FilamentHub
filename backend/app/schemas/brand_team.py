"""Schemas for organization team management behind a public brand."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

TeamRole = Literal["owner", "editor"]
RequestDecision = Literal["approved", "rejected"]


class TeamInviteCreate(BaseModel):
    email: EmailStr
    role: TeamRole = "editor"
    all_brands: bool = False
    send_email: bool = True
    expires_days: int = Field(14, ge=1, le=90)

    @model_validator(mode="after")
    def owners_cover_the_organization(self) -> "TeamInviteCreate":
        if self.role == "owner":
            self.all_brands = True
        return self


class TeamInviteResponse(BaseModel):
    id: int
    email: str
    role: TeamRole
    all_brands: bool
    brand_id: int
    status: Literal["pending", "sent", "failed", "accepted", "expired", "revoked"]
    invite_url: str
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    send_error: str | None = None


class TeamMemberResponse(BaseModel):
    membership_id: int
    user_id: int
    username: str
    email: str
    role: TeamRole
    all_brands: bool
    brand_ids: list[int]
    joined_at: datetime
    is_current_user: bool


class TeamJoinRequestResponse(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    message: str | None = None
    created_at: datetime


class BrandTeamWorkspaceResponse(BaseModel):
    organization_id: int
    organization_name: str
    current_role: TeamRole
    can_manage_team: bool
    members: list[TeamMemberResponse]
    pending_invites: list[TeamInviteResponse]
    pending_join_requests: list[TeamJoinRequestResponse]


class TeamMembershipUpdate(BaseModel):
    role: TeamRole
    all_brands: bool = False
    brand_ids: list[int] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_scope(self) -> "TeamMembershipUpdate":
        self.brand_ids = list(dict.fromkeys(self.brand_ids))
        if self.role == "owner":
            self.all_brands = True
            self.brand_ids = []
        elif not self.all_brands and not self.brand_ids:
            raise ValueError("At least one brand is required for a scoped editor")
        return self


class OwnershipTransferRequest(BaseModel):
    target_membership_id: int = Field(gt=0)


class TeamJoinRequestDecision(BaseModel):
    status: RequestDecision
    rejection_reason: str | None = Field(None, max_length=1000)
