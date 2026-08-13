"""Latest normalized facts observed through a local printer bridge."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.material_system import MaterialSlot, PhysicalPrinterConnector


class PhysicalPrinterStatusObservation(Base):
    """Latest printer status from one connector, not printer identity."""

    __tablename__ = "physical_printer_status_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_id: Mapped[int] = mapped_column(
        ForeignKey("physical_printer_connectors.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remaining_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_layer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_layers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    nozzle_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    nozzle_target_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    bed_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    bed_target_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    chamber_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    wifi_signal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)

    connector: Mapped["PhysicalPrinterConnector"] = relationship(
        "PhysicalPrinterConnector", back_populates="status_observation"
    )


class MaterialSlotObservation(Base):
    """Latest device-reported contents of one stable material slot."""

    __tablename__ = "material_slot_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_id: Mapped[int] = mapped_column(
        ForeignKey("physical_printer_connectors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_slot_id: Mapped[int] = mapped_column(
        ForeignKey("material_slots.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    present: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    active_feed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    material: Mapped[str | None] = mapped_column(String(80), nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(6), nullable=True)
    remaining_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remaining_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "connector_id",
            "material_slot_id",
            name="uq_material_slot_observation_connector_slot",
        ),
    )

    connector: Mapped["PhysicalPrinterConnector"] = relationship(
        "PhysicalPrinterConnector", back_populates="slot_observations"
    )
    material_slot: Mapped["MaterialSlot"] = relationship(
        "MaterialSlot", back_populates="observation"
    )
