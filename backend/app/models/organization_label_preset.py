"""Shared label-layout presets for one organization brand workspace."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.organization import Organization
    from app.models.user import User


class OrganizationLabelPreset(Base):
    """A professional layout shared inside one exact company brand workspace."""

    __tablename__ = "organization_label_presets"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "brand_id",
            "name",
            name="uq_org_brand_label_preset_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    organization: Mapped["Organization"] = relationship()
    brand: Mapped["Brand"] = relationship()
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    updated_by: Mapped["User | None"] = relationship(foreign_keys=[updated_by_id])
