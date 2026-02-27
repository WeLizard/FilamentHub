"""PresetUsageEvent model — filament usage history and adjustments."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.preset import Preset
    from app.models.user import User
    from app.models.user_printer_device import UserPrinterDevice


class PresetUsageEventType(str, enum.Enum):
    """Type of usage event."""

    print_estimate = "print_estimate"
    reconcile_adjust = "reconcile_adjust"
    manual_adjust = "manual_adjust"


class PresetUsageEvent(Base):
    """A single filament usage event (print estimate, manual adjustment, etc.)."""

    __tablename__ = "preset_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_printer_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    preset_id: Mapped[int | None] = mapped_column(
        ForeignKey("presets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    spool_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    event_type: Mapped[PresetUsageEventType] = mapped_column(
        Enum(PresetUsageEventType, name="preset_usage_event_type", native_enum=False),
        nullable=False,
    )
    delta_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    job_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    device: Mapped["UserPrinterDevice | None"] = relationship("UserPrinterDevice")
    preset: Mapped["Preset | None"] = relationship("Preset")

    def __repr__(self) -> str:
        return (
            f"<PresetUsageEvent(id={self.id}, user_id={self.user_id}, "
            f"type={self.event_type.value}, delta={self.delta_weight_g}g)>"
        )
