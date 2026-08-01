"""Versioned evidence of user legal-document acceptance."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class UserLegalAcceptance(Base):
    """Immutable acceptance record for one document version."""

    __tablename__ = "user_legal_acceptances"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "document_type",
            "legal_document_pack",
            "document_version",
            name="uq_user_legal_acceptance_pack_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    document_version: Mapped[str] = mapped_column(String(32), nullable=False)
    related_privacy_policy_version: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    legal_document_pack: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="legacy"
    )
    acceptance_source: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="legal_acceptances")
