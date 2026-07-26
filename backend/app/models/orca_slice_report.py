"""What a slice in OrcaSlicer produced, as the G-code itself states it."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.printer_profile import PrinterProfile
    from app.models.user import User
    from app.models.user_printer_device import UserPrinterDevice


class OrcaSliceReport(Base):
    """A slice the plugin saw leaving OrcaSlicer.

    Orca writes the totals into the G-code, so the plugin reads the file's tail
    and sends the figures; the file itself stays on the person's machine until
    they ask for a full breakdown.
    """

    __tablename__ = "orca_slice_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    physical_printer_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_printer_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    printer_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("printer_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Straight out of the file: the preset the slice was made with and the model
    # it names. Kept even when nothing on the account matches them yet.
    printer_settings_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    printer_model: Mapped[str | None] = mapped_column(String(200), nullable=True)

    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    # Where it was headed: "File", "OctoPrint", "Klipper"…
    target_host: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slicer_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    total_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Grams per filament position, as the file lists them.
    filament_weights_g: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    estimated_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filament_changes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    layer_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sliced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Exporting to a file and uploading to a printer fire the same seam once
    # each, so the same slice arrives twice and has to be recognised.
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("uq_orca_slice_report_dedupe", "user_id", "dedupe_key", unique=True),
        Index("ix_orca_slice_reports_user_received", "user_id", "received_at"),
    )

    user: Mapped["User"] = relationship("User")
    physical_printer: Mapped["UserPrinterDevice | None"] = relationship("UserPrinterDevice")
    printer_profile: Mapped["PrinterProfile | None"] = relationship("PrinterProfile")

    def __repr__(self) -> str:
        return (
            f"<OrcaSliceReport(id={self.id}, user_id={self.user_id}, "
            f"file={self.file_name!r}, weight={self.total_weight_g})>"
        )
