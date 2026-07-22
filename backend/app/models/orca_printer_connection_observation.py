"""OrcaPrinterConnectionObservation — staging/evidence of printer connection data
observed by the OrcaSlicer plugin. Not a domain identity model: it records only
that at a moment the plugin saw a given printer preset with a given connection
configuration. Stage B reads these to build PhysicalPrinter/ConnectionBinding.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    pass


class OrcaPrinterConnectionObservation(Base):
    """Deduplicated evidence of a plugin-observed printer connection."""

    __tablename__ = "orca_printer_connection_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    source: Mapped[str] = mapped_column(
        String(50), default="orcaslicer_plugin", server_default="orcaslicer_plugin"
    )
    # Stable identity of the plugin install, when available; nullable until we have one.
    source_instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    printer_settings_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    preset_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    inherits: Mapped[str | None] = mapped_column(String(200), nullable=True)
    printer_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Raw observed endpoint after credential stripping. Normalization happens in stage B.
    print_host: Mapped[str | None] = mapped_column(String(500), nullable=True)
    host_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    payload_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # Dedup key only (owner/source/source_instance/printer_settings_id/host_type/print_host).
    # NOT a PhysicalPrinter identity.
    observation_fingerprint: Mapped[str] = mapped_column(String(64))

    # Match by exact printer_settings_id in the owner scope; nullable when unmatched.
    matched_printer_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("printer_profiles.id", ondelete="SET NULL"), nullable=True
    )

    # Credential-free copy of what was accepted.
    sanitized_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Short explicit names: PostgreSQL caps identifiers at 63 chars and the
        # table name alone leaves no room for auto-generated ix_<table>_<column>.
        Index(
            "ix_orca_conn_obs_owner_fingerprint",
            "owner_user_id",
            "observation_fingerprint",
            unique=True,
        ),
        Index("ix_orca_conn_obs_settings_id", "printer_settings_id"),
        Index("ix_orca_conn_obs_matched_profile", "matched_printer_profile_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<OrcaPrinterConnectionObservation(id={self.id}, "
            f"owner={self.owner_user_id}, settings_id={self.printer_settings_id!r})>"
        )
