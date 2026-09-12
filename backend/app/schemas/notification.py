"""Notification schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.notification import NotificationType


class NotificationBase(BaseModel):
    """Base schema for Notification."""

    type: NotificationType
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1)
    link: str | None = Field(None, max_length=500)
    extra_data: dict[str, Any] | None = None


class NotificationCreate(NotificationBase):
    """Schema for creating a notification."""

    user_id: int = Field(..., gt=0)


class NotificationResponse(NotificationBase):
    """Schema for Notification response."""

    id: int
    user_id: int
    read: bool
    read_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    """Schema for list of notifications."""

    items: list[NotificationResponse]
    total: int
    page: int
    size: int
    pages: int
    unread_count: int = Field(..., description="Количество непрочитанных уведомлений")


class NotificationFeedResponse(BaseModel):
    """Bounded keyset page of a user's notifications."""

    items: list[NotificationResponse]
    next_cursor: int | None = None
    unread_count: int = Field(..., description="Количество непрочитанных уведомлений")


class DeletedPresetDecisionItemResponse(BaseModel):
    id: int
    preset_id: int
    preset_name: str
    bundle_preset_name: str | None = None
    is_created: bool
    is_saved: bool

    model_config = ConfigDict(from_attributes=True)


class DeletedPresetDecisionFeedResponse(BaseModel):
    items: list[DeletedPresetDecisionItemResponse]
    next_cursor: int | None = None
    remaining_count: int
    created_count: int
    saved_count: int
