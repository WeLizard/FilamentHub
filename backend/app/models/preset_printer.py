"""PresetPrinter (связь пресетов с принтерами) model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.preset import Preset
    from app.models.printer import Printer


class PresetPrinter(Base):
    """
    Junction table для связи пресетов с принтерами (many-to-many).

    Позволяет:
    - Одному пресету быть связанным с несколькими принтерами
    - Отмечать, на каком принтере пресет был протестирован
    - Фильтровать пресеты по принтеру пользователя
    """

    __tablename__ = "preset_printers"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Preset relationship
    preset_id: Mapped[int] = mapped_column(ForeignKey("presets.id"), nullable=False, index=True)

    # Printer relationship
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id"), nullable=False, index=True)

    # Is this the primary printer for this preset?
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # is_primary: основной принтер для этого пресета (отображается в UI)

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
    preset: Mapped["Preset"] = relationship("Preset", back_populates="printer_links")
    printer: Mapped["Printer"] = relationship("Printer", back_populates="preset_links")

    def __repr__(self) -> str:
        """String representation."""
        primary = " (primary)" if self.is_primary else ""
        return f"<PresetPrinter(preset_id={self.preset_id}, printer_id={self.printer_id}{primary})>"

