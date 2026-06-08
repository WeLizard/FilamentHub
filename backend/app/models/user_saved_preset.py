"""UserSavedPreset model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.preset import Preset
    from app.models.user import User


class UserSavedPreset(Base):
    """Сохраненные пользователем пресеты (избранное)."""

    __tablename__ = "user_saved_presets"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Foreign keys
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    preset_id: Mapped[int] = mapped_column(ForeignKey("presets.id"), index=True)

    # Timestamp
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Sync settings
    sync: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # sync: Включена ли синхронизация с OrcaSlicer для этого пресета у этого пользователя
    # Каждый пользователь имеет свою настройку синхронизации для каждого пресета в "Профили филамента"

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="saved_presets")
    preset: Mapped["Preset"] = relationship("Preset", back_populates="saved_by_users")

    def __repr__(self) -> str:
        """String representation."""
        return f"<UserSavedPreset(id={self.id}, user_id={self.user_id}, preset_id={self.preset_id})>"
