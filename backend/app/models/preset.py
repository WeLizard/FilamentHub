"""Preset (настройки печати) model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament
    from app.models.preset_printer import PresetPrinter
    from app.models.user import User
    from app.models.user_saved_preset import UserSavedPreset


class PresetModerationStatus(str, Enum):
    """Статус модерации пресета."""

    PENDING = "pending"  # Ожидает модерации
    APPROVED = "approved"  # Одобрен
    REJECTED = "rejected"  # Отклонен
    AUTO_GENERATED = "auto_generated"  # Сгенерирован системой (weighted): виден, но не прошёл модерацию


# Statuses under which a preset is publicly visible (catalog, matching, recommend,
# spool-compat, version view). Centralized so weighted-preset safety (Ф8) keeps generated
# presets visible everywhere without auto-stamping them as human-APPROVED.
# NOT for admin/moderation-count or assignment sites — those stay specific to APPROVED.
PUBLIC_PRESET_STATUSES = (
    PresetModerationStatus.APPROVED,
    PresetModerationStatus.AUTO_GENERATED,
)


class Preset(Base):
    """
    Пресет настроек печати для материала.

    Может быть официальным (от производителя) или пользовательским.
    """

    __tablename__ = "presets"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Filament relationship
    # КРИТИЧНО: nullable=True для черновиков из OrcaSlicer (еще не привязаны к филаменту)
    filament_id: Mapped[int | None] = mapped_column(ForeignKey("filaments.id"), index=True, nullable=True)

    # User relationship (кто создал пресет)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    # user_id=None - для старых пресетов или системных

    # Preset info
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Type
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # is_official=True - от производителя, False - от пользователя
    is_weighted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # is_weighted=True - динамический взвешенный пресет, автоматически пересчитывается системой

    # Filament settings (material scope). print/travel speed и layer heights —
    # process-scope (Orca print profile), на filament-пресете их нет.
    extruder_temp: Mapped[float] = mapped_column(Float)
    bed_temp: Mapped[float] = mapped_column(Float)
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
    # rating: средняя оценка пользователей (1-5), вычисляется из отзывов
    success_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # success_rate: процент успешных печатей (0-100), вычисляется из отзывов
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

    # External ID and source (для синхронизации с OrcaSlicer)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    # external_id: Уникальный ID профиля в OrcaSlicer (для маппинга)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # source: Источник пресета ("orcaslicer", "user", "system", etc.)
    # УДАЛЕНО: sync_enabled - теперь синхронизация управляется через user_saved_presets.sync

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    # Relationships
    filament: Mapped["Filament | None"] = relationship("Filament", back_populates="presets")
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

