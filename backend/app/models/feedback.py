"""Feedback model for user feedback and bug reports."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class FeedbackType(str, Enum):
    """Типы обратной связи."""

    BUG = "bug"  # Сообщение об ошибке
    FEATURE = "feature"  # Предложение фичи
    QUESTION = "question"  # Вопрос
    OTHER = "other"  # Другое


class FeedbackStatus(str, Enum):
    """Статусы обратной связи."""

    OPEN = "open"  # Открыто (новое)
    IN_PROGRESS = "in_progress"  # В работе
    RESOLVED = "resolved"  # Решено
    CLOSED = "closed"  # Закрыто


class Feedback(Base):
    """Модель обратной связи от пользователей."""

    __tablename__ = "feedback"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Foreign keys
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    # user_id: может быть None для анонимных сообщений

    # Feedback data
    type: Mapped[FeedbackType] = mapped_column(
        SQLEnum(FeedbackType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # User contact info (для анонимных сообщений)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # email: email пользователя (для ответа, если сообщение анонимное)

    # Source context (откуда пришёл отзыв)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # source: тип источника (wiki_article, preset, catalog, general)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # source_url: URL страницы откуда отправили отзыв
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # source_id: ID связанного объекта (article_id, preset_id и т.д.)

    # Status
    status: Mapped[FeedbackStatus] = mapped_column(
        SQLEnum(FeedbackStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=FeedbackStatus.OPEN,
        index=True,
    )

    # Admin response (опционально)
    admin_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    responded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # responded_by: ID админа, который ответил на сообщение

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[user_id], back_populates="feedback_messages"
    )
    responder: Mapped["User | None"] = relationship(
        "User", foreign_keys=[responded_by]
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Feedback(id={self.id}, type={self.type.value}, status={self.status.value})>"


