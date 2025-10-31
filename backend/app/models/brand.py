"""Brand (производитель пластика) model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament


class Brand(Base):
    """
    Производитель пластика.

    Примеры: Bestfilament, Sunlu, eSUN, Polymaker, Prusament
    """

    __tablename__ = "brands"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Contact
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Verification
    verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # verified=True означает что это официальный аккаунт производителя

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

    def __repr__(self) -> str:
        """String representation."""
        verified_badge = "✓" if self.verified else ""
        return f"<Brand(id={self.id}, name='{self.name}'{verified_badge})>"

