"""Filament (материал) model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand


class Filament(Base):
    """
    Материал для 3D-печати.

    Примеры: Bestfilament PLA Red, Sunlu PETG Black
    """

    __tablename__ = "filaments"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Brand relationship
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), index=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(200), index=True)
    material_type: Mapped[str] = mapped_column(String(50), index=True)
    # material_type: PLA, ABS, PETG, TPU, Nylon, ASA, PC, etc.

    # Visual
    color_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # color_hex: #FF0000

    # Physical properties
    diameter: Mapped[float] = mapped_column(Float, default=1.75)
    # diameter: 1.75 или 2.85 мм

    density: Mapped[float | None] = mapped_column(Float, nullable=True)
    # density: г/см³ (для расчета веса)

    # Pricing (для калькулятора)
    price_per_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    spool_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    # spool_weight: вес катушки в граммах (обычно 1000г)

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    brand: Mapped["Brand"] = relationship("Brand", back_populates="filaments")
    presets: Mapped[list["Preset"]] = relationship(
        "Preset", back_populates="filament", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Filament(id={self.id}, name='{self.name}', type='{self.material_type}')>"

