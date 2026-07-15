"""Schemas for the administrative communication inbox."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

EmailSenderProfile = Literal["support", "partnerships", "pr"]
EmailDeliveryStatus = Literal[
    "received",
    "sent",
    "delivered",
    "delayed",
    "bounced",
    "complained",
]


class EmailAttachmentResponse(BaseModel):
    filename: str
    content_type: str | None = None
    size: int | None = None


class EmailMessageResponse(BaseModel):
    id: int
    direction: Literal["inbound", "outbound"]
    sender_email: str
    recipient_emails: list[str]
    subject: str
    text_body: str
    attachment_metadata: list[EmailAttachmentResponse]
    delivery_status: EmailDeliveryStatus | None
    read_at: datetime | None
    created_at: datetime


class EmailThreadSummaryResponse(BaseModel):
    id: int
    invite_id: int | None
    brand_id: int | None
    brand_name: str | None
    participant_email: str
    participant_name: str | None
    subject: str
    status: Literal["open", "closed"]
    unread_count: int
    last_message_at: datetime
    latest_preview: str
    latest_direction: Literal["inbound", "outbound"] | None
    suggested_sender_profile: EmailSenderProfile


class EmailThreadDetailResponse(EmailThreadSummaryResponse):
    messages: list[EmailMessageResponse]


class EmailThreadListResponse(BaseModel):
    items: list[EmailThreadSummaryResponse]
    total: int
    page: int
    size: int
    pages: int
    unread_total: int


class EmailThreadStatusUpdate(BaseModel):
    status: Literal["open", "closed"]


class EmailThreadCreate(BaseModel):
    to: EmailStr
    participant_name: str | None = Field(default=None, max_length=200)
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1, max_length=20_000)
    sender_profile: EmailSenderProfile = "support"

    @field_validator("participant_name")
    @classmethod
    def normalize_participant_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("subject", "body")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized


class EmailThreadReplyCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=20_000)
    sender_profile: EmailSenderProfile | None = None

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("body cannot be blank")
        return normalized
