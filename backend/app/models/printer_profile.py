"""PrinterProfile model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.printer import Printer
    from app.models.user import User


class PrinterProfile(Base):
    """Настройки принтера, импортируемые в OrcaSlicer."""

    __tablename__ = "printer_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    printer_id: Mapped[int | None] = mapped_column(
        ForeignKey("printers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_official: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    orcaslicer_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    start_gcode: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_gcode: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    printer: Mapped["Printer | None"] = relationship("Printer", back_populates="profiles")
    owner: Mapped["User | None"] = relationship("User", back_populates="printer_profiles")

    def __repr__(self) -> str:
        status = "official" if self.is_official else "user"
        return f"<PrinterProfile(id={self.id}, name='{self.name}', status={status})>"


