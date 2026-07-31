"""Feedback schemas."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class FeedbackType(str, Enum):
    """Типы обратной связи."""

    BUG = "bug"
    FEATURE = "feature"
    QUESTION = "question"
    OTHER = "other"


class FeedbackStatus(str, Enum):
    """Статусы обратной связи."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class FeedbackBase(BaseModel):
    """Базовая схема обратной связи."""

    type: str = Field(..., description="Тип обратной связи")
    subject: str = Field(..., max_length=200, description="Тема сообщения")
    message: str = Field(..., description="Текст сообщения")
    email: str | None = Field(None, description="Email для ответа (для анонимных сообщений)")
    # Source context
    source: str | None = Field(None, description="Источник: wiki_article, preset, catalog, general")
    source_url: str | None = Field(None, max_length=500, description="URL страницы откуда отправили")
    source_id: int | None = Field(None, description="ID связанного объекта")

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        """Валидация email: пустая строка конвертируется в None, валидация формата только если есть значение."""
        if v is None:
            return None
        v = v.strip() if isinstance(v, str) else v
        if not v or v == '':
            return None

        # Простая валидация формата email
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('Invalid email format')
        return v


class FeedbackCreate(FeedbackBase):
    """Схема для создания обратной связи."""

    pass


class FeedbackUpdate(BaseModel):
    """Схема для обновления обратной связи (админ)."""

    status: FeedbackStatus | None = None
    admin_response: str | None = None
    reply_idempotency_key: UUID | None = None


class FeedbackMessageCreate(BaseModel):
    """Schema for adding a message to an existing feedback conversation."""

    message: str = Field(..., min_length=1, max_length=10_000)
    idempotency_key: UUID

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty")
        return value


class FeedbackMessageResponse(BaseModel):
    """One message in a feedback conversation."""

    id: int
    author_user_id: int | None
    author_type: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackResponse(BaseModel):
    """Схема ответа с обратной связью."""

    id: int
    user_id: int | None
    type: str
    subject: str
    message: str
    email: str | None
    # Source context
    source: str | None = None
    source_url: str | None = None
    source_id: int | None = None
    # Status
    status: str
    admin_response: str | None
    admin_response_at: datetime | None
    responded_by: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FeedbackDetailResponse(FeedbackResponse):
    """Feedback with its ordered conversation."""

    messages: list[FeedbackMessageResponse]


class FeedbackListResponse(BaseModel):
    """Схема списка обратной связи."""

    items: list[FeedbackResponse]
    total: int
    page: int
    size: int
    pages: int
