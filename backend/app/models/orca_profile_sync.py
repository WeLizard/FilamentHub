"""Durable bindings between local Orca profiles and FilamentHub profiles."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class OrcaProfileSyncScope(Base):
    """The current authoritative snapshot for one Orca account and profile kind."""

    __tablename__ = "orca_profile_sync_scopes"
    __table_args__ = (
        CheckConstraint("kind IN ('machine', 'process')", name="ck_orca_sync_scope_kind"),
        Index(
            "uq_orca_sync_scope_owner_source_account_kind",
            "owner_user_id",
            "source_instance_id",
            "account_id",
            "kind",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_instance_id: Mapped[str] = mapped_column(String(100), nullable=False)
    account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    current_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="open", server_default="open", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrcaProfileBinding(Base):
    """One locally stable Orca profile identity mapped to one owned FH profile."""

    __tablename__ = "orca_profile_bindings"
    __table_args__ = (
        CheckConstraint("kind IN ('machine', 'process')", name="ck_orca_profile_binding_kind"),
        CheckConstraint(
            "(kind = 'machine' AND printer_profile_id IS NOT NULL AND print_profile_id IS NULL) "
            "OR (kind = 'process' AND print_profile_id IS NOT NULL AND printer_profile_id IS NULL)",
            name="ck_orca_profile_binding_target",
        ),
        Index(
            "uq_orca_binding_owner_source_account_kind_local",
            "owner_user_id",
            "source_instance_id",
            "account_id",
            "kind",
            "local_profile_id",
            unique=True,
        ),
        Index(
            "ix_orca_binding_scope_present",
            "owner_user_id",
            "source_instance_id",
            "account_id",
            "kind",
            "present",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_instance_id: Mapped[str] = mapped_column(String(100), nullable=False)
    account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    local_profile_id: Mapped[str] = mapped_column(String(36), nullable=False)
    printer_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("printer_profiles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    print_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("print_profiles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    present: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    last_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    last_name: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
