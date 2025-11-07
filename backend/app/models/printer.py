"""Printer (3D printer) model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.preset_printer import PresetPrinter
    from app.models.printer_profile import PrinterProfile


class Printer(Base):
    """
    Модель FDM (FFF) 3D принтера.

    Филаменты используются только для FDM/FFF технологии печати.
    Содержит информацию о принтере для фильтрации пресетов.
    """

    __tablename__ = "printers"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Printer info
    name: Mapped[str] = mapped_column(String(200), index=True)
    manufacturer: Mapped[str] = mapped_column(String(100), index=True)
    model: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    
    # Build volume (optional)
    build_volume_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    build_volume_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    build_volume_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Размеры в мм
    
    # Nozzle diameter (FDM only)
    nozzle_diameter: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Диаметр сопла в мм (0.2, 0.4, 0.6, 0.8 и т.д.)
    
    # Temperature limits
    max_extruder_temp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_bed_temp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Image/Logo
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
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
    preset_links: Mapped[list["PresetPrinter"]] = relationship(
        "PresetPrinter", back_populates="printer", cascade="all, delete-orphan"
    )
    profiles: Mapped[list["PrinterProfile"]] = relationship(
        "PrinterProfile", back_populates="printer", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Printer(id={self.id}, name='{self.name}', manufacturer='{self.manufacturer}')>"

