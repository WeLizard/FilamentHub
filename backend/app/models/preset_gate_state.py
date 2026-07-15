"""PresetGateState model — slot/gate state for preset-to-device mapping."""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, reconstructor, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.preset import Preset
    from app.models.user import User
    from app.models.user_printer_device import UserPrinterDevice
    from app.models.user_spool import UserSpool


class PresetGateStateSource(str, enum.Enum):
    """Source of the gate state update."""

    hh_snapshot = "hh_snapshot"
    manual_orca = "manual_orca"
    web_manual = "web_manual"


class HHGateStatus(int, enum.Enum):
    """Happy Hare gate status codes.

    Values:
        -1: unknown
         0: empty
         1: spool_loaded
         2: in_buffer
    """

    unknown = -1
    empty = 0
    spool_loaded = 1
    in_buffer = 2


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
    # HH status code semantics:
    # -1=unknown, 0=empty, 1=spool_loaded, 2=in_buffer
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
        # A physical spool can occupy at most one slot across all devices.
        Index(
            "uq_gate_state_active_spool",
            "spool_id",
            unique=True,
            postgresql_where=text("spool_id IS NOT NULL"),
            sqlite_where=text("spool_id IS NOT NULL"),
        ),
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    device: Mapped["UserPrinterDevice"] = relationship(
        "UserPrinterDevice", back_populates="gate_states"
    )
    preset: Mapped["Preset | None"] = relationship("Preset")
    spool: Mapped["UserSpool | None"] = relationship("UserSpool")

    @staticmethod
    def _to_aware_utc(ts: datetime) -> datetime:
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    @reconstructor
    def _normalize_datetimes_on_load(self) -> None:
        self.source_ts = self._to_aware_utc(self.source_ts)

    def __repr__(self) -> str:
        return (
            f"<PresetGateState(id={self.id}, device_id={self.device_id}, "
            f"gate={self.gate_index}, preset_id={self.preset_id})>"
        )
