"""Currencies the calculator and quotes can be priced in."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Currency(Base):
    """A currency as a reference row rather than a list baked into the frontend.

    Symbols repeat across currencies (kr, ¥, $), so the code is the identity and the
    symbol is presentation only.
    """

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(4), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    # ISO 4217 minor units: yen and won have none, and printing "1400.00 ¥" is wrong.
    decimals: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    # Smallest sensible "round the quote to" step. Ten roubles is small change, ten
    # dollars is a noticeable part of a small order.
    rounding_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Dropdown order: how likely this is the currency wanted, not the alphabet.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    # ISO-3166 alpha-2 codes that price in this currency. One answer to "what does a
    # shop in Germany bill in", shared by the backend and the interface.
    countries: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
