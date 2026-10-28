"""A pair of catalog filaments an administrator should merge or dismiss."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class FilamentDuplicateReview(Base):
    __tablename__ = "filament_duplicate_reviews"
    __table_args__ = (
        UniqueConstraint("filament_id", "candidate_id", name="uq_filament_dup_review_pair"),
        Index("ix_filament_dup_review_status", "status"),
        Index("ix_filament_dup_review_candidate", "candidate_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # The newer record; the pair is always stored as (newer, older) by id.
    filament_id: Mapped[int] = mapped_column(
        ForeignKey("filaments.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("filaments.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
