"""Provider-neutral material systems, slots, and connector capabilities."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
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
    from app.models.material_slot_assignment import MaterialSlotAssignment
    from app.models.preset_gate_state import PresetGateState
    from app.models.printer_bridge_observation import (
        MaterialSlotObservation,
        PhysicalPrinterStatusObservation,
    )
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
    # Set once a person confirms how many slots the system really has; until then
    # the slot list is only what the provider happened to report.
    declared_slot_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # A printer feeds from one place; two systems on it would race to say what
    # sits in a slot. Several AMS units are one system counting gates in a row.
    __table_args__ = (
        Index(
            "uq_material_system_per_printer",
            "physical_printer_id",
            unique=True,
        ),
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
    """Stable internal feed slot/route with a provider-local index or label."""

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
    assignment_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
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
    observations: Mapped[list["MaterialSlotObservation"]] = relationship(
        "MaterialSlotObservation",
        back_populates="material_slot",
        cascade="all, delete-orphan",
    )

    @property
    def observation(self) -> "MaterialSlotObservation | None":
        def freshness(item: "MaterialSlotObservation") -> tuple[datetime, datetime, int]:
            def utc(value: datetime) -> datetime:
                return (
                    value.astimezone(timezone.utc)
                    if value.tzinfo
                    else value.replace(tzinfo=timezone.utc)
                )

            return (
                utc(item.observed_at),
                utc(item.received_at),
                item.id,
            )

        return max(
            (item for item in self.observations if item.connector.active),
            key=freshness,
            default=None,
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
    source_instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    node_instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    capabilities: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_observation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_snapshot_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_snapshot_source_instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
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
    status_observation: Mapped["PhysicalPrinterStatusObservation | None"] = relationship(
        "PhysicalPrinterStatusObservation",
        back_populates="connector",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )
    slot_observations: Mapped[list["MaterialSlotObservation"]] = relationship(
        "MaterialSlotObservation",
        back_populates="connector",
        cascade="all, delete-orphan",
    )
