"""Physical NFC/RFID tags linked to account-owned spools."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SpoolTag(Base):
    """One hardware UID linked to one UserSpool inside one account."""

    __tablename__ = "spool_tags"
    __table_args__ = (
        UniqueConstraint("user_id", "uid", name="uq_spool_tag_user_uid"),
        Index("ix_spool_tag_user_spool", "user_id", "spool_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    spool_id: Mapped[int] = mapped_column(
        ForeignKey("user_spools.id", ondelete="CASCADE"), nullable=False
    )
    uid: Mapped[str] = mapped_column(String(64), nullable=False)
    technology: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
