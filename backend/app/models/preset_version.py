"""PresetVersion model — timeline-based version history for filament presets.

Each meaningful change to a Preset's settings is captured as an immutable
snapshot. Users can browse the timeline, compare versions, label important
ones, and restore a previous version. Modeled after Orca Cloud's profile
history, but positioned as an unobtrusive addition rather than a headline
feature.

Invariant: snapshot fields + content_hash are immutable once written. Only
`label`, `label_description`, `updated_at`, and `squash_count` may change
after creation (the last two during in-place squash of orca_sync edits).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

# BigInteger that becomes INTEGER on SQLite so the PK auto-increments in
# tests (SQLite only gives rowid autoincrement to INTEGER PRIMARY KEY).
_BigIntPK = BigInteger().with_variant(Integer, "sqlite")

if TYPE_CHECKING:
    from app.models.preset import Preset
    from app.models.user import User


class PresetVersionSource:
    """Where a preset version came from.

    String constants (not a Python Enum) to mirror BundleStatus/BundleSource
    convention and avoid PostgreSQL ``ALTER TYPE`` migrations when adding
    new sources.
    """

    WEB_EDIT = "web_edit"      # explicit save in the web UI
    ORCA_SYNC = "orca_sync"    # upsert from OrcaSlicer sync (squashable)
    RESTORE = "restore"        # created by restoring an earlier version
    ADMIN = "admin"            # admin manual edit
    ENRICHMENT = "enrichment"  # weighted-preset / draft enrichment
    MIGRATION = "migration"    # initial v1 backfill for pre-existing presets

    ALL = (WEB_EDIT, ORCA_SYNC, RESTORE, ADMIN, ENRICHMENT, MIGRATION)


class PresetVersion(Base):
    """Immutable snapshot of a Preset at a point in time."""

    __tablename__ = "preset_versions"

    id: Mapped[int] = mapped_column(_BigIntPK, primary_key=True, index=True)

    preset_id: Mapped[int] = mapped_column(
        ForeignKey("presets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Dense per-preset counter (1, 2, 3, ...). Generated under a row lock on
    # the parent Preset — NOT a global sequence. See preset_version_service.
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Full snapshot of the preset state at save time.
    snapshot_orcaslicer_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_structured: Mapped[dict] = mapped_column(JSON, nullable=False)

    # sha256 of canonical-JSON(snapshot_orcaslicer_settings). Used for dedup
    # (skip identical saves) and squash detection.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # User-supplied label (Orca Cloud's "Add Label"). Empty when unlabeled;
    # the "Labeled Only" filter excludes empty labels.
    label: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default="")
    label_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    change_source: Mapped[str] = mapped_column(String(40), nullable=False)

    # If created via restore, reference the source version so the UI can show
    # "Restored from v3".
    restored_from_version_id: Mapped[int | None] = mapped_column(
        _BigIntPK, ForeignKey("preset_versions.id", ondelete="SET NULL"), nullable=True
    )

    # In-place squash bookkeeping: number of orca_sync saves folded into this
    # row within the squash window. 1 = never squashed.
    squash_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    preset: Mapped["Preset"] = relationship("Preset", foreign_keys=[preset_id])
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        UniqueConstraint("preset_id", "version_number", name="uq_preset_version"),
        Index("ix_preset_versions_preset_created", "preset_id", "created_at"),
    )

    def __repr__(self) -> str:
        """String representation."""
        lbl = f" '{self.label}'" if self.label else ""
        return f"<PresetVersion(preset_id={self.preset_id}, v{self.version_number}{lbl})>"
