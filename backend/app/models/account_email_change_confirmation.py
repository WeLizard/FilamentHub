"""One-time proofs for changing a regular account's email address."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountEmailChangeConfirmation(Base):
    __tablename__ = "account_email_change_confirmations"
    __table_args__ = (
        CheckConstraint(
            "attempts >= 0 AND attempts <= 5", name="ck_account_email_change_attempts"
        ),
        Index("ix_account_email_change_user_time", "user_id", "created_at"),
        Index("ix_account_email_change_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(43), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(43), nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_email_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    new_email_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    link_delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
