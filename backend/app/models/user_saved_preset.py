"""UserSavedPreset model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.preset import Preset
    from app.models.printer_profile import PrinterProfile
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
    sync: Mapped[bool] = mapped_column(Boolean, default=True)
    # sync: Включена ли синхронизация с OrcaSlicer для этого пресета у этого пользователя
    # Каждый пользователь имеет свою настройку синхронизации для каждого пресета в "Профили филамента"

    # Library scope (RFC material-systems §3.3, filament slice):
    #   unscoped — universal: compatibility comes from the preset's catalog
    #              PresetPrinter links, today's behavior;
    #   targeted — pinned to one of the user's own Orca machine profiles;
    #              export narrows compatible_printers to that profile.
    # "compatible" is computed at apply time, never stored. Target is the
    # existing PrinterProfile.id — no separate target table (RFC §3.1).
    scope: Mapped[str] = mapped_column(String(20), default="unscoped", server_default="unscoped")
    target_printer_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("printer_profiles.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        # One saved row per (user, preset). The original unique index from
        # 572fc7e611e3 was dropped by cd4a3c3232ff; restored by the
        # usp_user_preset_unique_restore migration under the historical name.
        Index(
            "ix_user_saved_presets_user_preset_unique",
            "user_id",
            "preset_id",
            unique=True,
        ),
        # Historical name: the column was renamed sync_enabled -> sync in
        # 0de996edecbd, the index was not.
        Index("ix_user_saved_presets_sync_enabled", "sync"),
        Index("ix_user_saved_presets_target_profile", "target_printer_profile_id"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="saved_presets")
    preset: Mapped["Preset"] = relationship("Preset", back_populates="saved_by_users")
    target_profile: Mapped["PrinterProfile | None"] = relationship("PrinterProfile")

    def __repr__(self) -> str:
        """String representation."""
        return f"<UserSavedPreset(id={self.id}, user_id={self.user_id}, preset_id={self.preset_id})>"
