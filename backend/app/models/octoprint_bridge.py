"""Persistence owned by the native OctoPrint Bridge adapter."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class OctoPrintBridgeConnection(Base):
    """Pairing credentials and observations private to the OctoPrint adapter."""

    __tablename__ = "octoprint_bridge_connections"

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
    instance_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    plugin_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    octoprint_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    active_slot_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OctoPrintBridgeEvent(Base):
    """Durable replay protection for events submitted by one Bridge instance."""

    __tablename__ = "octoprint_bridge_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("octoprint_bridge_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    consumed_weight_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "event_id",
            name="uq_octobridge_event_connection",
        ),
    )
