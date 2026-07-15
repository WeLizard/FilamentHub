"""Administrative email conversations and messages."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.brand_invite import BrandInvite
    from app.models.user import User


class EmailThread(Base):
    """A minimal CRM thread for external email communication."""

    __tablename__ = "email_threads"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    invite_id: Mapped[int | None] = mapped_column(
        ForeignKey("brand_invites.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", ondelete="SET NULL"), nullable=True, index=True
    )
    participant_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    participant_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    reply_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    sender_profile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open", index=True
    )
    unread_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    invite: Mapped["BrandInvite | None"] = relationship("BrandInvite", foreign_keys=[invite_id])
    brand: Mapped["Brand | None"] = relationship("Brand", foreign_keys=[brand_id])
    messages: Mapped[list["EmailMessage"]] = relationship(
        "EmailMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EmailMessage.created_at",
    )


class EmailMessage(Base):
    """One safe plain-text message inside an administrative email thread."""

    __tablename__ = "email_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_emails: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    text_body: Mapped[str] = mapped_column(Text, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    provider_event_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    internet_message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attachment_metadata: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    delivery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sent_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    thread: Mapped["EmailThread"] = relationship("EmailThread", back_populates="messages")
    sent_by: Mapped["User | None"] = relationship("User", foreign_keys=[sent_by_id])
