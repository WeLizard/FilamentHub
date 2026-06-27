"""Filament (материал) model."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.filament_line import FilamentLine
    from app.models.filament_review import FilamentReview
    from app.models.preset import Preset
    from app.models.print_profile_filament import PrintProfileFilament


class FilamentAvailability(str, enum.Enum):
    """Доступность филамента для покупки у бренда."""

    available = "available"
    out_of_stock = "out_of_stock"
    discontinued = "discontinued"
    coming_soon = "coming_soon"


class Filament(Base):
    """
    Материал для 3D-печати.

    Примеры: ThermPlast PLA Red, ThermPlast PETG Black
    """

    __tablename__ = "filaments"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Brand relationship
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), index=True)
    line_id: Mapped[int | None] = mapped_column(
        ForeignKey("filament_lines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # line_id: линейка (группирует варианты-цвета). NULL = филамент вне линейки.

    # Basic info
    name: Mapped[str] = mapped_column(String(200), index=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    # slug: URL-friendly identifier for filament pages (e.g., "thermoplast-pla-red")
    material_type: Mapped[str] = mapped_column(String(50), index=True)
    # material_type: PLA, ABS, PETG, TPU, Nylon, ASA, PC, etc.

    # Visual
    color_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # color_hex: #FF0000 (базовый цвет, используется в OrcaSlicer)

    # Extended visual settings (JSON) - только для сайта
    visual_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # visual_settings: {
    #   "color_type": "single" | "two" | "three" | "gradient" | "transition" | "thermochromic",
    #   "colors": ["#FF0000", "#00FF00", ...], // до 5 цветов
    #   "finish": "matte" | "glossy",
    #   "filler": "none" | "wood" | "carbon" | "glitter" | "metallic" | "luminescent" | "fibers" | "stone" | "glass" | "pattern1-12",
    #   "transparency": 0-100 // прозрачность в процентах
    # }

    # Physical properties
    diameter: Mapped[float] = mapped_column(Float, default=1.75)
    # diameter: 1.75 или 2.85 мм

    density: Mapped[float | None] = mapped_column(Float, nullable=True)
    # density: г/см³ (для расчета веса)

    # Pricing (для калькулятора)
    price_per_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    # price_per_kg: рекомендованная цена за кг (вендор заполняет)
    spool_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    # spool_weight: вес нетто филамента в граммах (обычно 1000г)
    empty_spool_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    # empty_spool_weight_g: вес пустой катушки (тара) в граммах, для взвешивания
    price_display_unit: Mapped[str] = mapped_column(
        String(10), default="per_kg", server_default="per_kg", nullable=False
    )
    # price_display_unit: в каком виде бренд назначил цену и хочет её показывать —
    # "per_kg" или "per_spool". price_per_kg всегда канонический; вторая единица
    # выводится как доп-инфо.

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Statistics
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    # views_count: сколько раз посмотрели страницу филамента

    scans_count: Mapped[int] = mapped_column(Integer, default=0)
    # scans_count: сколько раз отсканировали QR-код

    # QR Code
    qr_code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    # qr_code: короткий код для QR-кода (например: "FHUB-ABC123")
    # Автоматически генерируется для верифицированных брендов

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # active управляет видимостью; availability — статус продажи у бренда
    availability: Mapped[FilamentAvailability] = mapped_column(
        Enum(FilamentAvailability, name="filament_availability", native_enum=False),
        default=FilamentAvailability.available,
        server_default=FilamentAvailability.available.value,
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="filaments")
    line: Mapped["FilamentLine | None"] = relationship("FilamentLine", back_populates="filaments")
    presets: Mapped[list["Preset"]] = relationship(
        "Preset", back_populates="filament", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["FilamentReview"]] = relationship(
        "FilamentReview", back_populates="filament", cascade="all, delete-orphan"
    )
    print_profile_links: Mapped[list["PrintProfileFilament"]] = relationship(
        "PrintProfileFilament", back_populates="filament", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Filament(id={self.id}, name='{self.name}', type='{self.material_type}')>"

