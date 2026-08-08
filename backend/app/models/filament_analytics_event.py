"""Country-snapshotted analytics events for a catalog filament."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class FilamentAnalyticsEvent(Base):
    """A future-facing event that can be attributed to a market.

    Aggregate counters on ``Filament`` remain the historical global totals.
    This table supplies the territorial split without pretending old events
    had a country that was never captured.
    """

    __tablename__ = "filament_analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filament_id: Mapped[int] = mapped_column(
        ForeignKey("filaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
