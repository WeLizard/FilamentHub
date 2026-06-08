"""FilamentReview model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Text, UniqueConstraint
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
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
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
    printer_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    # printer_model: например "Bambu Lab A1 mini"

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
    filament: Mapped["Filament"] = relationship("Filament", back_populates="reviews")
    user: Mapped["User"] = relationship("User", back_populates="filament_reviews")
    preset: Mapped["Preset | None"] = relationship("Preset", foreign_keys=[preset_id])

    def __repr__(self) -> str:
        """String representation."""
        return f"<FilamentReview(id={self.id}, filament_id={self.filament_id}, rating={self.rating})>"
