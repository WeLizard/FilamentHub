"""FilamentReview model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament
    from app.models.preset import Preset
    from app.models.user import User


class FilamentReview(Base):
    """Отзыв о филаменте от пользователя."""

    __tablename__ = "filament_reviews"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "filament_id", "preset_id",
            name="uq_user_filament_preset_review",
        ),
    )

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Foreign keys
    filament_id: Mapped[int] = mapped_column(ForeignKey("filaments.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    preset_id: Mapped[int | None] = mapped_column(
        ForeignKey("presets.id"), nullable=True, index=True
    )
    # preset_id: к какому пресету относится отзыв (None если отзыв о филаменте в целом)

    # Review data
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # success: True если печать успешна, False если провал
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    # rating: 1.0 - 5.0
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    printer_id: Mapped[int | None] = mapped_column(
        ForeignKey("printers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Which machine from the catalogue, when the person picked one. Typing the
    # name is still allowed for a self-build, but only a chosen machine lets a
    # later reader ask how this material behaves on the printer they own —
    # "Voron 2.4", "voron 2.4" and "Ворон 2.4" are one machine and three strings.
    printer_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    # printer_model: the name as shown, canonical when a machine was picked

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    # Relationships
    filament: Mapped["Filament"] = relationship("Filament", back_populates="reviews")
    user: Mapped["User"] = relationship("User", back_populates="filament_reviews")
    preset: Mapped["Preset | None"] = relationship("Preset", foreign_keys=[preset_id])

    def __repr__(self) -> str:
        """String representation."""
        return f"<FilamentReview(id={self.id}, filament_id={self.filament_id}, rating={self.rating})>"
