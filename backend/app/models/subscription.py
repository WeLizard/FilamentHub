"""Subscription model — per-user Pro/premium entitlement (payment-ready)."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class SubscriptionStatus(str, Enum):
    """Subscription lifecycle status (mirrors common billing providers)."""

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"


class Subscription(Base):
    """Per-user Pro subscription. One row per user; status drives entitlement.

    Payment-ready: ``provider`` / ``provider_subscription_id`` / ``current_period_end``
    are set by a future payment webhook. Until payments launch the paywall is not
    enforced (see ``app_settings.paywall_enforced``) and everyone stays on trial.
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SQLEnum(SubscriptionStatus, values_callable=lambda x: [e.value for e in x]),
        default=SubscriptionStatus.TRIALING,
        nullable=False,
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Complimentary (admin-granted) access — not tied to a payment.
    is_comp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Payment provider linkage (reserved; unused until payments launch).
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="subscription")

    def __repr__(self) -> str:
        return f"<Subscription(user_id={self.user_id}, status={self.status.value}, is_comp={self.is_comp})>"
