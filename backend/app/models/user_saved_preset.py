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

    # Library scope (RFC material-systems §3.3, filament slice), derived from
    # the target set in user_saved_preset_targets:
    #   unscoped   — universal, no targets: compatibility comes from the
    #                preset's catalog PresetPrinter links, today's behavior;
    #   targeted   — exactly one of the user's own Orca machine profiles;
    #   compatible — allowed for a chosen set of the user's machine profiles.
    # The scope/target-count invariant is maintained by the single writer
    # (PATCH /saved-presets/{id}/scope); export narrows compatible_printers
    # to the target profiles.
    scope: Mapped[str] = mapped_column(String(20), default="unscoped", server_default="unscoped")

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
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="saved_presets")
    preset: Mapped["Preset"] = relationship("Preset", back_populates="saved_by_users")
    # lazy="selectin": the target set is small and needed by every response
    # serialization; avoids MissingGreenlet on async lazy loads.
    targets: Mapped[list["UserSavedPresetTarget"]] = relationship(
        "UserSavedPresetTarget",
        back_populates="saved_preset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def target_printer_profile_ids(self) -> list[int]:
        return [t.printer_profile_id for t in self.targets]

    def __repr__(self) -> str:
        """String representation."""
        return f"<UserSavedPreset(id={self.id}, user_id={self.user_id}, preset_id={self.preset_id})>"


class UserSavedPresetTarget(Base):
    """Target machine profile of a saved preset (RFC §3.3 target set)."""

    __tablename__ = "user_saved_preset_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_saved_preset_id: Mapped[int] = mapped_column(
        ForeignKey("user_saved_presets.id", ondelete="CASCADE"), nullable=False
    )
    printer_profile_id: Mapped[int] = mapped_column(
        ForeignKey("printer_profiles.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_usp_targets_saved_profile_unique",
            "user_saved_preset_id",
            "printer_profile_id",
            unique=True,
        ),
        Index("ix_usp_targets_printer_profile", "printer_profile_id"),
    )

    saved_preset: Mapped["UserSavedPreset"] = relationship(
        "UserSavedPreset", back_populates="targets"
    )
    profile: Mapped["PrinterProfile"] = relationship("PrinterProfile")

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<UserSavedPresetTarget(id={self.id}, "
            f"saved_preset={self.user_saved_preset_id}, profile={self.printer_profile_id})>"
        )
