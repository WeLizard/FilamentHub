"""Short-lived, purpose-bound email proofs for critical administrator actions."""

from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AdminConfirmationAction(str, Enum):
    BLOCK_USER = "block_user"
    PROMOTE_ADMIN = "promote_admin"
    DEMOTE_ADMIN = "demote_admin"
    DELETE_USER = "delete_user"
    CHANGE_ADMIN_EMAIL = "change_admin_email"


class AdminActionConfirmation(Base):
    __tablename__ = "admin_action_confirmations"
    __table_args__ = (
        CheckConstraint(
            "action IN ('block_user', 'promote_admin', 'demote_admin', "
            "'delete_user', 'change_admin_email')",
            name="ck_admin_confirmation_action",
        ),
        CheckConstraint("attempts >= 0 AND attempts <= 5", name="ck_admin_confirmation_attempts"),
        Index("ix_admin_confirmation_actor_time", "actor_user_id", "created_at"),
        Index("ix_admin_confirmation_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(43), primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    session_id: Mapped[str] = mapped_column(String(43), nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    email_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
