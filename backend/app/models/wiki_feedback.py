"""Wiki Article Feedback model - для лайков и отзывов wiki статей."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.wiki_article import WikiArticle


class WikiFeedbackType(str, Enum):
    """Тип обратной связи wiki."""

    HELPFUL = "helpful"  # Статья была полезна (кнопка "Полезно")
    FEEDBACK = "feedback"  # Развернутый отзыв с текстом


class WikiArticleFeedback(Base):
    """Обратная связь по статьям Wiki (лайки и отзывы)."""

    __tablename__ = "wiki_article_feedback"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Foreign keys
    article_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # article_id: статья, к которой относится обратная связь

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # user_id: пользователь (null для анонимных лайков)

    # Type
    feedback_type: Mapped[WikiFeedbackType] = mapped_column(
        SQLEnum(WikiFeedbackType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    # feedback_type: тип обратной связи (helpful или feedback)

    # Content
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # comment: текст отзыва (только для feedback типа)

    # Анонимный идентификатор (для отслеживания дубликатов от анонимов)
    anonymous_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # anonymous_id: хэш IP или fingerprint для анонимов

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    article: Mapped["WikiArticle"] = relationship("WikiArticle", back_populates="feedback")
    user: Mapped["User"] = relationship("User", back_populates="wiki_feedback")

    # Уникальность: один пользователь = один лайк на статью
    # Анонимы могут лайкать, но ограничиваются по anonymous_id
    __table_args__ = (
        UniqueConstraint(
            'article_id', 'user_id', 'feedback_type',
            name='uq_wiki_feedback_user_article_type'
        ),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<WikiArticleFeedback(id={self.id}, article_id={self.article_id}, type={self.feedback_type.value})>"
