"""Durable issued routes and delivery receipts for printer bridges."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class PrinterBridgeReceipt(Base):
    """Retain issued route evidence or the result of one connector delivery.

    A usage_route row authorizes an exact historical route, not an amount.
    Usage event and batch rows separately prevent repeated ledger application.
    """

    __tablename__ = "printer_bridge_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_id: Mapped[int] = mapped_column(
        ForeignKey("physical_printer_connectors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_instance_id: Mapped[str] = mapped_column(String(100), nullable=False)
    receipt_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    receipt_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    consumed_weight_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "connector_id",
            "source_instance_id",
            "receipt_kind",
            "receipt_id",
            name="uq_printer_bridge_receipt_identity",
        ),
        Index(
            "ix_printer_bridge_receipt_sequence",
            "connector_id",
            "source_instance_id",
            "receipt_kind",
            "sequence",
        ),
    )
