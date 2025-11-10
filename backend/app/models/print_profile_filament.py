"""Связь профилей печати с филаментами."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament
    from app.models.print_profile import PrintProfile


class PrintProfileFilament(Base):
    """Junction-профиль печати ↔ филамент."""

    __tablename__ = "print_profile_filaments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    print_profile_id: Mapped[int] = mapped_column(
        ForeignKey("print_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filament_id: Mapped[int | None] = mapped_column(
        ForeignKey("filaments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    filament_slug: Mapped[str] = mapped_column(String(200), index=True)
    relation_type: Mapped[str] = mapped_column(String(30), default="explicit", server_default="explicit", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    profile: Mapped["PrintProfile"] = relationship(
        "PrintProfile", back_populates="filament_links"
    )
    filament: Mapped["Filament | None"] = relationship(
        "Filament", back_populates="print_profile_links"
    )

    def __repr__(self) -> str:
        return f"<PrintProfileFilament(profile_id={self.print_profile_id}, filament_slug='{self.filament_slug}')>"

