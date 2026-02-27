"""PresetGateState model — slot/gate state for preset-to-device mapping."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.preset import Preset
    from app.models.user import User
    from app.models.user_spool import UserSpool
    from app.models.user_printer_device import UserPrinterDevice


class PresetGateStateSource(str, enum.Enum):
    """Source of the gate state update."""

    hh_snapshot = "hh_snapshot"
    manual_orca = "manual_orca"
    web_manual = "web_manual"


class PresetGateState(Base):
    """Current state of a single gate/slot on a user's printer device."""

    __tablename__ = "preset_gate_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("user_printer_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gate_index: Mapped[int] = mapped_column(Integer, nullable=False)

    preset_id: Mapped[int | None] = mapped_column(
        ForeignKey("presets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    spool_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_spools.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # HH actual data (from Happy Hare snapshot)
    hh_material: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hh_color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    hh_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

    source: Mapped[PresetGateStateSource] = mapped_column(
        Enum(PresetGateStateSource, name="preset_gate_state_source", native_enum=False),
        nullable=False,
    )
    source_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("device_id", "gate_index", name="uq_device_gate_index"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    device: Mapped["UserPrinterDevice"] = relationship(
        "UserPrinterDevice", back_populates="gate_states"
    )
    preset: Mapped["Preset | None"] = relationship("Preset")
    spool: Mapped["UserSpool | None"] = relationship("UserSpool")

    def __repr__(self) -> str:
        return (
            f"<PresetGateState(id={self.id}, device_id={self.device_id}, "
            f"gate={self.gate_index}, preset_id={self.preset_id})>"
        )
