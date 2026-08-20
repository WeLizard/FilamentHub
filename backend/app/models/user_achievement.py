"""Immutable achievements earned by a FilamentHub user."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class UserAchievement(Base):
    """One useful or historical milestone, awarded at most once per user."""

    __tablename__ = "user_achievements"
    __table_args__ = (
        Index(
            "uq_user_achievements_user_code",
            "user_id",
            "code",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evidence_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
