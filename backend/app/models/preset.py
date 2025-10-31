"""Preset (настройки печати) model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament


class Preset(Base):
    """
    Пресет настроек печати для материала.

    Может быть официальным (от производителя) или пользовательским.
    """

    __tablename__ = "presets"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Filament relationship
    filament_id: Mapped[int] = mapped_column(ForeignKey("filaments.id"), index=True)

    # Preset info
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Type
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # is_official=True - от производителя, False - от пользователя

    # Print settings
    extruder_temp: Mapped[float] = mapped_column(Float)
    bed_temp: Mapped[float] = mapped_column(Float)
    print_speed: Mapped[float] = mapped_column(Float)
    travel_speed: Mapped[float] = mapped_column(Float, nullable=True)

    # Advanced settings (optional)
    layer_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_layer_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    flow_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Cooling
    fan_speed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # fan_speed: 0-100%

    # Retraction
    retraction_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    retraction_speed: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Rating & usage stats
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    # rating: средняя оценка пользователей (1-5)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    # usage_count: сколько раз использовали

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
    filament: Mapped["Filament"] = relationship("Filament", back_populates="presets")

    def __repr__(self) -> str:
        """String representation."""
        official = " (official)" if self.is_official else ""
        return f"<Preset(id={self.id}, name='{self.name}'{official})>"

