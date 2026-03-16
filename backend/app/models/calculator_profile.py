"""User calculator profile — server-persisted calculator & quote settings."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class UserCalculatorProfile(Base):
    """Per-user calculator economics + quote profile (replaces localStorage)."""

    __tablename__ = "user_calculator_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Economics (static calculator settings) ──────────────────────────
    electricity_cost_per_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=6.0)
    printer_power_w: Mapped[float] = mapped_column(Float, nullable=False, default=350.0)
    modeling_rate_per_hour: Mapped[float] = mapped_column(Float, nullable=False, default=934.0)
    postprocessing_rate_per_hour: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    printing_rate_per_hour: Mapped[float] = mapped_column(Float, nullable=False, default=170.0)
    amortization_rate_per_hour: Mapped[float] = mapped_column(Float, nullable=False, default=16.0)
    overhead_percent: Mapped[float] = mapped_column(Float, nullable=False, default=20.0)
    markup_percent: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)
    tax_rate_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fixed_costs: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bed_prep_cost_per_print: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    min_order_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    round_to_nearest: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    rounding_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="up")

    # ── Quote profile ───────────────────────────────────────────────────
    seller_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    seller_inn: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    seller_phone: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    payment_terms: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    validity_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    disclaimer_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="not_offer")
    currency: Mapped[str] = mapped_column(String(4), nullable=False, default="₽")
    quote_number_prefix: Mapped[str] = mapped_column(String(32), nullable=False, default="КП")

    # ── Timestamps ──────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<UserCalculatorProfile(id={self.id}, user_id={self.user_id})>"
