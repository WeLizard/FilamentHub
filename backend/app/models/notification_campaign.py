"""Auditable two-step campaigns for administrative in-app broadcasts."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class NotificationCampaign(Base):
    """A recipient snapshot that must be previewed before it can be sent."""

    __tablename__ = "notification_campaigns"
    __table_args__ = (
        CheckConstraint("channel = 'in_app'", name="ck_notification_campaign_channel"),
        CheckConstraint(
            "audience IN ('active', 'all', 'selected')",
            name="ck_notification_campaign_audience",
        ),
        CheckConstraint(
            "status IN ('draft', 'sent', 'cancelled')",
            name="ck_notification_campaign_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="in_app")
    audience: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    confirmation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    recipients: Mapped[list["NotificationCampaignRecipient"]] = relationship(
        "NotificationCampaignRecipient",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )


class NotificationCampaignRecipient(Base):
    """Immutable recipient snapshot captured during campaign preview."""

    __tablename__ = "notification_campaign_recipients"
    __table_args__ = (
        UniqueConstraint("campaign_id", "user_id", name="uq_notification_campaign_recipient"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("notification_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    campaign: Mapped[NotificationCampaign] = relationship(
        "NotificationCampaign", back_populates="recipients"
    )
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
