"""PrinterConnectionBinding — a normalized connection endpoint bound to a
physical printer (UserPrinterDevice). Stage B derives these from staged
OrcaPrinterConnectionObservation rows.

The endpoint (provider + scheme + host + port + path), not a bare IP, is the
discovery/matching key. It is NOT the printer's permanent identity: it lives
here so the same machine survives config changes and merge/split later.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_printer_device import UserPrinterDevice


class PrinterConnectionBinding(Base):
    """One normalized connection endpoint → one physical printer, per user."""

    __tablename__ = "printer_connection_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    physical_printer_id: Mapped[int] = mapped_column(
        ForeignKey("user_printer_devices.id", ondelete="CASCADE")
    )

    source: Mapped[str] = mapped_column(
        String(50), default="orcaslicer_plugin", server_default="orcaslicer_plugin"
    )
    # Canonical "provider|scheme|host|port|path" — the discovery/matching key.
    normalized_endpoint: Mapped[str] = mapped_column(String(600))
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scheme: Mapped[str | None] = mapped_column(String(20), nullable=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Raw observed host (credential-stripped) for display.
    print_host: Mapped[str | None] = mapped_column(String(500), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    physical_printer: Mapped["UserPrinterDevice"] = relationship("UserPrinterDevice")

    __table_args__ = (
        Index("ix_pcb_user_endpoint", "user_id", "normalized_endpoint", unique=True),
        Index("ix_pcb_physical_printer", "physical_printer_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<PrinterConnectionBinding(id={self.id}, user={self.user_id}, "
            f"printer={self.physical_printer_id}, endpoint={self.normalized_endpoint!r})>"
        )
