"""Provider-neutral production print history and its immutable timeline."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.calculator_history_entry import CalculatorHistoryEntry
    from app.models.orca_slice_report import OrcaSliceReport
    from app.models.preset_usage_event import PresetUsageEvent
    from app.models.user import User
    from app.models.user_printer_device import UserPrinterDevice
    from app.models.user_spool import UserSpool


class PrintJobStatus(str, enum.Enum):
    """Lifecycle of one concrete attempt to print something."""

    prepared = "prepared"
    sent = "sent"
    printing = "printing"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class PrintJob(Base):
    """One execution attempt, independent of the printer provider."""

    __tablename__ = "print_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "source_ref", name="uq_print_job_source_ref"),
        Index("ix_print_jobs_user_status", "user_id", "status", "created_at"),
        Index("ix_print_jobs_printer", "physical_printer_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    logical_id: Mapped[str] = mapped_column(
        String(36), default=lambda: str(uuid4()), nullable=False, unique=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    physical_printer_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_printer_devices.id", ondelete="SET NULL"), nullable=True
    )
    calculator_history_id: Mapped[int | None] = mapped_column(
        ForeignKey("calculator_history_entries.id", ondelete="SET NULL"), nullable=True
    )
    calculator_job_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    orca_slice_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("orca_slice_reports.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[PrintJobStatus] = mapped_column(
        Enum(PrintJobStatus, name="print_job_status", native_enum=False),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    source_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    printer_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    calculation_title_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_name_snapshot: Mapped[str | None] = mapped_column(String(300), nullable=True)
    estimated_duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User")
    physical_printer: Mapped["UserPrinterDevice | None"] = relationship("UserPrinterDevice")
    calculator_history: Mapped["CalculatorHistoryEntry | None"] = relationship(
        "CalculatorHistoryEntry"
    )
    orca_slice_report: Mapped["OrcaSliceReport | None"] = relationship("OrcaSliceReport")
    events: Mapped[list["PrintJobEvent"]] = relationship(
        "PrintJobEvent",
        back_populates="print_job",
        cascade="all, delete-orphan",
        order_by="PrintJobEvent.occurred_at, PrintJobEvent.id",
    )
    materials: Mapped[list["PrintJobMaterial"]] = relationship(
        "PrintJobMaterial",
        back_populates="print_job",
        cascade="all, delete-orphan",
        order_by="PrintJobMaterial.id",
    )
    usage_events: Mapped[list["PresetUsageEvent"]] = relationship(
        "PresetUsageEvent", back_populates="print_job"
    )


class PrintJobEvent(Base):
    """Append-only, replay-protected lifecycle fact for a print job."""

    __tablename__ = "print_job_events"
    __table_args__ = (
        UniqueConstraint("print_job_id", "event_key", name="uq_print_job_event_key"),
        Index("ix_print_job_events_time", "print_job_id", "occurred_at"),
        Index("ix_print_job_events_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    print_job_id: Mapped[int] = mapped_column(
        ForeignKey("print_jobs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[PrintJobStatus] = mapped_column(
        Enum(PrintJobStatus, name="print_job_event_status", native_enum=False),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    print_job: Mapped["PrintJob"] = relationship("PrintJob", back_populates="events")


class PrintJobMaterial(Base):
    """A physical spool selected for the attempt, with a deletion-safe label snapshot."""

    __tablename__ = "print_job_materials"
    __table_args__ = (
        Index("ix_print_job_materials_job", "print_job_id"),
        Index("ix_print_job_materials_spool", "spool_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    print_job_id: Mapped[int] = mapped_column(
        ForeignKey("print_jobs.id", ondelete="CASCADE"), nullable=False
    )
    spool_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_spools.id", ondelete="SET NULL"), nullable=True
    )
    material_line_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tool_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planned_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    spool_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)

    print_job: Mapped["PrintJob"] = relationship("PrintJob", back_populates="materials")
    spool: Mapped["UserSpool | None"] = relationship("UserSpool")
