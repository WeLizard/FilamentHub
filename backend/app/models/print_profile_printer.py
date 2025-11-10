"""Связь профилей печати с принтерами."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.print_profile import PrintProfile
    from app.models.printer import Printer


class PrintProfilePrinter(Base):
    """Junction-профиль печати ↔ принтер."""

    __tablename__ = "print_profile_printers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    print_profile_id: Mapped[int] = mapped_column(
        ForeignKey("print_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    printer_id: Mapped[int | None] = mapped_column(
        ForeignKey("printers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    printer_slug: Mapped[str] = mapped_column(String(200), index=True)
    relation_type: Mapped[str] = mapped_column(String(30), default="explicit", server_default="explicit", index=True)
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    profile: Mapped["PrintProfile"] = relationship(
        "PrintProfile", back_populates="printer_links"
    )
    printer: Mapped["Printer | None"] = relationship(
        "Printer", back_populates="print_profile_links"
    )

    def __repr__(self) -> str:
        return f"<PrintProfilePrinter(profile_id={self.print_profile_id}, printer_slug='{self.printer_slug}')>"

