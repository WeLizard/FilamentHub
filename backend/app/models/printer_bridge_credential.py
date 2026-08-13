"""Revocable credentials for provider-neutral local printer bridges."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class PrinterBridgeCredential(Base):
    """One server credential bound to one physical-printer connector.

    Provider credentials (for example a Bambu LAN access code) never belong in
    this table. The local bridge receives only a narrow FilamentHub token, while
    the database keeps its SHA-256 digest.
    """

    __tablename__ = "printer_bridge_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_id: Mapped[int] = mapped_column(
        ForeignKey("physical_printer_connectors.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    pairing_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    pairing_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    paired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plugin_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
