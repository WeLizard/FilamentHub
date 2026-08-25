"""Server-side state for rotating refresh-token families."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class RefreshSession(Base):
    """One independently revocable browser or embedded-client login session.

    Only token fingerprints are persisted.  The current and immediately
    previous fingerprints make one short retry idempotent without retaining a
    bearer refresh token in the database.
    """

    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(43), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_token_fingerprint: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    previous_token_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_refresh_sessions_user_id", "user_id"),
        Index("ix_refresh_sessions_expires_at", "expires_at"),
    )
