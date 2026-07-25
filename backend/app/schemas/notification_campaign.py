"""Schemas for previewed and auditable in-app notification campaigns."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

NotificationCampaignAudience = Literal["active", "all", "selected"]
NotificationCampaignStatus = Literal["draft", "sent", "cancelled", "expired"]


class NotificationCampaignDraft(BaseModel):
    audience: NotificationCampaignAudience = "active"
    user_ids: list[int] = Field(default_factory=list, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=5_000)
    link: str | None = Field(default=None, max_length=500)

    @field_validator("title", "message")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("user_ids")
    @classmethod
    def normalize_user_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(user_id for user_id in value if user_id > 0))

    @field_validator("link")
    @classmethod
    def normalize_internal_link(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if (
            not normalized.startswith("/")
            or normalized.startswith("//")
            or "\\" in normalized
            or any(ord(character) < 32 for character in normalized)
        ):
            raise ValueError("link must be an internal application path")
        return normalized

    @model_validator(mode="after")
    def validate_audience(self) -> "NotificationCampaignDraft":
        if self.audience == "selected" and not self.user_ids:
            raise ValueError("selected audience requires at least one user")
        if self.audience != "selected" and self.user_ids:
            raise ValueError("user_ids are only allowed for selected audience")
        return self


class NotificationCampaignRecipientPreview(BaseModel):
    id: int
    email: str
    username: str
    full_name: str | None


class NotificationCampaignPreviewResponse(BaseModel):
    campaign_id: str
    audience: NotificationCampaignAudience
    recipient_count: int
    recipient_sample: list[NotificationCampaignRecipientPreview]
    excluded_user_ids: list[int]
    title: str
    message: str
    link: str | None
    confirmation_token: str
    confirmation_expires_at: datetime


class NotificationCampaignConfirm(BaseModel):
    confirmation_token: str = Field(..., min_length=32, max_length=2_048)


class NotificationCampaignSendResponse(BaseModel):
    campaign_id: str
    status: Literal["sent"]
    recipient_count: int
    replayed: bool
    sent_at: datetime


class NotificationCampaignHistoryItem(BaseModel):
    campaign_id: str
    audience: NotificationCampaignAudience
    title: str
    message: str
    link: str | None
    recipient_count: int
    status: NotificationCampaignStatus
    created_by_id: int
    created_by_name: str
    created_at: datetime
    confirmation_expires_at: datetime
    sent_at: datetime | None


class NotificationCampaignHistoryResponse(BaseModel):
    items: list[NotificationCampaignHistoryItem]
    total: int
    page: int
    size: int
    pages: int
