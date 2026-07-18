"""Provider-neutral material systems, slots, and connector capabilities."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.material_slot_assignment import MaterialSlotAssignment
    from app.models.preset_gate_state import PresetGateState
    from app.models.user_printer_device import UserPrinterDevice


class MaterialSystem(Base):
    """Optional material-feed topology attached to a physical printer."""

    __tablename__ = "material_systems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    physical_printer_id: Mapped[int] = mapped_column(
        ForeignKey("user_printer_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="direct_feed")
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    capabilities: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    physical_printer: Mapped["UserPrinterDevice"] = relationship(
        "UserPrinterDevice", back_populates="material_systems"
    )
    slots: Mapped[list["MaterialSlot"]] = relationship(
        "MaterialSlot", back_populates="material_system", cascade="all, delete-orphan"
    )
    connectors: Mapped[list["PhysicalPrinterConnector"]] = relationship(
        "PhysicalPrinterConnector", back_populates="material_system"
    )


class MaterialSlot(Base):
    """Stable internal slot with a provider-local index or label."""

    __tablename__ = "material_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_system_id: Mapped[int] = mapped_column(
        ForeignKey("material_systems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_index: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="slot")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "material_system_id", "provider_index", name="uq_material_system_slot_index"
        ),
    )

    material_system: Mapped["MaterialSystem"] = relationship(
        "MaterialSystem", back_populates="slots"
    )
    legacy_gate_state: Mapped["PresetGateState | None"] = relationship(
        "PresetGateState", back_populates="material_slot", uselist=False
    )
    assignment: Mapped["MaterialSlotAssignment | None"] = relationship(
        "MaterialSlotAssignment",
        back_populates="material_slot",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )


class PhysicalPrinterConnector(Base):
    """Exchange adapter and capabilities, separate from printer identity."""

    __tablename__ = "physical_printer_connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    physical_printer_id: Mapped[int] = mapped_column(
        ForeignKey("user_printer_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_system_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_systems.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    transport: Mapped[str] = mapped_column(String(50), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "physical_printer_id",
            "provider",
            "transport",
            name="uq_physical_printer_connector",
        ),
    )

    physical_printer: Mapped["UserPrinterDevice"] = relationship(
        "UserPrinterDevice", back_populates="connectors"
    )
    material_system: Mapped["MaterialSystem | None"] = relationship(
        "MaterialSystem", back_populates="connectors"
    )
