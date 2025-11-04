"""MaterialMapping (маппинг материалов на системные пресеты OrcaSlicer) model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand


class MaterialMappingPriority(str, Enum):
    """Приоритет маппинга материала."""

    AUTOMATIC = "automatic"  # Автоматический (на основе анализа названия)
    MANUAL = "manual"  # Ручной (от админа или производителя)
    BRAND = "brand"  # От производителя (высший приоритет)


class MaterialMapping(Base):
    """
    Кастомный маппинг типа материала на системный пресет OrcaSlicer.

    Позволяет:
    - Производителям указывать базовый материал для новых типов
    - Админам управлять маппингами через админ-панель
    - Автоматически мапить материалы на основе анализа названия
    """

    __tablename__ = "material_mappings"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Material type (e.g., "PLA-MAX", "SUPER PLA", "ABS-X")
    material_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    # material_type: название типа материала (может быть уникальным)

    # OrcaSlicer system preset name (e.g., "Generic PLA @System")
    orcaslicer_preset: Mapped[str] = mapped_column(String(200), nullable=False)
    # orcaslicer_preset: имя системного пресета OrcaSlicer для наследования

    # Priority: automatic vs manual vs brand
    priority: Mapped[MaterialMappingPriority] = mapped_column(
        SQLEnum(MaterialMappingPriority, values_callable=lambda x: [e.value for e in x]),
        default=MaterialMappingPriority.MANUAL,
        nullable=False,
        index=True,
    )
    # priority: приоритет маппинга (brand > manual > automatic)

    # Brand relationship (if mapping created by brand)
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id"), nullable=True, index=True
    )
    # brand_id: если маппинг создан производителем

    # Description (optional)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # description: описание маппинга (например, "PLA-MAX наследуется от Generic PLA")

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # active: активен ли маппинг

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="material_mappings")

    def __repr__(self) -> str:
        """String representation."""
        return f"<MaterialMapping(id={self.id}, material_type='{self.material_type}', orcaslicer_preset='{self.orcaslicer_preset}')>"

