"""Durable operation records without credentials or request payloads."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditAction(str, Enum):
    PASSWORD_RESET = "password_reset"
    PASSWORD_CHANGE = "password_change"
    AUTH_REVOKED = "auth_revoked"


class AuditResult(str, Enum):
    SUCCESS = "success"


class AuditReason(str, Enum):
    RECOVERY_GRANT = "recovery_grant"
    AUTHENTICATED_CHANGE = "authenticated_change"
    LOGOUT = "logout"
    REFRESH_REUSE = "refresh_reuse"
    ADMIN_BLOCK = "admin_block"


class AuditEvent(Base):
    """An operation that committed; account erasure removes only its identity links."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('password_reset', 'password_change', 'auth_revoked')",
            name="ck_audit_events_action",
        ),
        CheckConstraint("result IN ('success')", name="ck_audit_events_result"),
        CheckConstraint(
            "reason IN ('recovery_grant', 'authenticated_change', 'logout', "
            "'refresh_reuse', 'admin_block')",
            name="ck_audit_events_reason",
        ),
        Index("ix_audit_events_actor_time", "actor_user_id", "occurred_at"),
        Index("ix_audit_events_target_time", "target_user_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
