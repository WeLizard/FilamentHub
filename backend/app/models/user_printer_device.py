"""UserPrinterDevice model — user's physical 3D printer device."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.material_system import MaterialSystem, PhysicalPrinterConnector
    from app.models.physical_printer_profile import UserPrinterProfileLink
    from app.models.preset_gate_state import PresetGateState
    from app.models.user import User


class UserPrinterDevice(Base):
    """A user's physical 3D printer device (not the reference Printer catalog)."""

    __tablename__ = "user_printer_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    logical_id: Mapped[str] = mapped_column(
        String(36), default=lambda: str(uuid4()), nullable=False, unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    printer_id: Mapped[int | None] = mapped_column(
        ForeignKey("printers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    device_fingerprint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    supports_hh: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    printer_hostname: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "device_fingerprint", name="uq_user_device_fingerprint"),
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User", foreign_keys="UserPrinterDevice.user_id", back_populates="printer_devices"
    )
    gate_states: Mapped[list["PresetGateState"]] = relationship(
        "PresetGateState", back_populates="device", cascade="all, delete-orphan"
    )
    profile_links: Mapped[list["UserPrinterProfileLink"]] = relationship(
        "UserPrinterProfileLink",
        back_populates="physical_printer",
        cascade="all, delete-orphan",
    )
    material_systems: Mapped[list["MaterialSystem"]] = relationship(
        "MaterialSystem",
        back_populates="physical_printer",
        cascade="all, delete-orphan",
    )
    connectors: Mapped[list["PhysicalPrinterConnector"]] = relationship(
        "PhysicalPrinterConnector",
        back_populates="physical_printer",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<UserPrinterDevice(id={self.id}, user_id={self.user_id})>"
        )
