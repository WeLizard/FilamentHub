"""FilamentLine (линейка филамента) model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.filament import Filament


class FilamentLine(Base):
    """
    Линейка филамента бренда — группирует варианты-цвета одного продукта.

    Каждый цвет остаётся отдельным Filament со своими параметрами; линейка только
    объединяет их для отображения (не сливает).
    """

    __tablename__ = "filament_lines"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    brand: Mapped["Brand"] = relationship("Brand")
    filaments: Mapped[list["Filament"]] = relationship(
        "Filament", back_populates="line"
    )
