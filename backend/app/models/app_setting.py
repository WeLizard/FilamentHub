"""Global application settings (key-value) — proper replacement for ad-hoc flag files."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AppSetting(Base):
    """One row per global setting key (e.g. ``paywall_enforced``, ``trial_days``).

    Values are stored as text and parsed by the owning service. Shared across all
    workers via the database (unlike the old per-file flag).
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
