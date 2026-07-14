"""Brand (производитель пластика) model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament
    from app.models.material_mapping import MaterialMapping
    from app.models.organization import Organization


class Brand(Base):
    """
    Производитель пластика.

    Примеры: ThermPlast, SampleManufacturer, BrandName
    """

    __tablename__ = "brands"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Official owner workspace. Public brands stay separate even when one
    # company owns several of them.
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Contact
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_bg: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # logo_bg: фон под лого (HEX/CSS-цвет), чтобы прозрачные лого не терялись на тёмной теме

    # Public profile
    social_media_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    shop_links: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Pricing
    currency: Mapped[str] = mapped_column(
        String(8), default="RUB", server_default="RUB", nullable=False
    )
    price_hidden: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # Verification
    verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # verified=True означает что это официальный аккаунт производителя
    name_correction_available: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    name_corrected_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    # Relationships
    filaments: Mapped[list["Filament"]] = relationship(
        "Filament", back_populates="brand", cascade="all, delete-orphan"
    )
    material_mappings: Mapped[list["MaterialMapping"]] = relationship(
        "MaterialMapping", back_populates="brand"
    )
    organization: Mapped["Organization | None"] = relationship(back_populates="brands")

    def __repr__(self) -> str:
        """String representation."""
        verified_badge = "✓" if self.verified else ""
        return f"<Brand(id={self.id}, name='{self.name}'{verified_badge})>"
