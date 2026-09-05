"""Persisted monthly brand releases contain no individual inventory records."""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BrandMonthlyAnalyticsRelease(Base):
    """One immutable release, including suppression, for each brand and month."""

    __tablename__ = "brand_monthly_analytics_releases"
    __table_args__ = (
        CheckConstraint(
            "spool_count IS NULL OR spool_count >= 10",
            name="ck_brand_monthly_release_cohort",
        ),
    )

    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), primary_key=True
    )
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    spool_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
