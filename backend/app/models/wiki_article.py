"""Wiki Article model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.wiki_category import WikiCategory
    from app.models.wiki_feedback import WikiArticleFeedback
    from app.models.wiki_revision import WikiRevision
    from app.models.wiki_space import WikiSpace


class WikiArticleStatus(str, Enum):
    """Статус статьи Wiki."""

    DRAFT = "draft"  # Черновик (только автор видит)
    PENDING_REVIEW = "pending_review"  # На модерации
    PUBLISHED = "published"  # Опубликовано
    REJECTED = "rejected"  # Отклонено


class WikiArticleProvenance(str, Enum):
    """Who is responsible for the published article identity."""

    EDITORIAL = "editorial"
    COMMUNITY = "community"


class WikiGuideProgress(Base):
    """Account-backed completion marker for one stable Wiki guide identity."""

    __tablename__ = "wiki_guide_progress"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "guide_id",
            name="uq_wiki_guide_progress_user_guide",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    guide_id: Mapped[str] = mapped_column(String(96), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WikiArticle(Base):
    """Статья Wiki."""

    __tablename__ = "wiki_articles"
    __table_args__ = (
        UniqueConstraint(
            "content_key",
            "language",
            name="uq_wiki_article_content_key_language",
        ),
    )

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Foreign keys
    category_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_categories.id"), nullable=False, index=True
    )
    space_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_spaces.id"), nullable=False, default=2, server_default="2", index=True
    )
    published_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "wiki_revisions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_wiki_article_published_revision",
        ),
        nullable=True,
    )

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # created_by_id: кто создал статью (nullable для обратной совместимости)

    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # updated_by_id: кто последним редактировал

    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # reviewed_by_id: кто одобрил/отклонил

    # Content
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    # slug: URL-friendly версия заголовка (например, "pla-for-beginners")

    content_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # content_key: стабильная идентичность одного материала во всех языках.

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # summary: краткое описание для карточки (1-2 предложения)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    # content: полный текст статьи в Markdown формате

    language: Mapped[str] = mapped_column(
        String(8), nullable=False, default="ru", server_default="ru", index=True
    )
    provenance: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WikiArticleProvenance.EDITORIAL.value,
        server_default=WikiArticleProvenance.EDITORIAL.value,
        index=True,
    )

    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # tags: массив тегов (например, ["PLA", "температура", "новичкам"])

    # Metadata
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # author: имя автора (отображаемое имя, может отличаться от username)

    status: Mapped[WikiArticleStatus] = mapped_column(
        SQLEnum(WikiArticleStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=WikiArticleStatus.DRAFT,
        server_default="draft",
        index=True,
    )
    # status: статус публикации

    # Обратная совместимость
    published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    # published: устаревшее поле, но оставляем для совместимости

    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # views: количество просмотров

    # Moderation
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # reviewed_at: когда была модерация

    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # rejection_reason: причина отклонения (если статус rejected)

    # Display order within category
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # order: порядок отображения внутри категории (меньше = выше)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    category: Mapped["WikiCategory"] = relationship("WikiCategory", back_populates="articles")
    space: Mapped["WikiSpace"] = relationship("WikiSpace", back_populates="articles")
    revisions: Mapped[list["WikiRevision"]] = relationship(
        "WikiRevision",
        back_populates="article",
        cascade="all, delete-orphan",
        foreign_keys="WikiRevision.article_id",
    )
    published_revision: Mapped["WikiRevision | None"] = relationship(
        "WikiRevision",
        foreign_keys=[published_revision_id],
        post_update=True,
    )
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped["User"] = relationship("User", foreign_keys=[updated_by_id])
    reviewed_by: Mapped["User"] = relationship("User", foreign_keys=[reviewed_by_id])
    feedback: Mapped[list["WikiArticleFeedback"]] = relationship(
        "WikiArticleFeedback", back_populates="article", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<WikiArticle(id={self.id}, title={self.title}, slug={self.slug}, status={self.status.value})>"
