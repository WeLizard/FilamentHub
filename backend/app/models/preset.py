"""Preset (настройки печати) model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament
    from app.models.user import User
    from app.models.user_saved_preset import UserSavedPreset
    from app.models.preset_printer import PresetPrinter


class PresetModerationStatus(str, Enum):
    """Статус модерации пресета."""

    PENDING = "pending"  # Ожидает модерации
    APPROVED = "approved"  # Одобрен
    REJECTED = "rejected"  # Отклонен


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

    # User relationship (кто создал пресет)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    # user_id=None - для старых пресетов или системных

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

    # Extended OrcaSlicer parameters (JSON)
    orcaslicer_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # orcaslicer_settings: JSON объект со всеми параметрами OrcaSlicer
    # Используется для хранения расширенных параметров, которых нет в базовых полях
    # Например: nozzle_temperature_range_low, filament_max_volumetric_speed, pressure_advance и т.д.

    # Rating & usage stats
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    # rating: средняя оценка пользователей (1-5)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    # usage_count: сколько раз использовали

    # Moderation (для пользовательских пресетов)
    moderation_status: Mapped[PresetModerationStatus] = mapped_column(
        SQLEnum(PresetModerationStatus, values_callable=lambda x: [e.value for e in x]),
        default=PresetModerationStatus.PENDING,
        nullable=False,
        index=True,
    )
    # Официальные пресеты автоматически APPROVED
    # Пользовательские требуют модерации
    moderation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    moderated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # admin user_id
    moderated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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
    user: Mapped["User"] = relationship("User", back_populates="presets")
    saved_by_users: Mapped[list["UserSavedPreset"]] = relationship(
        "UserSavedPreset", back_populates="preset", cascade="all, delete-orphan"
    )
    printer_links: Mapped[list["PresetPrinter"]] = relationship(
        "PresetPrinter", back_populates="preset", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation."""
        official = " (official)" if self.is_official else ""
        return f"<Preset(id={self.id}, name='{self.name}'{official})>"

