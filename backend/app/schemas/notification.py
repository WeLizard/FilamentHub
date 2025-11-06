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

