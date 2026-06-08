"""Calculator Pro history entry model."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class CalculatorHistoryEntry(Base):
    """Persisted Calculator Pro estimate snapshot for a user."""

    __tablename__ = "calculator_history_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    pricing_method: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    parsed_gcode: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    filament_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CalculatorHistoryEntry(id={self.id}, user_id={self.user_id}, title={self.title!r})>"
