"""Versioned Wiki article content and peer validation."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.wiki_article import WikiArticle


class WikiRevisionStatus(str, Enum):
    """Lifecycle state for an authored Wiki revision."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class WikiRevisionAuthorship(str, Enum):
    """Authority under which the revision was created."""

    EDITORIAL = "editorial"
    COMMUNITY = "community"


class WikiReviewVerdict(str, Enum):
    """Advisory peer-review verdict; it never publishes a revision by itself."""

    SUPPORT = "support"
    NEEDS_CHANGES = "needs_changes"


class WikiRevision(Base):
    """A content snapshot that is mutable only while it remains a draft."""

    __tablename__ = "wiki_revisions"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "revision_number", name="uq_wiki_revision_number"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    base_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_revisions.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[WikiRevisionStatus] = mapped_column(
        SQLEnum(
            WikiRevisionStatus,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            length=32,
        ),
        default=WikiRevisionStatus.DRAFT,
        server_default="draft",
        nullable=False,
        index=True,
    )
    authorship: Mapped[WikiRevisionAuthorship] = mapped_column(
        SQLEnum(
            WikiRevisionAuthorship,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            length=32,
        ),
        default=WikiRevisionAuthorship.COMMUNITY,
        server_default="community",
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    edit_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    article: Mapped["WikiArticle"] = relationship(
        "WikiArticle", back_populates="revisions", foreign_keys=[article_id]
    )
    base_revision: Mapped["WikiRevision | None"] = relationship(
        "WikiRevision", remote_side=[id], foreign_keys=[base_revision_id]
    )
    created_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by_id]
    )
    reviewed_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[reviewed_by_id]
    )
    peer_reviews: Mapped[list["WikiRevisionReview"]] = relationship(
        "WikiRevisionReview", back_populates="revision", cascade="all, delete-orphan"
    )


class WikiRevisionReview(Base):
    """One user's advisory validation of a submitted Wiki revision."""

    __tablename__ = "wiki_revision_reviews"
    __table_args__ = (
        UniqueConstraint(
            "revision_id", "reviewer_id", name="uq_wiki_revision_reviewer"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    revision_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verdict: Mapped[WikiReviewVerdict] = mapped_column(
        SQLEnum(
            WikiReviewVerdict,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    revision: Mapped["WikiRevision"] = relationship(
        "WikiRevision", back_populates="peer_reviews"
    )
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewer_id])
