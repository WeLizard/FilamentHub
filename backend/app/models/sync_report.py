"""Durable staging for chunked OrcaSlicer device reports."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.sync_history import SyncOperation, SyncPresetType


class SyncReport(Base):
    """One versioned device report assembled from one or more chunks."""

    __tablename__ = "sync_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("sync_devices.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sync_version: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_sync_reports_device_version",
            "device_id",
            "sync_version",
            unique=True,
        ),
        Index("uq_sync_reports_user_report_id", "user_id", "report_id", unique=True),
    )


class SyncReportChunk(Base):
    """Idempotency receipt for one accepted report chunk."""

    __tablename__ = "sync_report_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_pk: Mapped[int] = mapped_column(
        ForeignKey("sync_reports.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_sync_report_chunks_report_index",
            "report_pk",
            "chunk_index",
            unique=True,
        ),
    )


class SyncReportItem(Base):
    """Validated staging row for one per-preset outcome."""

    __tablename__ = "sync_report_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_pk: Mapped[int] = mapped_column(
        ForeignKey("sync_reports.id", ondelete="CASCADE"), nullable=False
    )
    chunk_pk: Mapped[int] = mapped_column(
        ForeignKey("sync_report_chunks.id", ondelete="CASCADE"), nullable=False
    )
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    preset_type: Mapped[SyncPresetType] = mapped_column(
        SQLEnum(SyncPresetType, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    operation: Mapped[SyncOperation] = mapped_column(
        SQLEnum(SyncOperation, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    preset_id: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index("ix_sync_report_items_report_cursor", "report_pk", "id"),
        Index(
            "uq_sync_report_items_result_key",
            "report_pk",
            "preset_type",
            "operation",
            "preset_id",
            unique=True,
        ),
        Index(
            "uq_sync_report_items_chunk_position",
            "chunk_pk",
            "item_index",
            unique=True,
        ),
    )
