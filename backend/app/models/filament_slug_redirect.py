"""Persistent aliases for renamed public filament slugs."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.filament import Filament


class FilamentSlugRedirect(Base):
    """An old per-brand slug that must keep resolving to one filament."""

    __tablename__ = "filament_slug_redirects"
    __table_args__ = (
        UniqueConstraint(
            "brand_id",
            "old_slug",
            name="uq_filament_slug_redirect_brand_old",
        ),
        Index("ix_filament_slug_redirect_brand", "brand_id"),
        Index("ix_filament_slug_redirect_filament", "filament_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    filament_id: Mapped[int] = mapped_column(
        ForeignKey("filaments.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    old_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(
        String(20), nullable=False, default="rename", server_default="rename"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )

    filament: Mapped["Filament"] = relationship()
    brand: Mapped["Brand"] = relationship()
