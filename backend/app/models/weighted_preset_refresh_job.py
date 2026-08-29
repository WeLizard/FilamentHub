"""Durable, coalesced requests to rebuild a filament's weighted preset."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament


class WeightedPresetRefreshJob(Base):
    """Latest pending rebuild request for one catalogue filament.

    ``filament_id`` is the coalescing key: repeated mutations update the same
    row. The row is deleted only after a successful rebuild, so a process crash
    or transient database failure cannot silently lose the request.
    """

    __tablename__ = "weighted_preset_refresh_jobs"

    filament_id: Mapped[int] = mapped_column(
        ForeignKey("filaments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)

    filament: Mapped["Filament"] = relationship("Filament")
