"""Low-stock alert rules: for every spool, for one spool, or for one material on the shelf."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression, func

from app.db.base import Base


class StockAlertRule(Base):
    """scope 'all' covers every spool without its own rule; 'spool' one spool; 'material' the
    shelf stock of a catalog material (key "f:<filament id>" or "c:<imported ref id>")."""

    __tablename__ = "stock_alert_rules"
    __table_args__ = (
        CheckConstraint("scope IN ('all', 'spool', 'material')", name="ck_stock_alert_scope"),
        CheckConstraint("threshold_g > 0", name="ck_stock_alert_threshold"),
        Index(
            "uq_stock_alert_all",
            "user_id",
            unique=True,
            postgresql_where=text("scope = 'all'"),
            sqlite_where=text("scope = 'all'"),
        ),
        Index(
            "uq_stock_alert_spool",
            "user_id",
            "spool_id",
            unique=True,
            postgresql_where=text("scope = 'spool'"),
            sqlite_where=text("scope = 'spool'"),
        ),
        Index(
            "uq_stock_alert_material",
            "user_id",
            "material_key",
            unique=True,
            postgresql_where=text("scope = 'material'"),
            sqlite_where=text("scope = 'material'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    spool_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_spools.id", ondelete="CASCADE"), nullable=True
    )
    material_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    threshold_g: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=expression.true()
    )
    # Material rules only: an alert fired and has not been re-armed by a refill.
    fired: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=expression.false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
